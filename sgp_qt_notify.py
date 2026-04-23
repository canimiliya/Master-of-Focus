"""WeChat Work (企业微信) Webhook notification channel for Study Game Pro.

Provides:
  - send_wecom_message(): low-level HTTP POST to webhook
  - notify_focus_complete(): focus session end notification
  - notify_task_checkin(): task check-in notification (done + remaining)
  - notify_daily_task_list(): periodic daily task list push
  - notify_review_reminder(): night review reminder
  - NotificationManager: QTimer-based random reminder scheduler
"""

from __future__ import annotations

import json
import random
import ssl
import threading
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from PySide6 import QtCore

from sgp_qt_core import TASK_CATS, app_config, global_data


def _webhook_url() -> str:
    return str(app_config.get("notify_wecom_webhook_url", "") or "").strip()


def _notify_enabled() -> bool:
    return bool(app_config.get("notify_enabled")) and bool(_webhook_url())


def _username_tag() -> str:
    name = str(app_config.get("notify_username", "") or "").strip()
    if name:
        return f"> **用户**: {name}\n"
    return ""


def send_wecom_message(title: str, content: str) -> bool:
    url = _webhook_url()
    if not url:
        return False

    if title:
        md_content = f"## {title}\n{content}"
    else:
        md_content = content
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": md_content},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=10, context=context) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            return result.get("errcode") == 0
    except Exception:
        return False


def _send_async(title: str, content: str) -> None:
    threading.Thread(target=send_wecom_message, args=(title, content), daemon=True).start()


def notify_focus_complete(
    segments: list[dict[str, Any]],
    total_minutes: int,
    total_points: int,
    mode: str = "countdown",
) -> None:
    if not _notify_enabled():
        return

    filtered = [
        s for s in segments
        if s.get("category") in ("科研", "理论/技术")
    ]
    if not filtered:
        return

    start_dt = None
    end_dt = None
    for s in filtered:
        s_start = s.get("start")
        s_end = s.get("end")
        if isinstance(s_start, datetime):
            if start_dt is None or s_start < start_dt:
                start_dt = s_start
        if isinstance(s_end, datetime):
            if end_dt is None or s_end > end_dt:
                end_dt = s_end

    if isinstance(start_dt, datetime) and isinstance(end_dt, datetime):
        time_display = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
    else:
        time_display = datetime.now().strftime("%H:%M")

    if mode == "countdown":
        title = "番茄倒计时结束"
    else:
        title = "正向专注结束"

    task_lines: list[str] = []
    for seg in filtered:
        cat = seg.get("category", "")
        task = seg.get("task", "")
        try:
            seg_mins = int((seg["end"] - seg["start"]).total_seconds() // 60)
        except Exception:
            seg_mins = 0
        if seg_mins <= 0:
            continue
        task_lines.append(f"<{cat}>-{task} ({seg_mins}min)")

    if not task_lines:
        return

    if len(task_lines) == 1:
        task_text = task_lines[0]
    else:
        task_text = "\n".join(f"{i+1}. {line}" for i, line in enumerate(task_lines))

    content = (
        f"{_username_tag()}"
        f"> **时间**: {time_display}\n"
        f"> **任务**: {task_text}\n"
        f"> **时长**: {total_minutes} 分钟\n\n"
        f"获得 <font color=\"warning\">{total_points} 积分</font>，继续加油！"
    )
    _send_async(title, content)


def notify_focus_start(cat: str, task: str, mode: str = "countup") -> None:
    if not _notify_enabled():
        return
    if cat not in ("科研", "理论/技术"):
        return

    now_str = datetime.now().strftime("%H:%M")
    name = str(app_config.get("notify_username", "") or "").strip()
    if name:
        greeting = f"{name}！"
    else:
        greeting = ""

    mode_label = "正向专注" if mode == "countup" else "番茄倒计时"
    content = (
        f"{_username_tag()}"
        f"> **时间**: {now_str}\n"
        f"> **任务**: <{cat}>-{task}\n\n"
        f"{greeting}开始进行{mode_label}！"
    )
    _send_async(f"{mode_label}开始", content)


_checkin_buffer: list[dict[str, Any]] = []
_checkin_timer: QtCore.QTimer | None = None


def _flush_checkin_buffer() -> None:
    global _checkin_timer
    if _checkin_timer is not None:
        _checkin_timer.stop()
        _checkin_timer = None

    if not _checkin_buffer:
        return

    if not _notify_enabled():
        _checkin_buffer.clear()
        return

    data = global_data or {}
    tasks_dict = data.get("today_structured_tasks", {})
    if not isinstance(tasks_dict, dict):
        _checkin_buffer.clear()
        return

    done_lines: list[str] = []
    for c in TASK_CATS:
        for t in tasks_dict.get(c, []):
            if not isinstance(t, dict):
                continue
            text = t.get("text", "")
            if t.get("done"):
                done_lines.append(f"<font color=\"info\">√</font> <{c}>-{text}")

    today_str = datetime.now().strftime("%Y-%m-%d")
    all_times: list[datetime] = []
    for item in _checkin_buffer:
        cat_i = item.get("cat", "")
        task_i = item.get("task", "")
        found_in_logs = False
        for log in data.get("focus_logs", []) if isinstance(data.get("focus_logs"), list) else []:
            if not isinstance(log, dict):
                continue
            if log.get("category") != cat_i or log.get("task") != task_i:
                continue
            start_str = str(log.get("start", "") or "")
            end_str = str(log.get("end", "") or "")
            if not start_str.startswith(today_str):
                continue
            found_in_logs = True
            try:
                all_times.append(datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                try:
                    all_times.append(datetime.strptime(start_str, "%Y-%m-%d %H:%M"))
                except ValueError:
                    pass
            try:
                all_times.append(datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                try:
                    all_times.append(datetime.strptime(end_str, "%Y-%m-%d %H:%M"))
                except ValueError:
                    pass
        if not found_in_logs:
            for sh in data.get("study_history", []) if isinstance(data.get("study_history"), list) else []:
                if not isinstance(sh, dict):
                    continue
                if sh.get("category") != cat_i or sh.get("task") != task_i:
                    continue
                date_str = str(sh.get("date", "") or "")
                if not date_str.startswith(today_str):
                    continue
                try:
                    end_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        end_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                    except ValueError:
                        continue
                study_mins_i = int(sh.get("study_time", 0) or 0)
                start_dt = end_dt - timedelta(minutes=study_mins_i)
                all_times.append(start_dt)
                all_times.append(end_dt)

    if all_times:
        all_times.sort()
        time_display = f"{all_times[0].strftime('%H:%M')} - {all_times[-1].strftime('%H:%M')}"
    else:
        now = datetime.now()
        time_display = now.strftime("%H:%M")

    tomatoes = int(data.get("today_tomatoes", 0) or 0)
    study_mins = int(data.get("today_study_time", 0) or 0)

    if len(_checkin_buffer) == 1:
        item = _checkin_buffer[0]
        just_done_text = f"<{item['cat']}>-{item['task']}"
    else:
        just_done_parts = [f"<{item['cat']}>-{item['task']}" for item in _checkin_buffer]
        just_done_text = "\n".join(f"{i+1}. {p}" for i, p in enumerate(just_done_parts))

    content = (
        f"{_username_tag()}"
        f"> **时间**: {time_display}\n"
        f"> **刚完成**: {just_done_text}\n"
        f"> **今日番茄**: {tomatoes} 个\n"
        f"> **今日学习**: {study_mins} 分钟\n\n"
    )

    if done_lines:
        content += f"**已完成 ({len(done_lines)})**\n"
        for line in done_lines:
            content += f"{line}\n"

    _checkin_buffer.clear()
    _send_async("任务打卡", content)


def notify_task_checkin(cat: str, task: str) -> None:
    global _checkin_timer

    _checkin_buffer.append({"cat": cat, "task": task, "time": datetime.now()})

    if _checkin_timer is None:
        _checkin_timer = QtCore.QTimer()
        _checkin_timer.setSingleShot(True)
        _checkin_timer.timeout.connect(_flush_checkin_buffer)

    _checkin_timer.start(30000)


def notify_daily_task_list() -> None:
    if not _notify_enabled():
        return
    data = global_data or {}
    tasks_dict = data.get("today_structured_tasks", {})
    if not isinstance(tasks_dict, dict):
        return

    now_str = datetime.now().strftime("%H:%M")
    content = f"{_username_tag()}> **时间**: {now_str}\n\n"

    has_any = False
    for cat in TASK_CATS:
        items = tasks_dict.get(cat, [])
        if not isinstance(items, list) or not items:
            continue
        has_any = True
        done_count = sum(1 for t in items if isinstance(t, dict) and t.get("done"))
        total = len(items)
        undone_count = total - done_count
        content += f"**[{cat}]** 已完成 <font color=\"info\">{done_count}</font> / 未完成 <font color=\"warning\">{undone_count}</font>\n"

    if not has_any:
        return

    _send_async("今日任务清单", content)


def notify_review_reminder() -> None:
    if not _notify_enabled():
        return
    now_str = datetime.now().strftime("%H:%M")
    content = (
        f"{_username_tag()}"
        f"> **时间**: {now_str}\n\n"
        f"距离零点不远了，请尽快提交 <font color=\"warning\">今日复盘</font>！\n\n"
        f"打开软件点击【今日复盘】即可。"
    )
    _send_async("复盘提醒", content)


class NotificationManager(QtCore.QObject):
    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._reminder_timer = QtCore.QTimer(self)
        self._reminder_timer.setSingleShot(True)
        self._reminder_timer.timeout.connect(self._on_reminder)
        self._review_notified_today = ""
        self._custom_fired_today: set[str] = set()

        self._minute_timer = QtCore.QTimer(self)
        self._minute_timer.setInterval(60000)
        self._minute_timer.timeout.connect(self._on_minute_tick)

    def start(self) -> None:
        self._schedule_next_reminder()
        self._minute_timer.start()

    def _schedule_next_reminder(self) -> None:
        delay_minutes = random.randint(90, 180)
        self._reminder_timer.start(delay_minutes * 60 * 1000)

    def _on_reminder(self) -> None:
        notify_daily_task_list()
        self._schedule_next_reminder()

    def _on_minute_tick(self) -> None:
        self.check_review_time()
        self._check_custom_scheduled()

    def _check_custom_scheduled(self) -> None:
        if not _notify_enabled():
            return
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_hm = now.strftime("%H:%M")

        for item in app_config.get("custom_scheduled_messages", []):
            if not isinstance(item, dict):
                continue
            msg_time = str(item.get("time", "")).strip()
            msg_content = str(item.get("content", "")).strip()
            if not msg_time or not msg_content:
                continue

            fired_key = f"{today_str}|{msg_time}|{msg_content}"
            if fired_key in self._custom_fired_today:
                continue

            if current_hm == msg_time:
                self._custom_fired_today.add(fired_key)
                _send_async("", msg_content)

    def check_review_time(self) -> None:
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        if now.hour == 23 and now.minute >= 30:
            if self._review_notified_today != today_str:
                data = global_data or {}
                if not data.get("today_review_submitted"):
                    notify_review_reminder()
                    self._review_notified_today = today_str
