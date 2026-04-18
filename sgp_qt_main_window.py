"""Qt main window for Study Game Pro (PySide6)."""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import DATA_FOLDER_NAME, app_config, init_data, load_app_config, save_app_config
from sgp_qt_dialogs import FocusTask
from sgp_qt_platform import windows_force_top_alert
from sgp_qt_charts import ChartsMixin
from sgp_qt_exchange import ExchangeMixin
from sgp_qt_logs import LogsMixin
from sgp_qt_memo import MemoMixin
from sgp_qt_reading import ReadingMixin
from sgp_qt_tasks import TasksMixin
from sgp_qt_timer import TimerMixin
from sgp_qt_ui import UiMixin


class StudyGameQt(
    UiMixin,
    TimerMixin,
    LogsMixin,
    TasksMixin,
    ReadingMixin,
    ChartsMixin,
    ExchangeMixin,
    MemoMixin,
    QtWidgets.QMainWindow,
):
    WIDTH = 780

    def __init__(self):
        super().__init__()
        self.setWindowTitle("✨改变自己✨")

        # Fixed width (matches original). Height is managed by Qt layouts.
        self.setMinimumWidth(self.WIDTH)
        self.setMaximumWidth(self.WIDTH)

        load_app_config()
        self.ensure_storage_directory()
        init_data()

        # state
        self.time_left = 0
        self.timer_running = False
        self.current_stage = ""  # "study" | "break" | ""
        self.current_focus_task: FocusTask | None = None
        self.focus_segment_start_dt: datetime | None = None
        self.pending_focus_segments: list[dict[str, Any]] = []

        self.task_viewer_window: QtWidgets.QDialog | None = None
        self.reading_window: QtWidgets.QDialog | None = None
        self.reading_tree_metas: dict[str, Any] = {}
        self._report_write_permission_alerted = False

        self.current_date_str = datetime.now().strftime("%Y-%m-%d")

        self._ticker = QtCore.QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._on_tick)

        self._build_ui()
        # Ensure rollover settlement happens on startup before daily reset.
        self.handle_new_day_rollover(show_popup=True)
        self.schedule_daily_check()
        self._refresh_all_labels()

        # Similar to tkinter after(50,...): let layout settle, then adjust.
        QtCore.QTimer.singleShot(50, self._ensure_fit_height)

    # ------------------- data dir -------------------
    def ensure_storage_directory(self) -> None:
        root_dir = app_config.get("storage_root_dir")
        if root_dir and os.path.isdir(root_dir):
            data_dir = os.path.join(root_dir, DATA_FOLDER_NAME)
            if os.path.isdir(data_dir):
                app_config["data_dir"] = data_dir
                app_config["memo_dir"] = data_dir
                app_config["storage_dir_confirmed"] = True
                save_app_config()
                return

        if root_dir and not os.path.isdir(root_dir):
            app_config["storage_dir_confirmed"] = False
            save_app_config()

        QtWidgets.QMessageBox.information(
            self,
            "需要设置目录",
            "请设置统一的数据存储根目录。\n\n将在该目录下创建或使用【专注改变（个人软件数据）】文件夹。",
        )

        new_root = QtWidgets.QFileDialog.getExistingDirectory(self, "请选择统一的数据存储根目录")
        if not new_root:
            windows_force_top_alert("必须设置目录", "未选择目录，程序将退出。")
            raise SystemExit(0)

        self.apply_storage_directory(new_root_dir=new_root, show_message=False)

    def apply_storage_directory(self, new_root_dir: str | None = None, show_message: bool = True) -> None:
        if new_root_dir is None:
            new_root_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "请选择存放数据的文件夹")
            if not new_root_dir:
                return

        new_root_dir = os.path.normpath(new_root_dir)
        target_data_dir = os.path.join(new_root_dir, DATA_FOLDER_NAME)
        old_data_dir = app_config.get("data_dir")

        if not os.path.isdir(target_data_dir):
            if old_data_dir and os.path.isdir(old_data_dir):
                try:
                    os.makedirs(new_root_dir, exist_ok=True)
                    shutil.move(old_data_dir, target_data_dir)
                except Exception:
                    os.makedirs(target_data_dir, exist_ok=True)
            else:
                os.makedirs(target_data_dir, exist_ok=True)

        app_config["storage_root_dir"] = new_root_dir
        app_config["data_dir"] = target_data_dir
        app_config["memo_dir"] = target_data_dir
        app_config["storage_dir_confirmed"] = True
        save_app_config()
        init_data()

        if show_message:
            QtWidgets.QMessageBox.information(self, "设置成功", f"未来的数据将存储在：\n{target_data_dir}")

        self._refresh_all_labels()
        self._ensure_fit_height()

    # ------------------- UI -------------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        try:
            self._ticker.stop()
        except Exception:
            pass
        event.accept()


