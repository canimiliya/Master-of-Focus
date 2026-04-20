from __future__ import annotations
from datetime import datetime, timedelta
import os
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import PENALTY_MULTIPLIER, TASK_CATS, app_config, global_data, inject_long_term_tasks_for_date, save_app_config, save_data


class LogsMixin:
    def schedule_daily_check(self) -> None:
        if getattr(self, "_daily_check_timer", None) is not None:
            return
        self.current_date_str = datetime.now().strftime("%Y-%m-%d")
        self._daily_check_timer = QtCore.QTimer(self)
        self._daily_check_timer.setInterval(60 * 1000)
        self._daily_check_timer.timeout.connect(self._on_daily_check)
        self._daily_check_timer.start()

    def _on_daily_check(self) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d")
        if now_str != getattr(self, "current_date_str", now_str):
            self.current_date_str = now_str
            self.handle_new_day_rollover(show_popup=False)
        self.check_review_reminder()

    def check_review_reminder(self) -> None:
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        if now.hour != 23:
            return
        if now.minute < 30:
            return
        data = global_data or {}
        if data.get("today_review_submitted"):
            return
        if app_config.get("review_reminder_date") == today_str:
            return

        QtWidgets.QMessageBox.information(
            self,
            "⚠️ 复盘提醒",
            "现在距离零点不远了，请尽快提交【今日复盘】！\n\n点击“确认”后继续使用。",
        )
        app_config["review_reminder_date"] = today_str
        save_app_config()

    def get_reward_by_rate(self, rate: float) -> int:
        if rate >= 100:
            base = 200
        elif rate >= 80:
            base = 80
        elif rate >= 70:
            base = 30
        else:
            base = 0
        return int(round(base * PENALTY_MULTIPLIER))

    def build_task_status_lines(self, tasks_dict: dict[str, Any]) -> str:
        done_lines: list[str] = []
        undone_lines: list[str] = []
        for cat in TASK_CATS:
            for t in tasks_dict.get(cat, []) if isinstance(tasks_dict, dict) else []:
                if not isinstance(t, dict):
                    continue
                text = t.get("text", "")
                line = f"<{cat}>-{text}"
                if t.get("done"):
                    done_lines.append(f"√已完成——{line}")
                else:
                    undone_lines.append(f"×未完成——{line}")
        lines = done_lines + undone_lines
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    def build_daily_task_list_text(self, tasks_dict: dict[str, Any]) -> str:
        lines: list[str] = []
        if not isinstance(tasks_dict, dict):
            return ""
        for cat in TASK_CATS:
            items = tasks_dict.get(cat, [])
            if not isinstance(items, list) or not items:
                continue
            lines.append(f"[{cat}]")
            for i, t in enumerate(items):
                if isinstance(t, dict):
                    lines.append(f"{i+1}. {t.get('text', '')}")
        return "\n".join(lines)

    def upsert_daily_reward_history(self, date_str: str, rate: float, reward: int) -> None:
        data = global_data
        if data is None:
            return
        history = data.get("daily_rewards_history", [])
        if not isinstance(history, list):
            history = []
        updated = False
        for item in history:
            if isinstance(item, dict) and item.get("date") == date_str:
                item["rate"] = rate
                item["reward"] = reward
                updated = True
                break
        if not updated:
            history.append({"date": date_str, "rate": rate, "reward": reward})
        history = sorted([h for h in history if isinstance(h, dict)], key=lambda x: str(x.get("date", "")))[-365:]
        data["daily_rewards_history"] = history

    def log_to_txt(self, log_type: str, content: str) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = "daily_tasks_log.txt"
        if app_config.get("data_dir"):
            log_file = os.path.join(app_config["data_dir"], log_file)
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                if log_type == "task_update":
                    f.write(f"\n{'='*40}\n日期: {today}\n【每日任务设定】\n{content}\n")
                elif log_type == "pomodoro":
                    f.write(f"{content}")
                elif log_type == "review":
                    f.write(f"{content}")
                elif log_type == "task_cancel":
                    f.write(f"{content}")
                elif log_type == "task_time":
                    f.write(f"{content}")
                elif log_type == "focus_log":
                    f.write(f"{content}")
                elif log_type == "task_rollover":
                    f.write(f"{content}")
        except Exception:
            pass

    def export_task_reports(self) -> None:
        import csv

        data = global_data or {}
        data_dir = app_config.get("data_dir")
        if not data_dir or not os.path.exists(data_dir):
            return

        by_date: dict[str, dict[str, dict[str, Any]]] = {}
        by_cat: dict[str, dict[str, dict[str, Any]]] = {}

        exclusions = data.get("report_exclusions", [])
        excluded_focus: set[tuple[Any, Any, Any, Any]] = set()
        excluded_history: set[tuple[Any, Any, Any, Any]] = set()
        for ex in exclusions if isinstance(exclusions, list) else []:
            try:
                if not isinstance(ex, dict):
                    continue
                t = ex.get("type")
                if t == "focus_log":
                    excluded_focus.add((ex.get("start"), ex.get("end"), ex.get("category"), ex.get("task")))
                elif t == "study_history":
                    excluded_history.add((ex.get("date"), ex.get("category"), ex.get("task"), ex.get("study_time")))
            except Exception:
                pass

        def record(date_str: str, cat: str, task: str, dur: int) -> None:
            if dur <= 0:
                return
            by_date.setdefault(date_str, {})
            k = f"{cat}::{task}"
            by_date[date_str].setdefault(k, {"cat": cat, "task": task, "dur": 0})
            by_date[date_str][k]["dur"] += dur

            by_cat.setdefault(cat, {})
            by_cat[cat].setdefault(task, {"dates": set(), "dur": 0})
            by_cat[cat][task]["dates"].add(date_str)
            by_cat[cat][task]["dur"] += dur

        for item in data.get("study_history", []) if isinstance(data.get("study_history"), list) else []:
            try:
                if not isinstance(item, dict):
                    continue
                dt_full = str(item.get("date", ""))
                dur = int(item.get("study_time", item.get("duration", 0)) or 0)
                cat = str(item.get("category", "其他") or "其他")
                task = str(item.get("task", "未知任务") or "未知任务")
                if (dt_full, cat, task, dur) in excluded_history:
                    continue
                if dur <= 0:
                    continue
                end_dt = None
                try:
                    end_dt = datetime.strptime(dt_full, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        end_dt = datetime.strptime(dt_full, "%Y-%m-%d %H:%M")
                    except Exception:
                        end_dt = None
                if end_dt is None:
                    dt_str = dt_full.split()[0]
                    if len(dt_str) == 10:
                        record(dt_str, cat, task, dur)
                    continue
                start_dt = end_dt - timedelta(minutes=dur)
                for d_str, mins in self._split_minutes_by_date(start_dt, end_dt):
                    if mins > 0:
                        record(d_str, cat, task, mins)
            except Exception:
                pass

        for log in data.get("focus_logs", []) if isinstance(data.get("focus_logs"), list) else []:
            try:
                if not isinstance(log, dict):
                    continue
                cat = str(log.get("category", "") or "")
                if cat in ["科研", "理论/技术"]:
                    continue
                task = str(log.get("task", "未知任务") or "未知任务")
                start_str = log.get("start")
                end_str = log.get("end")
                if (start_str, end_str, cat, task) in excluded_focus:
                    continue
                s = datetime.strptime(str(start_str), "%Y-%m-%d %H:%M")
                e = datetime.strptime(str(end_str), "%Y-%m-%d %H:%M")
                for d_str, mins in self._split_minutes_by_date(s, e):
                    if mins > 0:
                        record(d_str, cat, task, mins)
            except Exception:
                pass

        try:
            file_date = os.path.join(data_dir, "任务复盘报表_按日期.csv")
            with open(file_date, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["日期", "任务分类", "子任务明细", "当日专注时长(分钟)"])
                for d in sorted(by_date.keys(), reverse=True):
                    for v in by_date[d].values():
                        writer.writerow([d, v["cat"], v["task"], v["dur"]])

            file_cat = os.path.join(data_dir, "任务复盘报表_按分类汇总.csv")
            with open(file_cat, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["任务分类", "子任务明细", "总计专注时长(分钟)", "坚持天数", "参与的打卡日期"])
                for cat in TASK_CATS + [c for c in by_cat.keys() if c not in TASK_CATS]:
                    if cat not in by_cat:
                        continue
                    tasks = sorted(by_cat[cat].items(), key=lambda x: int(x[1].get("dur", 0) or 0), reverse=True)
                    for task, v in tasks:
                        dates_list = sorted(list(v.get("dates", set())))
                        writer.writerow([cat, task, int(v.get("dur", 0) or 0), len(dates_list), "、".join(dates_list)])

            self._report_write_permission_alerted = False
        except PermissionError as e:
            print("写入CSV报表失败:", e)
            if not getattr(self, "_report_write_permission_alerted", False):
                self._report_write_permission_alerted = True
                QtWidgets.QMessageBox.warning(
                    self,
                    "报表写入失败",
                    "CSV报表正在被占用，无法实时更新。\n\n请关闭正在打开的报表文件（Excel/WPS），再勾选/取消勾选一次即可刷新。",
                )
        except Exception as e:
            print("写入CSV报表失败:", e)

    def handle_new_day_rollover(self, show_popup: bool = False) -> None:
        data = global_data
        if data is None:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        today_date = datetime.now().date()
        last_checkin_str = str(data.get("last_checkin_date") or "")
        settlement_msg: str | None = None

        new_day = last_checkin_str != today_str
        if new_day:
            tasks_snapshot = {
                cat: [dict(t) for t in data.get("today_structured_tasks", {}).get(cat, []) if isinstance(t, dict)]
                for cat in TASK_CATS
            }
            if last_checkin_str:
                self.log_daily_task_time(last_checkin_str, tasks_snapshot)

            carryover_tasks = {
                cat: [t for t in tasks_snapshot.get(cat, []) if not t.get("done")]
                for cat in TASK_CATS
            }

            if last_checkin_str:
                settlement_msg = f"已结算昨日({last_checkin_str})"

            if last_checkin_str and data.get("last_penalty_date") != last_checkin_str:
                total_tasks, done_tasks, rate = self.get_task_completion_stats()
                settlement_note = ""
                if data.get("today_task_submitted") and total_tasks > 0:
                    reward = self.get_reward_by_rate(rate)
                    penalty = self.get_penalty_by_rate(rate)
                    delta = 0
                    title = "【自动结算】"
                    if reward > 0:
                        delta = reward
                        title = "【自动奖励】"
                        data["total_points"] = int(data.get("total_points", 0) or 0) + reward
                    elif penalty < 0:
                        delta = penalty
                        title = "【自动惩罚】"
                        data["total_points"] = int(data.get("total_points", 0) or 0) + penalty

                    self.upsert_daily_reward_history(last_checkin_str, rate, delta)
                    settlement_note = f"完成率 {done_tasks}/{total_tasks} ({rate:.0f}%)，奖惩 {delta} 分"

                    if delta != 0:
                        task_status_text = ""
                        if penalty < 0:
                            task_status_text = self.build_task_status_lines(data.get("today_structured_tasks", {}))
                        log_text = (
                            f"{title}\n"
                            f"日期: {last_checkin_str}\n"
                            f"完成率 {done_tasks}/{total_tasks} ({rate:.0f}%)\n"
                            f"奖惩 {delta} 分\n"
                            f"{task_status_text}"
                            f"{'='*40}\n"
                        )
                        self.log_to_txt("review", log_text)
                else:
                    settlement_note = "昨日未提交任务清单，未结算奖惩"

                if settlement_msg and settlement_note:
                    settlement_msg = f"{settlement_msg}\n{settlement_note}"
                data["last_penalty_date"] = last_checkin_str

            if last_checkin_str:
                try:
                    last_date = datetime.strptime(last_checkin_str, "%Y-%m-%d").date()
                    if (today_date - last_date).days == 1:
                        data["continuous_checkin_days"] = int(data.get("continuous_checkin_days", 0) or 0) + 1
                    else:
                        data["continuous_checkin_days"] = 1
                except Exception:
                    data["continuous_checkin_days"] = 1
            else:
                data["continuous_checkin_days"] = 1

            data["today_tomatoes"] = 0
            data["today_study_time"] = 0
            data["today_exchanged_time"] = 0
            data["today_incentive_pool"] = 0
            data["today_structured_tasks"] = carryover_tasks

            inject_long_term_tasks_for_date(data, today_date)

            data["today_review_text"] = ""
            data["today_review_submitted"] = False
            data["last_checkin_date"] = today_str
            save_data()

        if inject_long_term_tasks_for_date(data, today_date):
            save_data()

        if new_day:
            today_tasks_text = self.build_daily_task_list_text(data.get("today_structured_tasks", {}))
            if not today_tasks_text:
                today_tasks_text = "（今日无任务）"
            log_text = (
                "\n\n\n"
                f"日期: {today_str}\n"
                "【今日任务清单】\n"
                f"{today_tasks_text}\n"
                f"{'='*40}\n"
            )
            self.log_to_txt("task_rollover", log_text)

        self.export_task_reports()

        self.update_date_label()
        self.update_dashboard()
        self.update_task_buttons()
        self.update_task_status_label()
        if show_popup and settlement_msg:
            QtWidgets.QMessageBox.information(self, "启动结算完成", settlement_msg)

    # ===================== focus logs & cancel logic =====================

    def normalize_dt(self, dt_obj: datetime) -> datetime:
        return dt_obj.replace(second=0, microsecond=0)

    def append_focus_log(self, start_dt: datetime, end_dt: datetime, cat: str, text: str) -> None:
        data = global_data
        if data is None:
            return
        start_dt = self.normalize_dt(start_dt)
        end_dt = self.normalize_dt(end_dt)
        if end_dt <= start_dt:
            return
        data.setdefault("focus_logs", []).append(
            {
                "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                "end": end_dt.strftime("%Y-%m-%d %H:%M"),
                "category": cat,
                "task": text,
            }
        )
        save_data()
        log_line = self._format_focus_log_line(start_dt, end_dt, cat, text)
        self.log_to_txt("focus_log", log_line)

    def get_today_focus_logs(self, include_current: bool = False) -> list[dict[str, Any]]:
        today_str = datetime.now().strftime("%Y-%m-%d")
        data = global_data or {}
        logs: list[dict[str, Any]] = []
        for item in data.get("focus_logs", []) if isinstance(data.get("focus_logs"), list) else []:
            if isinstance(item, dict) and str(item.get("start", "")).startswith(today_str):
                logs.append(item)

        if include_current and self.timer_running and self.current_stage == "study" and self.current_focus_task and self.focus_segment_start_dt:
            now_dt = self.normalize_dt(datetime.now())
            start_dt = self.normalize_dt(self.focus_segment_start_dt)
            if now_dt > start_dt:
                logs.append(
                    {
                        "start": start_dt.strftime("%Y-%m-%d %H:%M"),
                        "end": now_dt.strftime("%Y-%m-%d %H:%M"),
                        "category": self.current_focus_task.cat,
                        "task": self.current_focus_task.text,
                    }
                )
        return logs

    def _format_focus_log_line(self, start_dt: datetime, end_dt: datetime, cat: str, text: str) -> str:
        today = datetime.now().date()
        prefix = ""
        if start_dt.date() == (today - timedelta(days=1)):
            prefix = "昨天 "
        elif start_dt.date() != today:
            prefix = start_dt.strftime("%Y-%m-%d ")
        return f"{prefix}{start_dt.strftime('%H:%M')} —— {end_dt.strftime('%H:%M')} <{cat}>-{text}\n"

    def check_focus_conflict(self, start_dt: datetime, end_dt: datetime) -> tuple[str | None, str | None]:
        data = global_data or {}
        logs = list(data.get("focus_logs", []) or [])
        if self.timer_running and self.current_stage == "study" and self.current_focus_task and self.focus_segment_start_dt:
            now_dt = self.normalize_dt(datetime.now())
            seg_start = self.normalize_dt(self.focus_segment_start_dt)
            if now_dt > seg_start:
                logs.append(
                    {
                        "start": seg_start.strftime("%Y-%m-%d %H:%M"),
                        "end": now_dt.strftime("%Y-%m-%d %H:%M"),
                        "category": self.current_focus_task.cat,
                        "task": self.current_focus_task.text,
                    }
                )

        for item in logs:
            if not isinstance(item, dict):
                continue
            try:
                existing_start = datetime.strptime(str(item.get("start")), "%Y-%m-%d %H:%M")
                existing_end = datetime.strptime(str(item.get("end")), "%Y-%m-%d %H:%M")
            except Exception:
                continue
            if start_dt < existing_end and end_dt > existing_start:
                conflict_range = f"{existing_start.strftime('%m-%d %H:%M')} —— {existing_end.strftime('%m-%d %H:%M')}"
                conflict_task = f"<{item.get('category', '')}>-{item.get('task', '')}"
                return conflict_range, conflict_task
        return None, None

    def collect_manual_focus_time(self, cat: str, task_text: str) -> tuple[bool, datetime | None, datetime | None]:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("选择专注时间")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)

        title = QtWidgets.QLabel(f"任务: <{cat}>-{task_text}")
        title.setFont(self._font(size=9, bold=True))
        layout.addWidget(title)

        hours = [f"{h:02d}" for h in range(24)]
        minutes = [""] + [f"{m:02d}" for m in range(60)]

        def build_row(label_text: str) -> tuple[QtWidgets.QComboBox, QtWidgets.QComboBox]:
            row = QtWidgets.QHBoxLayout()
            lab = QtWidgets.QLabel(label_text)
            lab.setFixedWidth(40)
            row.addWidget(lab)
            hour_cb = QtWidgets.QComboBox()
            hour_cb.addItems([""] + hours)
            hour_cb.setFixedWidth(70)
            min_cb = QtWidgets.QComboBox()
            min_cb.addItems(minutes)
            min_cb.setFixedWidth(70)
            row.addWidget(hour_cb)
            row.addWidget(QtWidgets.QLabel(":"))
            row.addWidget(min_cb)
            row.addStretch(1)
            layout.addLayout(row)
            return hour_cb, min_cb

        start_hour_cb, start_min_cb = build_row("开始")
        end_hour_cb, end_min_cb = build_row("结束")

        start_yesterday = QtWidgets.QCheckBox("开始时间是昨天")
        layout.addWidget(start_yesterday)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("确认")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

        result: dict[str, Any] = {"ok": False, "start": None, "end": None}

        def confirm() -> None:
            sh_txt = start_hour_cb.currentText().strip()
            eh_txt = end_hour_cb.currentText().strip()
            if not sh_txt or not eh_txt:
                QtWidgets.QMessageBox.warning(dialog, "填写不完整", "请至少选择开始和结束的小时。")
                return
            sh = int(sh_txt)
            sm = int((start_min_cb.currentText() or "0") or "0")
            eh = int(eh_txt)
            em = int((end_min_cb.currentText() or "0") or "0")

            today_date = datetime.now().date()
            start_date = today_date - timedelta(days=1) if start_yesterday.isChecked() else today_date
            start_dt = datetime.combine(start_date, datetime.min.time()).replace(hour=sh, minute=sm)

            end_date = start_date
            if (eh, em) < (sh, sm):
                end_date = start_date + timedelta(days=1)
            end_dt = datetime.combine(end_date, datetime.min.time()).replace(hour=eh, minute=em)

            now_dt = self.normalize_dt(datetime.now())
            if start_dt > now_dt:
                QtWidgets.QMessageBox.warning(dialog, "时间错误", "开始时间必须早于当前时间。")
                return
            if end_dt > now_dt:
                QtWidgets.QMessageBox.warning(dialog, "时间错误", "结束时间必须早于当前时间。")
                return
            if end_dt <= start_dt:
                QtWidgets.QMessageBox.warning(dialog, "时间错误", "结束时间必须晚于开始时间。")
                return

            conflict_range, conflict_task = self.check_focus_conflict(start_dt, end_dt)
            if conflict_range:
                QtWidgets.QMessageBox.warning(dialog, "时间冲突", f"所选时间与已有记录冲突：\n{conflict_range} {conflict_task}")
                return

            self.append_focus_log(start_dt, end_dt, cat, task_text)
            result["ok"] = True
            result["start"] = start_dt
            result["end"] = end_dt
            dialog.accept()

        ok_btn.clicked.connect(confirm)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()
        return bool(result["ok"]), result.get("start"), result.get("end")

    def get_focus_minutes_by_task(self, date_str: str) -> dict[tuple[str, str], float]:
        data = global_data or {}
        totals: dict[tuple[str, str], float] = {}
        for item in data.get("focus_logs", []) if isinstance(data.get("focus_logs"), list) else []:
            if not isinstance(item, dict):
                continue
            start_str = str(item.get("start", "") or "")
            end_str = str(item.get("end", "") or "")
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
            except Exception:
                continue
            key = (str(item.get("category", "") or ""), str(item.get("task", "") or ""))
            for d_str, mins in self._split_minutes_by_date(start_dt, end_dt):
                if d_str != date_str or mins <= 0:
                    continue
                totals[key] = totals.get(key, 0) + mins
        return totals

    def _split_minutes_by_date(self, start_dt: datetime, end_dt: datetime) -> list[tuple[str, int]]:
        start_dt = self.normalize_dt(start_dt)
        end_dt = self.normalize_dt(end_dt)
        if end_dt <= start_dt:
            return []

        parts: list[tuple[str, int]] = []
        cursor = start_dt
        while cursor.date() < end_dt.date():
            next_midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
            mins = int((next_midnight - cursor).total_seconds() / 60)
            if mins > 0:
                parts.append((cursor.strftime("%Y-%m-%d"), mins))
            cursor = next_midnight

        mins = int((end_dt - cursor).total_seconds() / 60)
        if mins > 0:
            parts.append((cursor.strftime("%Y-%m-%d"), mins))
        return parts

    def log_daily_task_time(self, date_str: str, tasks_snapshot: dict[str, list[dict[str, Any]]]) -> None:
        totals = self.get_focus_minutes_by_task(date_str)
        lines: list[str] = []
        for cat in TASK_CATS:
            tasks = tasks_snapshot.get(cat, [])
            if not tasks:
                continue
            lines.append(f"[{cat}]")
            for t in tasks:
                text = t.get("text", "")
                mins = totals.get((cat, text), 0)
                lines.append(f"- {text}：{self.format_minutes(mins)}")
        if not lines:
            return
        log_text = f"【每日任务耗时】\n日期: {date_str}\n" + "\n".join(lines) + f"\n{'='*40}\n"
        self.log_to_txt("task_time", log_text)

    def open_work_log_window(self) -> None:
        win = QtWidgets.QDialog(self)
        win.setWindowTitle("📒 今日工作日志")
        win.resize(620, 560)
        win.setModal(True)

        root = QtWidgets.QVBoxLayout(win)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        logs = self.get_today_focus_logs(include_current=True)
        logs.sort(key=lambda x: str(x.get("start", "")))

        root.addWidget(QtWidgets.QLabel("今日专注日志"))
        log_text = QtWidgets.QTextEdit()
        log_text.setReadOnly(True)
        log_text.setFont(self._font(size=9, bold=False))
        root.addWidget(log_text, 1)

        if not logs:
            log_text.setPlainText("暂无记录\n")
        else:
            lines: list[str] = []
            for item in logs:
                try:
                    start_dt = datetime.strptime(str(item["start"]), "%Y-%m-%d %H:%M")
                    end_dt = datetime.strptime(str(item["end"]), "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                lines.append(f"{start_dt.strftime('%H:%M')} —— {end_dt.strftime('%H:%M')} <{item.get('category', '')}>-{item.get('task', '')}")
            log_text.setPlainText("\n".join(lines) + ("\n" if lines else ""))

        root.addWidget(QtWidgets.QLabel("已完成任务耗时"))
        done_text = QtWidgets.QTextEdit()
        done_text.setReadOnly(True)
        done_text.setFont(self._font(size=9, bold=False))
        root.addWidget(done_text, 1)

        totals: dict[tuple[str, str], float] = {}
        for item in logs:
            try:
                start_dt = datetime.strptime(str(item["start"]), "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(str(item["end"]), "%Y-%m-%d %H:%M")
            except Exception:
                continue
            mins = (end_dt - start_dt).total_seconds() / 60.0
            key = (str(item.get("category", "") or ""), str(item.get("task", "") or ""))
            totals[key] = totals.get(key, 0) + mins

        data = global_data or {}
        tasks_dict = data.get("today_structured_tasks", {})
        out_lines: list[str] = []
        if isinstance(tasks_dict, dict):
            for cat in TASK_CATS:
                for t in tasks_dict.get(cat, []) if isinstance(tasks_dict.get(cat), list) else []:
                    if not isinstance(t, dict) or not t.get("done"):
                        continue
                    mins = totals.get((cat, str(t.get("text", "") or "")), 0)
                    if mins <= 0:
                        continue
                    out_lines.append(f"√已完成——耗时{self.format_minutes(mins)}——<{cat}>-{t.get('text', '')}")

        done_text.setPlainText("\n".join(out_lines) + ("\n" if out_lines else "暂无已完成任务\n"))
        win.exec()

    # ===================== reading module =====================
