"""Platform-specific helpers for the Qt app.

Kept small and isolated so most modules stay platform-neutral.
"""

from __future__ import annotations

import ctypes
import socket
import sys
import threading

try:
    from win10toast import ToastNotifier

    WIN_TOAST_AVAILABLE = True
except Exception:
    ToastNotifier = None
    WIN_TOAST_AVAILABLE = False


_instance_socket: socket.socket | None = None


def windows_force_top_alert(title: str, message: str) -> None:
    """Show a top-most blocking alert on Windows; fallback to stderr."""
    if sys.platform == "win32":
        style = 0x00000000 | 0x00000030 | 0x00040000 | 0x00010000
        ctypes.windll.user32.MessageBoxW(0, message, title, style)
        return
    print(f"{title}: {message}", file=sys.stderr)


def enforce_single_instance() -> None:
    """Exit the process if another instance is already running."""
    global _instance_socket
    try:
        _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _instance_socket.bind(("127.0.0.1", 38594))
    except OSError:
        windows_force_top_alert("启动拦截", "【改变自己】已经在运行中了！请查看任务栏或系统托盘。")
        raise SystemExit(0)


def notify_system(title: str, message: str, duration: int = 6) -> bool:
    """Send a best-effort system notification (Windows toast if available)."""
    if sys.platform == "win32" and WIN_TOAST_AVAILABLE:

        def _show() -> None:
            try:
                ToastNotifier().show_toast(title, message, duration=duration, threaded=False)
            except Exception:
                pass

        threading.Thread(target=_show, daemon=True).start()
        return True
    return False
