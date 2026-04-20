from __future__ import annotations
from datetime import datetime
from typing import Any

from PySide6 import QtWidgets

from sgp_qt_core import TASK_CATS, app_config, global_data, inject_long_term_tasks_for_date, save_app_config, save_data


class TasksMixin:
    def is_duplicate_task_text(self, text: str) -> bool:
        normalized = text.strip().casefold()
        if not normalized:
            return False
        data = global_data or {}
        tasks_dict = data.get("today_structured_tasks", {})
        if not isinstance(tasks_dict, dict):
            return False
        for items in tasks_dict.values():
            if not isinstance(items, list):
                continue
            for t in items:
                if not isinstance(t, dict):
                    continue
                if str(t.get("text", "")).strip().casefold() == normalized:
                    return True
        return False

    def reset_cancel_counter_if_needed(self) -> None:
        month_key = datetime.now().strftime("%Y-%m")
        if app_config.get("cancel_month") != month_key:
            app_config["cancel_month"] = month_key
            app_config["cancel_count"] = 0
            save_app_config()

    def get_cancel_penalty_info(self) -> tuple[int, int]:
        self.reset_cancel_counter_if_needed()
        count = int(app_config.get("cancel_count", 0) or 0)
        penalty = 20 * (2**count)
        return count, penalty

    def prompt_cancel_reason(self, cat: str, text: str, count: int, penalty: int) -> str | None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("取消任务")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)
        info = (
            f"任务: <{cat}>-{text}\n"
            f"本月已使用 {count} 次取消机会\n"
            f"若本次取消将扣除 {penalty} 分"
        )
        info_label = QtWidgets.QLabel(info)
        info_label.setWordWrap(True)
        info_label.setFont(self._font(size=9, bold=False))
        layout.addWidget(info_label)

        layout.addWidget(QtWidgets.QLabel("请输入取消原因:"))
        reason_edit = QtWidgets.QTextEdit()
        reason_edit.setMinimumHeight(100)
        layout.addWidget(reason_edit)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("确认")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

        result = {"reason": ""}

        def confirm() -> None:
            reason = reason_edit.toPlainText().strip()
            if not reason:
                QtWidgets.QMessageBox.warning(dialog, "需要原因", "请填写取消原因。")
                return
            result["reason"] = reason
            dialog.accept()

        ok_btn.clicked.connect(confirm)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return result["reason"] or None

    def handle_task_cancel(self, cat: str, idx: int, viewer: QtWidgets.QDialog | None = None) -> None:
        data = global_data
        if data is None:
            return
        if int(data.get("total_points", 0) or 0) < 0:
            QtWidgets.QMessageBox.warning(self, "无法取消", "当前积分为负，禁止取消任务。")
            return

        tasks_dict = data.get("today_structured_tasks", {})
        tasks = tasks_dict.get(cat, []) if isinstance(tasks_dict, dict) else []
        if not isinstance(tasks, list) or idx < 0 or idx >= len(tasks):
            return

        task_text = str(tasks[idx].get("text", "") if isinstance(tasks[idx], dict) else "")
        if task_text.startswith("（长期）") or task_text.startswith("(长期)"):
            QtWidgets.QMessageBox.warning(self, "无法取消", "长期任务只要没有完成，就永远不能删除！")
            return

        if isinstance(tasks[idx], dict) and tasks[idx].get("done"):
            QtWidgets.QMessageBox.warning(self, "无法取消", "已完成任务不能取消。")
            return

        count, penalty = self.get_cancel_penalty_info()
        reason = self.prompt_cancel_reason(cat, task_text, count, penalty)
        if not reason:
            return

        del tasks[idx]
        data["total_points"] = int(data.get("total_points", 0) or 0) - penalty
        app_config["cancel_count"] = count + 1
        save_app_config()
        save_data()

        log_text = (
            f"【任务取消】\n"
            f"日期: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"任务: <{cat}>-{task_text}\n"
            f"原因: {reason}\n"
            f"本月已使用 {count + 1} 次，扣除 {penalty} 分\n"
            f"{'='*40}\n"
        )
        self.log_to_txt("task_cancel", log_text)

        self.update_dashboard()
        self.update_task_status_label()

        if viewer is not None:
            try:
                viewer.close()
            except Exception:
                pass
            self.open_task_viewer()

    # ===================== windows: tasks / review =====================

    def refresh_task_viewer_if_open(self) -> None:
        viewer = self.task_viewer_window
        if viewer is None:
            return
        try:
            if viewer.isVisible():
                viewer.close()
        except Exception:
            pass
        finally:
            if self.task_viewer_window is viewer:
                self.task_viewer_window = None
        try:
            self.open_task_viewer()
        except Exception:
            pass

    def add_long_term_task_dialog(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("新增长期任务")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)

        name_entry = QtWidgets.QLineEdit()
        cat_combo = QtWidgets.QComboBox()
        cat_combo.addItems(TASK_CATS)
        days_spin = QtWidgets.QSpinBox()
        days_spin.setRange(1, 3650)
        days_spin.setValue(10)
        mins_spin = QtWidgets.QSpinBox()
        mins_spin.setRange(0, 24 * 60)
        mins_spin.setValue(30)

        form.addRow("任务名称:", name_entry)
        form.addRow("所属分类:", cat_combo)
        form.addRow("持续天数:", days_spin)
        form.addRow("每日需专注分钟数:", mins_spin)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("保存")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

        def submit() -> None:
            data = global_data
            if data is None:
                return
            text = name_entry.text().strip()
            cat = cat_combo.currentText()
            days = int(days_spin.value())
            req_time = int(mins_spin.value())
            if not text:
                QtWidgets.QMessageBox.warning(dialog, "错误", "任务名称不能为空。")
                return

            today_str = datetime.now().strftime("%Y-%m-%d")
            data.setdefault("long_term_tasks", []).append({
                "text": text,
                "cat": cat,
                "start_date": today_str,
                "days": days,
                "req_time": req_time,
            })

            inject_long_term_tasks_for_date(data, datetime.now().date())
            save_data()

            self.handle_new_day_rollover(show_popup=False)
            QtWidgets.QMessageBox.information(
                dialog,
                "成功",
                f"长期任务【{text}】已添加！\n\n请重新打开或者刷新【任务打卡看板】即可看到最新任务。",
            )
            dialog.accept()
            self.update_dashboard()
            self.update_task_buttons()
            self.update_task_status_label()
            self.refresh_task_viewer_if_open()

        ok_btn.clicked.connect(submit)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def open_task_editor(self) -> None:
        editor = QtWidgets.QDialog(self)
        editor.setWindowTitle("📝 制定今日 Todo 清单")
        editor.resize(500, 650)
        editor.setModal(True)

        root = QtWidgets.QVBoxLayout(editor)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QtWidgets.QWidget()
        scroll.setWidget(content)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        hint = QtWidgets.QLabel("请添加今日任务小点 (科研/理论属学习类，将记录番茄)")
        hint.setStyleSheet("color:gray")
        hint.setWordWrap(True)
        content_layout.addWidget(hint)

        tasks_container = QtWidgets.QWidget()
        tasks_layout = QtWidgets.QVBoxLayout(tasks_container)
        tasks_layout.setContentsMargins(0, 0, 0, 0)
        tasks_layout.setSpacing(10)
        content_layout.addWidget(tasks_container)

        btn_long_term = QtWidgets.QPushButton("➕ 新增长期任务")
        btn_long_term.setMinimumHeight(40)
        btn_submit = QtWidgets.QPushButton("🚀 完成设定并提交")
        btn_submit.setMinimumHeight(44)
        content_layout.addWidget(btn_long_term)
        content_layout.addWidget(btn_submit)
        content_layout.addStretch(1)

        def clear_layout(lay: QtWidgets.QLayout) -> None:
            while lay.count():
                item = lay.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                elif item.layout() is not None:
                    clear_layout(item.layout())

        def refresh_editor_ui() -> None:
            data = global_data
            if data is None:
                return
            clear_layout(tasks_layout)

            for cat in TASK_CATS:
                cat_frame = QtWidgets.QFrame()
                cat_frame.setStyleSheet("background:#F5F5F5;border-radius:6px;")
                cat_lay = QtWidgets.QVBoxLayout(cat_frame)
                cat_lay.setContentsMargins(10, 10, 10, 10)
                cat_lay.setSpacing(6)

                title = QtWidgets.QLabel(f"■ {cat}")
                title_color = "#FF69B4" if cat in ("科研", "理论/技术") else "#20B2AA"
                title.setStyleSheet(f"color:{title_color};")
                title.setFont(self._font(size=11, bold=True))
                cat_lay.addWidget(title)

                tasks = data.get("today_structured_tasks", {}).get(cat, [])
                if not isinstance(tasks, list):
                    tasks = []
                for idx, t in enumerate(tasks):
                    if not isinstance(t, dict):
                        continue
                    row = QtWidgets.QWidget()
                    row_lay = QtWidgets.QHBoxLayout(row)
                    row_lay.setContentsMargins(0, 0, 0, 0)
                    row_lay.setSpacing(8)

                    lbl = QtWidgets.QLabel(f"• {t.get('text', '')}")
                    lbl.setWordWrap(True)
                    lbl.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
                    row_lay.addWidget(lbl, 1)

                    btn_del = QtWidgets.QPushButton("删除")
                    btn_del.setFixedWidth(60)
                    btn_del.clicked.connect(lambda _=False, c=cat, i=idx: delete_task(c, i))
                    row_lay.addWidget(btn_del, 0)
                    cat_lay.addWidget(row)

                add_row = QtWidgets.QWidget()
                add_lay = QtWidgets.QHBoxLayout(add_row)
                add_lay.setContentsMargins(0, 0, 0, 0)
                entry = QtWidgets.QLineEdit()
                entry.setPlaceholderText("添加任务...")
                btn_add = QtWidgets.QPushButton("添加")
                btn_add.clicked.connect(lambda _=False, c=cat, e=entry: add_task(c, e))
                add_lay.addWidget(entry, 1)
                add_lay.addWidget(btn_add, 0)
                cat_lay.addWidget(add_row)

                tasks_layout.addWidget(cat_frame)

        def add_task(cat: str, entry_widget: QtWidgets.QLineEdit) -> None:
            data = global_data
            if data is None:
                return
            text = entry_widget.text().strip()
            if not text:
                return
            if self.is_duplicate_task_text(text):
                QtWidgets.QMessageBox.warning(editor, "重复任务", "已存在同名任务，不能重复添加。")
                return
            data.setdefault("today_structured_tasks", {}).setdefault(cat, []).append({"text": text, "done": False})
            entry_widget.clear()
            refresh_editor_ui()

        def delete_task(cat: str, idx: int) -> None:
            data = global_data
            if data is None:
                return
            tasks = data.get("today_structured_tasks", {}).get(cat, [])
            if not isinstance(tasks, list) or idx < 0 or idx >= len(tasks):
                return
            del tasks[idx]
            refresh_editor_ui()

        def submit_tasks() -> None:
            data = global_data
            if data is None:
                return
            total = 0
            tasks_dict = data.get("today_structured_tasks", {})
            if isinstance(tasks_dict, dict):
                total = sum(len(items) for items in tasks_dict.values() if isinstance(items, list))
            if total == 0:
                QtWidgets.QMessageBox.warning(editor, "无法提交", "四大分类中总共至少需要添加 1 个任务小点才能提交！")
                return

            data["today_task_submitted"] = True
            save_data()
            self.update_task_buttons()
            self.update_task_status_label()

            log_text = ""
            for cat in TASK_CATS:
                items = data.get("today_structured_tasks", {}).get(cat, [])
                if not isinstance(items, list) or not items:
                    continue
                log_text += f"[{cat}]\n"
                for i, t in enumerate(items):
                    if isinstance(t, dict):
                        log_text += f"{i+1}. {t.get('text', '')}\n"
            self.log_to_txt("task_update", log_text)

            editor.accept()
            QtWidgets.QMessageBox.information(self, "提交成功", "今日任务已设定！你可以开始打卡和计时的旅程了。")

        btn_long_term.clicked.connect(self.add_long_term_task_dialog)
        btn_submit.clicked.connect(submit_tasks)

        refresh_editor_ui()
        editor.exec()

    def open_task_viewer(self) -> None:
        if self.task_viewer_window is not None:
            try:
                if self.task_viewer_window.isVisible():
                    self.task_viewer_window.raise_()
                    self.task_viewer_window.activateWindow()
                    return
            except Exception:
                pass
            self.task_viewer_window = None

        viewer = QtWidgets.QDialog(self)
        viewer.setWindowTitle("✅ 今日打卡看板")
        viewer.resize(420, 560)
        viewer.setModal(False)
        self.task_viewer_window = viewer

        def _on_finished(_code: int) -> None:
            if self.task_viewer_window is viewer:
                self.task_viewer_window = None

        viewer.finished.connect(_on_finished)

        font_normal = self._font(size=10, bold=False)
        font_strike = self._font(size=10, bold=False)
        font_strike.setStrikeOut(True)
        font_bold_normal = self._font(size=11, bold=True)
        font_bold_strike = self._font(size=11, bold=True)
        font_bold_strike.setStrikeOut(True)

        root = QtWidgets.QVBoxLayout(viewer)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QtWidgets.QWidget()
        scroll.setWidget(content)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        def clear_layout(lay: QtWidgets.QLayout) -> None:
            while lay.count():
                item = lay.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                elif item.layout() is not None:
                    clear_layout(item.layout())

        def check_category_status(cat_label: QtWidgets.QLabel, cat: str) -> None:
            data = global_data or {}
            items = data.get("today_structured_tasks", {}).get(cat, [])
            if not isinstance(items, list) or not items:
                cat_label.setFont(font_bold_normal)
                cat_label.setStyleSheet("color:#2F4F4F")
                return
            all_done = all(isinstance(t, dict) and t.get("done") for t in items)
            cat_label.setFont(font_bold_strike if all_done else font_bold_normal)
            cat_label.setStyleSheet("color:gray" if all_done else "color:#2F4F4F")

        def toggle_task(cat: str, idx: int, cb: QtWidgets.QCheckBox, cancel_btn: QtWidgets.QPushButton, cat_label: QtWidgets.QLabel) -> None:
            data = global_data
            if data is None:
                return

            tasks_dict = data.get("today_structured_tasks", {})
            tasks = tasks_dict.get(cat, []) if isinstance(tasks_dict, dict) else []
            if not isinstance(tasks, list) or idx < 0 or idx >= len(tasks):
                return
            task_item = tasks[idx]
            if not isinstance(task_item, dict):
                return

            is_done = cb.isChecked()
            task_text = str(task_item.get("text", "") or "")
            today_str = datetime.now().strftime("%Y-%m-%d")
            manual_logged = False

            exclusions = data.setdefault("report_exclusions", [])
            if not isinstance(exclusions, list):
                exclusions = []
                data["report_exclusions"] = exclusions

            restored = False
            if is_done:
                if cat in ("生活", "兴趣爱好"):
                    latest_ex_idx = None
                    latest_ex_start = None
                    for i, ex in enumerate(exclusions):
                        if not isinstance(ex, dict) or ex.get("type") != "focus_log":
                            continue
                        if ex.get("category") != cat or ex.get("task") != task_text:
                            continue
                        s = str(ex.get("start", "") or "")
                        if not s.startswith(today_str):
                            continue
                        if latest_ex_start is None or s > latest_ex_start:
                            latest_ex_start = s
                            latest_ex_idx = i
                    if latest_ex_idx is not None:
                        del exclusions[latest_ex_idx]
                        restored = True

                if cat in ("科研", "理论/技术") and not restored:
                    latest_ex_idx = None
                    latest_ex_date = None
                    for i, ex in enumerate(exclusions):
                        if not isinstance(ex, dict) or ex.get("type") != "study_history":
                            continue
                        if ex.get("category") != cat or ex.get("task") != task_text:
                            continue
                        d = str(ex.get("date", "") or "")
                        if not d.startswith(today_str):
                            continue
                        if latest_ex_date is None or d > latest_ex_date:
                            latest_ex_date = d
                            latest_ex_idx = i
                    if latest_ex_idx is not None:
                        del exclusions[latest_ex_idx]
                        restored = True

            if is_done and (not restored) and cat in ("生活", "兴趣爱好"):
                ok, _start_dt, _end_dt = self.collect_manual_focus_time(cat, task_text)
                if not ok:
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
                    return

            if is_done and (not restored) and cat in ("科研", "理论/技术"):
                has_history = any(
                    isinstance(item, dict)
                    and item.get("category") == cat
                    and item.get("task") == task_text
                    and str(item.get("date", "")).startswith(today_str)
                    for item in data.get("study_history", [])
                )
                focus_totals = self.get_focus_minutes_by_task(today_str)
                has_focus = focus_totals.get((cat, task_text), 0) > 0
                if not (has_history or has_focus):
                    ok, start_dt, end_dt = self.collect_manual_focus_time(cat, task_text)
                    if not ok or start_dt is None or end_dt is None:
                        cb.blockSignals(True)
                        cb.setChecked(False)
                        cb.blockSignals(False)
                        return

                    mins = int((end_dt - start_dt).total_seconds() / 60)
                    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                    data.setdefault("study_history", []).append(
                        {"date": end_str, "study_time": mins, "category": cat, "task": task_text}
                    )
                    data["today_study_time"] = int(data.get("today_study_time", 0) or 0) + mins
                    save_data()
                    manual_logged = True

            if is_done and cat in ("科研", "理论/技术") and (task_text.startswith("（长期）") or task_text.startswith("(长期)")):
                if not manual_logged:
                    req_time = int(task_item.get("req_time", 0) or 0)
                    totals = self.get_focus_minutes_by_task(today_str)
                    invested = totals.get((cat, task_text), 0)
                    if invested < req_time:
                        cb.blockSignals(True)
                        cb.setChecked(False)
                        cb.blockSignals(False)
                        QtWidgets.QMessageBox.warning(
                            viewer,
                            "时长不足",
                            f"该长期任务需专注满 {req_time} 分钟！\n当前仅记录了 {int(invested)} 分钟。",
                        )
                        return

            if not is_done:
                if cat in ("生活", "兴趣爱好"):
                    latest_log = None
                    latest_start = None
                    for log in data.get("focus_logs", []) if isinstance(data.get("focus_logs"), list) else []:
                        if not isinstance(log, dict):
                            continue
                        if log.get("category") != cat or log.get("task") != task_text:
                            continue
                        start_str = str(log.get("start", "") or "")
                        if latest_start is None or start_str > latest_start:
                            latest_start = start_str
                            latest_log = log
                    if latest_log is not None:
                        try:
                            data["focus_logs"].remove(latest_log)
                        except Exception:
                            pass
                        exclusions[:] = [
                            ex
                            for ex in exclusions
                            if not (
                                isinstance(ex, dict)
                                and ex.get("type") == "focus_log"
                                and ex.get("start") == latest_log.get("start")
                                and ex.get("end") == latest_log.get("end")
                                and ex.get("category") == latest_log.get("category")
                                and ex.get("task") == latest_log.get("task")
                            )
                        ]

                if cat in ("科研", "理论/技术"):
                    excluded_history = {
                        (ex.get("date"), ex.get("category"), ex.get("task"), ex.get("study_time"))
                        for ex in exclusions
                        if isinstance(ex, dict) and ex.get("type") == "study_history"
                    }
                    latest_item = None
                    latest_date = None
                    latest_dur = None
                    for item in data.get("study_history", []) if isinstance(data.get("study_history"), list) else []:
                        if not isinstance(item, dict):
                            continue
                        if item.get("category") != cat or item.get("task") != task_text:
                            continue
                        date_str = str(item.get("date", "") or "")
                        if not date_str.startswith(today_str):
                            continue
                        dur = item.get("study_time", item.get("duration", 0))
                        key = (date_str, cat, task_text, dur)
                        if key in excluded_history:
                            continue
                        if latest_date is None or date_str > latest_date:
                            latest_date = date_str
                            latest_item = item
                            latest_dur = dur
                    if latest_item is not None:
                        exclusions.append(
                            {
                                "type": "study_history",
                                "date": latest_item.get("date"),
                                "study_time": latest_dur,
                                "category": latest_item.get("category"),
                                "task": latest_item.get("task"),
                            }
                        )

            data["today_structured_tasks"][cat][idx]["done"] = is_done
            reading_changed = self.apply_reading_task_status(task_item, is_done)
            literature_changed = self.apply_literature_task_status(task_item, is_done)

            cb.setFont(font_strike if is_done else font_normal)
            cb.setStyleSheet("color:gray" if is_done else "color:black")
            cancel_btn.setEnabled(not is_done)

            check_category_status(cat_label, cat)
            save_data()
            self.update_task_status_label()
            self.export_task_reports()
            if reading_changed or literature_changed:
                self.refresh_reading_ui()

        def add_task_in_viewer(cat: str, entry_widget: QtWidgets.QLineEdit) -> None:
            data = global_data
            if data is None:
                return
            text = entry_widget.text().strip()
            if not text:
                return
            if self.is_duplicate_task_text(text):
                QtWidgets.QMessageBox.warning(viewer, "重复任务", "已存在同名任务，不能重复添加。")
                return
            data.setdefault("today_structured_tasks", {}).setdefault(cat, []).append({"text": text, "done": False})
            save_data()
            entry_widget.clear()
            rebuild_viewer_ui()
            self.update_task_status_label()

        def rebuild_viewer_ui() -> None:
            clear_layout(content_layout)

            data = global_data or {}
            submitted = bool(data.get("today_task_submitted"))

            for idx_c, cat in enumerate(TASK_CATS):
                cat_frame = QtWidgets.QFrame()
                cat_frame.setStyleSheet("background:white;border:1px solid #DDDDDD;border-radius:6px;")
                cat_lay = QtWidgets.QVBoxLayout(cat_frame)
                cat_lay.setContentsMargins(10, 10, 10, 10)
                cat_lay.setSpacing(6)

                cat_label = QtWidgets.QLabel(f"{idx_c+1}  {cat}")
                cat_label.setFont(font_bold_normal)
                cat_label.setStyleSheet("color:#2F4F4F")
                cat_lay.addWidget(cat_label)

                tasks = data.get("today_structured_tasks", {}).get(cat, [])
                if not isinstance(tasks, list):
                    tasks = []

                for i, t in enumerate(tasks):
                    if not isinstance(t, dict):
                        continue
                    row = QtWidgets.QWidget()
                    row_lay = QtWidgets.QHBoxLayout(row)
                    row_lay.setContentsMargins(0, 0, 0, 0)
                    row_lay.setSpacing(6)

                    cb = QtWidgets.QCheckBox(str(t.get("text", "") or ""))
                    cb.setToolTip(cb.text())
                    cb.setChecked(bool(t.get("done")))
                    cb.setFont(font_strike if t.get("done") else font_normal)
                    cb.setStyleSheet("color:gray" if t.get("done") else "color:black")
                    row_lay.addWidget(cb, 1)

                    cancel_btn = QtWidgets.QPushButton("取消")
                    cancel_btn.setFixedWidth(50)
                    cancel_btn.setEnabled(not bool(t.get("done")))
                    cancel_btn.clicked.connect(lambda _=False, c=cat, idx=i: self.handle_task_cancel(c, idx, viewer))
                    row_lay.addWidget(cancel_btn, 0)

                    cb.stateChanged.connect(lambda _state, c=cat, idx=i, _cb=cb, _btn=cancel_btn, _lab=cat_label: toggle_task(c, idx, _cb, _btn, _lab))

                    cat_lay.addWidget(row)

                if submitted:
                    add_row = QtWidgets.QWidget()
                    add_lay = QtWidgets.QHBoxLayout(add_row)
                    add_lay.setContentsMargins(0, 0, 0, 0)
                    entry = QtWidgets.QLineEdit()
                    entry.setPlaceholderText("添加任务...")
                    btn_add = QtWidgets.QPushButton("添加")
                    btn_add.clicked.connect(lambda _=False, c=cat, e=entry: add_task_in_viewer(c, e))
                    add_lay.addWidget(entry, 1)
                    add_lay.addWidget(btn_add, 0)
                    cat_lay.addWidget(add_row)

                check_category_status(cat_label, cat)
                content_layout.addWidget(cat_frame)

            btn_long_term = QtWidgets.QPushButton("➕ 新增长期任务")
            btn_long_term.setMinimumHeight(36)
            btn_long_term.clicked.connect(self.add_long_term_task_dialog)
            content_layout.addWidget(btn_long_term)
            content_layout.addStretch(1)

        rebuild_viewer_ui()
        viewer.show()

    def open_review(self) -> None:
        data = global_data or {}
        if data.get("today_review_submitted"):
            QtWidgets.QMessageBox.information(self, "提示", "今日已复盘，无需重复提交！")
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("今日复盘")
        dialog.resize(520, 360)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(20, 15, 20, 15)
        root.setSpacing(10)

        root.addWidget(QtWidgets.QLabel("请输入今日任务总结与复盘反思："))
        review_text = QtWidgets.QTextEdit()
        root.addWidget(review_text, 1)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("提交")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        def submit_review_text() -> None:
            data2 = global_data
            if data2 is None:
                return
            content = review_text.toPlainText().strip()
            if not content:
                QtWidgets.QMessageBox.warning(dialog, "内容为空", "请填写复盘内容后再提交。")
                return
            data2["today_review_text"] = content
            data2["today_review_submitted"] = True
            save_data()
            task_status_text = self.build_task_status_lines(data2.get("today_structured_tasks", {}))
            log_text = f"【今日复盘】\n{task_status_text}\n今日反思：\n{data2['today_review_text']}\n{'='*40}\n"
            self.log_to_txt("review", log_text)
            dialog.accept()
            QtWidgets.QMessageBox.information(self, "提交成功", "复盘已提交，零点后将自动结算完成率奖惩。")

        ok_btn.clicked.connect(submit_review_text)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    # ===================== windows: exchange / incentive =====================
