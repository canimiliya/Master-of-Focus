from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any

from PySide6 import QtCore, QtWidgets

from sgp_qt_core import global_data, save_data
from sgp_qt_dialogs import FocusTask, TaskSelectDialog
from sgp_qt_notify import notify_focus_complete, notify_focus_start
from sgp_qt_platform import notify_system, windows_force_top_alert


class TimerMixin:
    def on_countdown_button(self) -> None:
        if self.timer_running:
            if self.current_stage == "study":
                self._open_change_task_dialog()
            return
        self._open_start_dialog(mode="countdown")

    def on_countup_button(self) -> None:
        if self.timer_running:
            if self.current_stage == "study":
                self._open_change_task_dialog()
            return
        self._open_start_dialog(mode="countup")

    def _open_start_dialog(self, mode: str) -> None:
        data = global_data or {}
        if not data.get("today_task_submitted"):
            QtWidgets.QMessageBox.warning(self, "⚠️ 拦截", "请先点击【制定每日清单】提交任务！")
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

        self.current_focus_task = dlg.selected_task
        self._execute_start(mode)

    def _open_change_task_dialog(self) -> None:
        if not self.timer_running or self.current_stage != "study":
            return

        data = global_data or {}
        available: list[FocusTask] = []
        tasks_dict = data.get("today_structured_tasks", {})
        for cat in ("科研", "理论/技术"):
            for t in tasks_dict.get(cat, []) if isinstance(tasks_dict, dict) else []:
                if isinstance(t, dict) and not t.get("done"):
                    available.append(FocusTask(cat=cat, text=str(t.get("text", ""))))

        if not available:
            QtWidgets.QMessageBox.information(self, "提示", "没有其他可切换的未完成任务。")
            return

        dlg = TaskSelectDialog(self, available)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or dlg.selected_task is None:
            return

        self._change_focus_task(dlg.selected_task.cat, dlg.selected_task.text)

    def _execute_start(self, mode: str) -> None:
        self.timer_running = True
        self.timer_mode = mode
        self.current_stage = "study"
        self.pending_focus_segments = []
        self.focus_segment_start_dt = datetime.now()

        if mode == "countdown":
            self.time_left = 25 * 60
            self.elapsed_seconds = 0
            self.btn_countdown.setText("🔁 更换任务")
            self.btn_countdown.setEnabled(True)
            self.btn_countup.setEnabled(False)
            self.btn_cancel.setText("⏹️ 放弃专注 (番茄作废)")
        else:
            self.time_left = 0
            self.elapsed_seconds = 0
            self.btn_countup.setText("🔁 更换任务")
            self.btn_countup.setEnabled(True)
            self.btn_countdown.setEnabled(False)
            self.btn_cancel.setText("⏹️ 结束专注并记录")

        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setStyleSheet(self.btn_cancel.styleSheet().replace("#CCCCCC", "#FFA07A"))

        if self.current_focus_task:
            mode_tag = "🍅" if mode == "countdown" else "⏱️"
            self.stage_label.setText(f"{mode_tag} 正在执行: {self.current_focus_task.cat} - {self.current_focus_task.text}")
        self.stage_label.setStyleSheet("color:#FF69B4")

        self._update_timer_label()
        self._ticker.start()
        self._ensure_fit_height()

        if mode == "countup" and self.current_focus_task:
            notify_focus_start(
                self.current_focus_task.cat,
                self.current_focus_task.text,
                mode=mode,
            )

    def _change_focus_task(self, new_cat: str, new_text: str) -> None:
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
        mode_tag = "🍅" if self.timer_mode == "countdown" else "⏱️"
        self.stage_label.setText(f"{mode_tag} 正在执行: {new_cat} - {new_text}")
        self.stage_label.setStyleSheet("color:#FF69B4")
        self._ensure_fit_height()

    def _on_tick(self) -> None:
        if self.timer_mode == "countdown":
            if self.time_left <= 0:
                self._ticker.stop()
                if self.current_stage == "break":
                    self._on_break_finished()
                else:
                    self._on_countdown_finished()
                return
            self.time_left -= 1
        else:
            self.elapsed_seconds += 1

        self._update_timer_label()

    def _update_timer_label(self) -> None:
        if self.timer_mode == "countdown":
            mins, secs = divmod(max(self.time_left, 0), 60)
        else:
            mins, secs = divmod(self.elapsed_seconds, 60)
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")

    def _on_countdown_finished(self) -> None:
        self.timer_label.setText("00:00")
        self.timer_running = False
        self.btn_cancel.setEnabled(False)

        msg = "25分钟到了！别学了，快起来活动一下！\n点击软件内弹窗领取积分。"
        notify_system("⏰ 学习结束", msg)
        windows_force_top_alert("⏰ 学习结束", msg)

        QtWidgets.QMessageBox.information(self, "⏰ 学习结束", msg)
        ans = QtWidgets.QMessageBox.question(
            self, "核算积分", "刚才全程专注没有摸鱼吗？", QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if ans == QtWidgets.QMessageBox.StandardButton.Yes:
            self._apply_study_reward(tomato_count=1, points_per_tomato=25)
            QtWidgets.QMessageBox.information(self, "🎉 奖励发放", "太棒了！获得 25 积分！\n准备进入 5 分钟休息阶段~")
        else:
            QtWidgets.QMessageBox.information(self, "❌ 无效记录", "很遗憾，本次不计入积分。下次专心一点哦！")
            self.pending_focus_segments = []

        self.current_stage = "break"
        self.timer_running = True
        self.time_left = 5 * 60
        self.stage_label.setText("☕ 休息一下吧...")
        self.stage_label.setStyleSheet("color:#87CEFA")
        self.btn_cancel.setText("⏹️ 提前结束休息")
        self.btn_cancel.setEnabled(True)
        self.btn_countdown.setEnabled(False)
        self.btn_countup.setEnabled(False)

        self._ticker.start()
        self._ensure_fit_height()

    def _on_break_finished(self) -> None:
        msg = "5分钟休息结束啦！\n准备开启下一个番茄钟吧~"
        notify_system("⏰ 休息结束！", msg)
        windows_force_top_alert("⏰ 休息结束！", msg)
        self._reset_timer_ui("休息结束，准备开始专注")

    def _finish_countup(self) -> None:
        self._ticker.stop()
        self.timer_running = False
        self.btn_cancel.setEnabled(False)

        total_seconds = self.elapsed_seconds
        total_minutes = total_seconds // 60
        tomato_count = total_minutes // 25
        remainder_minutes = total_minutes % 25

        if tomato_count > 0:
            ans = QtWidgets.QMessageBox.question(
                self,
                "结束专注",
                f"本次专注 {total_minutes} 分钟，折合 {tomato_count} 个番茄钟"
                + (f"，余 {remainder_minutes} 分钟" if remainder_minutes > 0 else "")
                + f"。\n\n确认全程专注没有摸鱼吗？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if ans == QtWidgets.QMessageBox.StandardButton.Yes:
                self._apply_study_reward(tomato_count=tomato_count, points_per_tomato=25)
                summary = f"太棒了！专注 {total_minutes} 分钟，获得 {tomato_count * 25} 积分（{tomato_count} 个番茄钟）！"
                QtWidgets.QMessageBox.information(self, "🎉 奖励发放", summary)
            else:
                QtWidgets.QMessageBox.information(self, "❌ 无效记录", "很遗憾，本次不计入积分。下次专心一点哦！")
                self.pending_focus_segments = []
        else:
            ans = QtWidgets.QMessageBox.question(
                self,
                "结束专注",
                f"本次专注 {total_minutes} 分钟，不足 1 个番茄钟（需满 25 分钟）。\n\n确认全程专注没有摸鱼吗？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if ans == QtWidgets.QMessageBox.StandardButton.Yes:
                self._apply_study_reward(tomato_count=0, points_per_tomato=0)
                QtWidgets.QMessageBox.information(self, "📝 已记录", f"专注 {total_minutes} 分钟已记录，继续加油凑满 25 分钟获得番茄！")
            else:
                QtWidgets.QMessageBox.information(self, "❌ 无效记录", "很遗憾，本次不计入积分。下次专心一点哦！")
                self.pending_focus_segments = []

        self._reset_timer_ui()

    def _apply_study_reward(self, tomato_count: int = 1, points_per_tomato: int = 25) -> None:
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

        segments = list(self.pending_focus_segments)

        for seg in segments:
            try:
                self.append_focus_log(seg["start"], seg["end"], seg["category"], seg["task"])
            except Exception:
                pass
        self.pending_focus_segments = []

        def _split_seconds_by_segments(items: list[dict[str, Any]]) -> list[float]:
            secs_list: list[float] = []
            for item in items:
                try:
                    secs = float((item["end"] - item["start"]).total_seconds())
                except Exception:
                    secs = 0.0
                secs_list.append(max(0.0, secs))
            return secs_list

        split_seconds = _split_seconds_by_segments(segments)

        total_points = tomato_count * points_per_tomato
        if total_points > 0:
            data["total_points"] = int(data.get("total_points", 0) or 0) + total_points
        if tomato_count > 0:
            data["today_tomatoes"] = int(data.get("today_tomatoes", 0) or 0) + tomato_count
        total_mins = round(sum(s for s in split_seconds if s > 0) / 60.0)
        if total_mins > 0:
            data["today_study_time"] = int(data.get("today_study_time", 0) or 0) + total_mins
        for seg, secs in zip(segments, split_seconds):
            if secs <= 0:
                continue
            seg_end = seg.get("end")
            end_stamp = end_str
            if isinstance(seg_end, datetime):
                end_stamp = seg_end.strftime("%Y-%m-%d %H:%M:%S")
            data.setdefault("study_history", []).append(
                {
                    "date": end_stamp,
                    "study_time": round(secs / 60.0, 2),
                    "category": seg.get("category", self.current_focus_task.cat),
                    "task": seg.get("task", self.current_focus_task.text),
                }
            )
        save_data()
        self.export_task_reports()
        self.update_dashboard()

        notify_focus_complete(
            segments=segments,
            total_minutes=total_mins,
            total_points=total_points,
            mode=self.timer_mode,
        )

    def cancel_timer(self) -> None:
        if not self.timer_running:
            return

        if self.timer_mode == "countup" and self.current_stage == "study":
            self._finish_countup()
            return

        if self.current_stage == "study" and self.timer_mode == "countdown":
            self.timer_running = False
            self.btn_cancel.setEnabled(False)
            ans = QtWidgets.QMessageBox.question(
                self,
                "放弃专注",
                "确定要打断专注吗？中途打断则本番茄钟彻底作废！",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                self.timer_running = True
                self.btn_cancel.setEnabled(True)
                return
            self.pending_focus_segments = []
            self._ticker.stop()
            msg = "已作废，调整好状态再战！"
            self._reset_timer_ui(msg)
            return

        if self.current_stage == "break":
            self.timer_running = False
            self.btn_cancel.setEnabled(False)
            ans = QtWidgets.QMessageBox.question(
                self,
                "结束休息",
                "提前结束休息开启下一个番茄钟吗？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                self.timer_running = True
                self.btn_cancel.setEnabled(True)
                return
            self._ticker.stop()
            self._reset_timer_ui("休息已提前结束")
            return

    def _reset_timer_ui(self, msg: str = "准备开始专注") -> None:
        self.timer_running = False
        self.timer_mode = ""
        self.current_stage = ""
        self.time_left = 25 * 60
        self.elapsed_seconds = 0
        self.timer_label.setText("25:00")
        self.stage_label.setText(msg)
        self.stage_label.setStyleSheet("color:#888888")

        self.btn_countdown.setEnabled(True)
        self.btn_countdown.setText("🍅 番茄倒计时(25m)")
        self.btn_countup.setEnabled(True)
        self.btn_countup.setText("⏱️ 正向专注计时")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("⏹️ 放弃当前计时")
        self.btn_cancel.setStyleSheet(self.btn_cancel.styleSheet().replace("#FFA07A", "#CCCCCC"))
        self.focus_segment_start_dt = None
        self._ensure_fit_height()

    # ===================== daily rollover & logging =====================
