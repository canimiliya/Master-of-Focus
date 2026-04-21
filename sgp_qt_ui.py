from __future__ import annotations
from datetime import datetime
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import PENALTY_MULTIPLIER, TASK_CATS, app_config, get_holiday_info, global_data


class UiMixin:
    def _font(self, family: str = "Microsoft YaHei", size: int = 10, bold: bool = False) -> QtGui.QFont:
        f = QtGui.QFont(family)
        f.setPointSize(size)
        f.setBold(bold)
        return f

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QtWidgets.QFrame()
        header.setStyleSheet("background:#FFB6C1;")
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(0, 10, 0, 10)
        header_layout.setSpacing(4)

        self.date_label = QtWidgets.QLabel("")
        self.date_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.date_label.setFont(self._font(size=10, bold=False))
        self.date_label.setStyleSheet("color:#FFFFFF")

        self.task_status_label = QtWidgets.QLabel("")
        self.task_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.task_status_label.setFont(self._font(size=10, bold=True))
        self.task_status_label.setStyleSheet("color:#FFFFE0")

        self.penalty_hint_label = QtWidgets.QLabel("")
        self.penalty_hint_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.penalty_hint_label.setFont(self._font(size=9, bold=False))
        self.penalty_hint_label.setStyleSheet("color:#FFFFFF")

        self.points_label = QtWidgets.QLabel("")
        self.points_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.points_label.setFont(self._font(size=20, bold=True))
        self.points_label.setStyleSheet("color:#FFFFFF")

        self.games_label = QtWidgets.QLabel("")
        self.games_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.games_label.setFont(self._font(size=11, bold=False))
        self.games_label.setStyleSheet("color:#FFFFFF")

        self.discount_info_label = QtWidgets.QLabel("")
        self.discount_info_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.discount_info_label.setFont(self._font(size=9, bold=True))
        self.discount_info_label.setStyleSheet("color:#FFFFE0")

        header_layout.addWidget(self.date_label)
        header_layout.addWidget(self.task_status_label)
        header_layout.addWidget(self.penalty_hint_label)
        header_layout.addWidget(self.points_label)
        header_layout.addWidget(self.games_label)
        header_layout.addWidget(self.discount_info_label)

        root.addWidget(header)

        # body
        body = QtWidgets.QFrame()
        body.setStyleSheet("background:#FFF0F5;")
        body_layout = QtWidgets.QHBoxLayout(body)
        body_layout.setContentsMargins(20, 10, 20, 10)
        body_layout.setSpacing(20)

        # left
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.timer_label = QtWidgets.QLabel("25:00")
        self.timer_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        timer_font = QtGui.QFont("Arial")
        timer_font.setPointSize(48)
        timer_font.setBold(True)
        self.timer_label.setFont(timer_font)
        self.timer_label.setStyleSheet("color:#FF69B4; padding-top:6px; padding-bottom:6px;")
        fm = QtGui.QFontMetrics(timer_font)
        self.timer_label.setMinimumHeight(fm.boundingRect("00:00").height() + 12)

        self.stage_label = QtWidgets.QLabel("准备开始专注")
        self.stage_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.stage_label.setWordWrap(True)
        self.stage_label.setFont(self._font(size=12, bold=False))
        self.stage_label.setStyleSheet("color:#888888")

        left_layout.addSpacing(6)
        left_layout.addWidget(self.timer_label)
        left_layout.addWidget(self.stage_label)
        left_layout.addStretch(1)

        # left bottom buttons
        self.btn_tomato = self._mk_btn("🍅 开始专注 (25分钟)", bg="#FF69B4", fg="white")
        self.btn_cancel = self._mk_btn("⏹️ 放弃当前计时", bg="#CCCCCC", fg="black")
        self.btn_cancel.setEnabled(False)

        self.btn_daily_task = self._mk_btn("📝 制定每日清单", bg="#87CEFA", fg="white")
        self.btn_view_task = self._mk_btn("✅ 任务打卡看板", bg="#87CEFA", fg="white", w=160)
        self.btn_review_task = self._mk_btn("📝 今日复盘", bg="#FFD700", fg="black", w=140)

        self.two_btn_row = QtWidgets.QHBoxLayout()
        self.two_btn_row.setContentsMargins(0, 0, 0, 0)
        self.two_btn_row.setSpacing(10)
        self.two_btn_row.addWidget(self.btn_view_task)
        self.two_btn_row.addWidget(self.btn_review_task)

        self.tasks_block = QtWidgets.QWidget()
        self.tasks_block_layout = QtWidgets.QVBoxLayout(self.tasks_block)
        self.tasks_block_layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_block_layout.setSpacing(8)
        self.tasks_block_layout.addWidget(self.btn_daily_task)

        # reading button
        self.btn_reading = self._mk_btn("📚 阅读管理", bg="#20B2AA", fg="white")

        left_layout.addWidget(self.btn_tomato)
        left_layout.addWidget(self.btn_cancel)
        left_layout.addWidget(self.tasks_block)
        left_layout.addWidget(self.btn_reading)

        # right
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addStretch(1)

        self.btn_exchange = self._mk_btn("🎮 兑换商店", bg="#98FB98", fg="black")
        self.btn_stats = self._mk_btn("📊 查看高级数据与图表", bg="#DDA0DD", fg="white")
        self.btn_memo = self._mk_btn("💡 随手记 (文件/图文归档)", bg="#FFB6C1", fg="white")
        self.btn_pdf2md = self._mk_btn("📄 批量翻译 / 文本处理", bg="#20B2AA", fg="white")
        self.btn_work_log = self._mk_btn("📒 今日工作日志", bg="#FFB07C", fg="black")
        self.btn_change_dir = self._mk_btn("📁 更改数据存储目录", bg="#B0C4DE", fg="white")

        right_layout.addWidget(self.btn_exchange)
        right_layout.addWidget(self.btn_stats)
        right_layout.addWidget(self.btn_memo)
        right_layout.addWidget(self.btn_pdf2md)
        right_layout.addWidget(self.btn_work_log)
        right_layout.addWidget(self.btn_change_dir)

        body_layout.addWidget(left, 1)
        body_layout.addWidget(right, 1)
        root.addWidget(body)

        # signals
        self.btn_tomato.clicked.connect(self.on_tomato_button)
        self.btn_cancel.clicked.connect(self.cancel_timer)
        self.btn_change_dir.clicked.connect(self.change_data_directory)

        self.btn_daily_task.clicked.connect(self.open_task_editor)
        self.btn_view_task.clicked.connect(self.open_task_viewer)
        self.btn_review_task.clicked.connect(self.open_review)
        self.btn_reading.clicked.connect(self.open_reading_library)
        self.btn_exchange.clicked.connect(self.open_exchange_shop)
        self.btn_stats.clicked.connect(self.show_charts_window)
        self.btn_memo.clicked.connect(self.open_memo_window)
        self.btn_pdf2md.clicked.connect(self.open_pdf2md_window)
        self.btn_work_log.clicked.connect(self.open_work_log_window)

        self.update_task_buttons()

    def _mk_btn(self, text: str, bg: str, fg: str, w: int = 320) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        b.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        b.setMinimumHeight(42)
        b.setMinimumWidth(w)
        b.setFont(self._font(size=12, bold=True))
        b.setStyleSheet(
            "QPushButton{" f"background:{bg};color:{fg};border:none;border-radius:6px;padding:8px;" "}"
            "QPushButton:disabled{background:#DDDDDD;color:#888888;}"
        )
        return b

    def _todo(self, name: str) -> None:
        QtWidgets.QMessageBox.information(self, "Qt 重构进行中", f"【{name}】尚未迁移到 Qt 版本。\n\n我会在后续步骤逐个迁移。")

    # ------------------- layout sizing -------------------

    def _ensure_fit_height(self) -> None:
        """Resize window height to fit current layout (Qt will compute correct sizeHint)."""
        self.centralWidget().adjustSize()
        hint = self.sizeHint()
        min_h = 500
        target_h = max(min_h, int(hint.height()))
        # Keep fixed width; let height change.
        self.resize(self.WIDTH, target_h)

    # ------------------- labels / dashboard -------------------

    def _refresh_all_labels(self) -> None:
        self.update_date_label()
        self.update_dashboard()
        self.update_task_status_label()
        self.update_task_buttons()
        self._ensure_fit_height()

    def update_date_label(self) -> None:
        today_str_full = datetime.now().strftime("%Y年%m月%d日")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_text = weekdays[datetime.now().weekday()]
        holiday_suffix = ""

        info = get_holiday_info(datetime.now().strftime("%Y-%m-%d"))
        if info:
            holiday = info.get("holiday")
            if isinstance(holiday, dict):
                if holiday.get("holiday") is True:
                    holiday_suffix = f" · 节假日: {holiday.get('name', '')}".rstrip()
                elif holiday.get("holiday") is False:
                    holiday_suffix = f" · 调休补班: {holiday.get('name', '')}".rstrip()

            if not holiday_suffix:
                day_type = info.get("type", {}).get("type")
                if day_type == 2:
                    holiday_suffix = " · 节假日"
                elif day_type == 3:
                    holiday_suffix = " · 调休补班"

        self.date_label.setText(f"📅 {today_str_full} {weekday_text}{holiday_suffix}")

    def get_task_completion_stats(self) -> tuple[int, int, float]:
        data = global_data or {}
        tasks_dict = data.get("today_structured_tasks", {})
        total = sum(len(items) for items in tasks_dict.values() if isinstance(items, list))
        done = 0
        for items in tasks_dict.values():
            if not isinstance(items, list):
                continue
            for t in items:
                if isinstance(t, dict) and t.get("done"):
                    done += 1
        if total == 0:
            return 0, 0, 0.0
        rate = done / total * 100
        return total, done, rate

    def get_penalty_by_rate(self, rate: float) -> int:
        if rate >= 60:
            return 0
        if rate >= 50:
            base = -20
        elif rate >= 40:
            base = -50
        elif rate >= 30:
            base = -90
        elif rate >= 20:
            base = -140
        else:
            base = -200
        return int(round(base * PENALTY_MULTIPLIER))

    def update_task_status_label(self) -> None:
        data = global_data or {}
        tasks_dict = data.get("today_structured_tasks", {})
        total_tasks = sum(len(items) for items in tasks_dict.values() if isinstance(items, list))
        done_tasks = 0
        for items in tasks_dict.values():
            if not isinstance(items, list):
                continue
            done_tasks += sum(1 for t in items if isinstance(t, dict) and t.get("done"))

        if total_tasks == 0:
            self.task_status_label.setText("⚠️ 今日您还没有添加任务！")
            self.task_status_label.setStyleSheet("color:#FF6347")
            self.penalty_hint_label.setText("📌 未设定任务，暂无扣分")
            return

        if done_tasks == total_tasks:
            self.task_status_label.setText("🎉 真棒！！今日任务全部完成")
            self.task_status_label.setStyleSheet("color:#32CD32")
        else:
            self.task_status_label.setText(f"🔥 今日还有 {total_tasks - done_tasks} 个任务未完成")
            self.task_status_label.setStyleSheet("color:#FFFFE0")

        rate = (done_tasks / total_tasks) * 100
        penalty = self.get_penalty_by_rate(rate)
        if penalty < 0:
            self.penalty_hint_label.setText(f"⚠️ 当前完成率 {rate:.0f}%，若保持将扣 {abs(penalty)} 分")
        else:
            self.penalty_hint_label.setText(f"✅ 当前完成率 {rate:.0f}%，无扣分")

    def format_minutes(self, minutes: float) -> str:
        mins = int(round(minutes))
        if mins < 60:
            return f"{mins}min"
        h, m = divmod(mins, 60)
        return f"{h}h{m}min"

    def get_today_point_exchange_count(self) -> int:
        today_str = datetime.now().strftime("%Y-%m-%d")
        data = global_data or {}
        return sum(
            1
            for item in data.get("exchange_history", [])
            if isinstance(item, dict)
            and item.get("used_points", 0) > 0
            and str(item.get("date", "")).startswith(today_str)
        )

    def update_dashboard(self) -> None:
        data = global_data or {}
        pts = int(data.get("total_points", 0) or 0)

        monthly_prefix = datetime.now().strftime("%Y-%m")
        monthly_tomatoes = sum(
            1
            for item in data.get("study_history", [])
            if isinstance(item, dict) and str(item.get("date", "")).startswith(monthly_prefix)
        )

        bonus = (monthly_tomatoes // 40) * 5
        rate = 25 + bonus
        cost_per_minute = 100 / rate if rate else 0

        today_ex = self.get_today_point_exchange_count()
        incentive_pool = int(data.get("today_incentive_pool", 0) or 0)

        point_time = int(pts / cost_per_minute) if cost_per_minute > 0 else 0
        today_playable = point_time + incentive_pool

        self.points_label.setText(f"总积分: {pts}")
        self.games_label.setText(
            f"✨ 今日还有多少时间改变自己: {today_playable} 分钟 | "
            f"积分可换: {point_time} 分钟 ({cost_per_minute:.1f}分/分钟) | 激励池: {incentive_pool} 分钟"
        )

        remaining = 40 - (monthly_tomatoes % 40)
        self.discount_info_label.setText(
            f"📌 本月累计番茄: {monthly_tomatoes} 个 | 再专注 {remaining} 个，比例提升 5 分！(当前兑换比: 100分换{rate}分)"
        )

    def update_task_buttons(self) -> None:
        data = global_data or {}
        submitted = bool(data.get("today_task_submitted"))

        # Clear tasks_block layout
        while self.tasks_block_layout.count():
            item = self.tasks_block_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        if submitted:
            row = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            lay.addWidget(self.btn_view_task)
            lay.addWidget(self.btn_review_task)
            self.tasks_block_layout.addWidget(row)
        else:
            self.tasks_block_layout.addWidget(self.btn_daily_task)

    # ------------------- actions -------------------

    def change_data_directory(self) -> None:
        self.apply_storage_directory()
