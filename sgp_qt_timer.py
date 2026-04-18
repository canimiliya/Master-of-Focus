from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any

from PySide6 import QtCore, QtWidgets

from sgp_qt_core import global_data, save_data
from sgp_qt_dialogs import FocusTask, TaskSelectDialog
from sgp_qt_platform import notify_system


class TimerMixin:
    def on_tomato_button(self) -> None:
        if not self.timer_running:
            self.start_tomato_dialog_by_action("start")
            return
        if self.current_stage == "study":
            self.start_tomato_dialog_by_action("change")
            return

    def start_tomato_dialog_by_action(self, action: str) -> None:
        data = global_data or {}
        if not data.get("today_task_submitted"):
            QtWidgets.QMessageBox.warning(self, "⚠️ 拦截", "请先点击【制定每日清单】提交任务！")
            return

        if action == "start" and self.timer_running:
            return

        available: list[FocusTask] = []
        tasks_dict = data.get("today_structured_tasks", {})
        for cat in ("科研", "理论/技术"):
            for t in tasks_dict.get(cat, []) if isinstance(tasks_dict, dict) else []:
                if isinstance(t, dict) and not t.get("done"):
                    available.append(FocusTask(cat=cat, text=str(t.get("text", ""))))

        if not available:
            QtWidgets.QMessageBox.warning(
                self,
                "无可用任务",
                "当前没有未完成的【科研】或【理论/技术】任务小点，无法开启学习番茄钟！\n（生活和兴趣爱好不计入专注记录）",
            )
            return

        dlg = TaskSelectDialog(self, available)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or dlg.selected_task is None:
            return

        if action == "start":
            self.current_focus_task = dlg.selected_task
            self.execute_start_tomato()
        else:
            self.change_focus_task(dlg.selected_task.cat, dlg.selected_task.text)

    def execute_start_tomato(self) -> None:
        self.timer_running = True
        self.btn_tomato.setText("🔁 更换任务")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setStyleSheet(self.btn_cancel.styleSheet().replace("#CCCCCC", "#FFA07A"))
        self.btn_cancel.setText("⏹️ 放弃专注 (直接作废)")

        self.current_stage = "study"
        self.time_left = 25 * 60
        self.focus_segment_start_dt = datetime.now()
        self.pending_focus_segments = []

        if self.current_focus_task:
            self.stage_label.setText(f"📖 正在执行: {self.current_focus_task.cat} - {self.current_focus_task.text}")
        self.stage_label.setStyleSheet("color:#FF69B4")

        self._update_timer_label()
        self._ticker.start()
        self._ensure_fit_height()

    def change_focus_task(self, new_cat: str, new_text: str) -> None:
        if not self.timer_running or self.current_stage != "study":
            return
        now_dt = datetime.now()
        if self.focus_segment_start_dt and self.current_focus_task:
            self.pending_focus_segments.append(
                {
                    "start": self.focus_segment_start_dt,
                    "end": now_dt,
                    "category": self.current_focus_task.cat,
                    "task": self.current_focus_task.text,
                }
            )

        self.current_focus_task = FocusTask(cat=new_cat, text=new_text)
        self.focus_segment_start_dt = now_dt
        self.stage_label.setText(f"📖 正在执行: {new_cat} - {new_text}")
        self.stage_label.setStyleSheet("color:#FF69B4")
        self._ensure_fit_height()

    def _on_tick(self) -> None:
        if self.time_left <= 0:
            self._ticker.stop()
            self.timer_finished()
            return
        self.time_left -= 1
        self._update_timer_label()

    def _update_timer_label(self) -> None:
        mins, secs = divmod(max(self.time_left, 0), 60)
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")

    def timer_finished(self) -> None:
        self.timer_label.setText("00:00")

        if self.current_stage == "study":
            msg = "25分钟到了！别学了，快起来活动一下！\n点击软件内弹窗领取积分。"
            notify_system("⏰ 学习结束", msg)

            QtWidgets.QMessageBox.information(self, "⏰ 学习结束", msg)
            ans = QtWidgets.QMessageBox.question(
                self, "核算积分", "刚才全程专注没有摸鱼吗？", QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )

            if ans == QtWidgets.QMessageBox.StandardButton.Yes:
                self._apply_study_reward()
                QtWidgets.QMessageBox.information(self, "🎉 奖励发放", "太棒了！获得 25 积分！\n准备进入 5 分钟休息阶段~")
            else:
                QtWidgets.QMessageBox.information(self, "❌ 无效记录", "很遗憾，本次不计入积分。下次专心一点哦！")
                self.pending_focus_segments = []

            self.current_stage = "break"
            self.time_left = 5 * 60
            self.stage_label.setText("☕ 休息一下吧...")
            self.stage_label.setStyleSheet("color:#87CEFA")
            self.btn_cancel.setText("⏹️ 提前结束休息")

            self._ticker.start()
            self._ensure_fit_height()
            return

        if self.current_stage == "break":
            notify_system("⏰ 休息结束！", "5分钟休息结束啦！\n准备开启下一个番茄钟吧~")
            self.timer_running = False
            self.current_stage = ""
            self.btn_tomato.setText("🍅 开始专注 (25分钟)")
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("⏹️ 放弃当前计时")
            self.stage_label.setText("准备开始专注")
            self.stage_label.setStyleSheet("color:#888888")
            self.timer_label.setText("25:00")
            self.focus_segment_start_dt = None
            self._ensure_fit_height()

    def _apply_study_reward(self) -> None:
        data = global_data
        if data is None or self.current_focus_task is None:
            return

        end_dt = datetime.now()
        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        if self.focus_segment_start_dt and self.current_focus_task:
            self.pending_focus_segments.append(
                {
                    "start": self.focus_segment_start_dt,
                    "end": end_dt,
                    "category": self.current_focus_task.cat,
                    "task": self.current_focus_task.text,
                }
            )

        # Write focus segments to focus_logs (for work log / long-term task timing).
        for seg in self.pending_focus_segments:
            try:
                self.append_focus_log(seg["start"], seg["end"], seg["category"], seg["task"])
            except Exception:
                pass
        self.pending_focus_segments = []

        data["total_points"] = int(data.get("total_points", 0) or 0) + 25
        data["today_tomatoes"] = int(data.get("today_tomatoes", 0) or 0) + 1
        data["today_study_time"] = int(data.get("today_study_time", 0) or 0) + 25
        data.setdefault("study_history", []).append(
            {"date": end_str, "study_time": 25, "category": self.current_focus_task.cat, "task": self.current_focus_task.text}
        )
        save_data()
        self.export_task_reports()

        start_dt = end_dt - timedelta(minutes=25)
        log_line = f"{start_dt.strftime('%H:%M')} —— {end_dt.strftime('%H:%M')} <{self.current_focus_task.cat}>-{self.current_focus_task.text}\n"
        self.log_to_txt("pomodoro", log_line)
        self.update_dashboard()

    def cancel_timer(self) -> None:
        if not self.timer_running:
            return

        if self.current_stage == "study":
            ans = QtWidgets.QMessageBox.question(
                self,
                "放弃专注",
                "确定要打断专注吗？中途打断则本番茄钟彻底作废！",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self.pending_focus_segments = []
            msg = "已作废，调整好状态再战！"
        else:
            ans = QtWidgets.QMessageBox.question(
                self,
                "结束休息",
                "提前结束休息开启下一个番茄钟吗？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            msg = "休息已提前结束"

        self._ticker.stop()
        self.timer_running = False
        self.current_stage = ""
        self.time_left = 25 * 60
        self.timer_label.setText("25:00")
        self.stage_label.setText(msg)
        self.stage_label.setStyleSheet("color:#888888")

        self.btn_tomato.setText("🍅 开始专注 (25分钟)")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("⏹️ 放弃当前计时")
        self.focus_segment_start_dt = None
        self._ensure_fit_height()

    # ===================== daily rollover & logging =====================
