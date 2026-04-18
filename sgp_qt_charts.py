from __future__ import annotations
from datetime import datetime, timedelta

from PySide6 import QtCore, QtWidgets

from sgp_qt_core import global_data


class ChartsMixin:
    def split_duration_by_day(self, start_dt: datetime, duration_mins: int) -> list[tuple[datetime, int]]:
        segments: list[tuple[datetime, int]] = []
        curr_dt = start_dt
        mins_left = int(duration_mins)
        while mins_left > 0:
            next_day = (curr_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            mins_in_day = int((next_day - curr_dt).total_seconds() / 60)
            if mins_left <= mins_in_day:
                segments.append((curr_dt, mins_left))
                break
            segments.append((curr_dt, mins_in_day))
            mins_left -= mins_in_day
            curr_dt = next_day
        return segments

    def split_time_to_bins(self, start_dt: datetime, duration_mins: int) -> list[int]:
        bins = [0] * 24
        curr_dt = start_dt
        mins_left = int(duration_mins)
        while mins_left > 0:
            hour = curr_dt.hour
            mins_in_curr_hour = 60 - curr_dt.minute
            if mins_left <= mins_in_curr_hour:
                bins[hour] += mins_left
                break
            bins[hour] += mins_in_curr_hour
            mins_left -= mins_in_curr_hour
            curr_dt = (curr_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return bins

    def get_daily_minutes_for_study(self, target_date_str: str) -> int:
        data = global_data or {}
        total = 0
        for item in data.get("study_history", []) if isinstance(data.get("study_history"), list) else []:
            if not isinstance(item, dict):
                continue
            try:
                end_dt = datetime.strptime(str(item.get("date")), "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            duration = int(item.get("study_time", item.get("duration", 0)) or 0)
            start_dt = end_dt - timedelta(minutes=duration)
            for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                if seg_start.strftime("%Y-%m-%d") == target_date_str:
                    total += seg_mins
        return total

    def get_daily_minutes_for_exchange(self, target_date_str: str) -> int:
        data = global_data or {}
        total = 0
        for item in data.get("exchange_history", []) if isinstance(data.get("exchange_history"), list) else []:
            if not isinstance(item, dict):
                continue
            try:
                start_dt = datetime.strptime(str(item.get("date")), "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            duration = int(item.get("exchange_time", 0) or 0)
            for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                if seg_start.strftime("%Y-%m-%d") == target_date_str:
                    total += seg_mins
        return total

    def show_charts_window(self) -> None:
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            import matplotlib
            import matplotlib.gridspec as gridspec
            from matplotlib.ticker import FuncFormatter
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "缺少依赖", f"无法打开图表窗口: {e}")
            return

        # Ensure Chinese text can be rendered in Matplotlib on Windows.
        # (Matplotlib default font often lacks CJK glyphs.)
        try:
            candidates = [
                "Microsoft YaHei",
                "SimHei",
                "Noto Sans CJK SC",
                "Source Han Sans CN",
                "Arial Unicode MS",
            ]
            existing = matplotlib.rcParams.get("font.sans-serif", [])
            merged: list[str] = []
            if isinstance(existing, (list, tuple)):
                base_list = list(candidates) + list(existing)
            else:
                base_list = list(candidates)
            for name in base_list:
                if name and name not in merged:
                    merged.append(name)
            matplotlib.rcParams["font.sans-serif"] = merged
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["axes.unicode_minus"] = False
        except Exception:
            pass

        chart_win = QtWidgets.QDialog(self)
        chart_win.setWindowTitle("📊 学习与改变自己时间看板")
        chart_win.resize(980, 880)
        chart_win.setModal(False)

        data = global_data or {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_study_minutes = self.get_daily_minutes_for_study(today_str)
        today_exchange_minutes = self.get_daily_minutes_for_exchange(today_str)
        study_display = self.format_minutes(today_study_minutes)

        info_text = (
            f"🏅 今日完成番茄: {int(data.get('today_tomatoes', 0) or 0)} 个   |   "
            f"⏱️ 今日专注: {study_display}   |   "
            f"🎮 今日兑换: {today_exchange_minutes} 分钟   |   "
            f"📅 连续打卡: {int(data.get('continuous_checkin_days', 1) or 1)} 天"
        )

        root = QtWidgets.QVBoxLayout(chart_win)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        info_label = QtWidgets.QLabel(info_text)
        info_label.setFont(self._font(size=12, bold=True))
        info_label.setStyleSheet("background:#f0f0f0;padding:10px;")
        root.addWidget(info_label)

        filter_frame = QtWidgets.QWidget()
        filter_frame.setStyleSheet("background:#E6E6FA;")
        filter_lay = QtWidgets.QHBoxLayout(filter_frame)
        filter_lay.setContentsMargins(10, 8, 10, 8)
        filter_lay.setSpacing(8)
        root.addWidget(filter_frame)

        filter_lay.addWidget(QtWidgets.QLabel("📅 图表范围筛选:"))

        preset = QtWidgets.QComboBox()
        preset.addItems(["今日", "最近一周", "最近一月", "全部记录", "自定义范围"])
        filter_lay.addWidget(preset)

        start_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        start_date.setCalendarPopup(True)
        end_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        end_date.setCalendarPopup(True)
        filter_lay.addWidget(QtWidgets.QLabel("开始:"))
        filter_lay.addWidget(start_date)
        filter_lay.addWidget(QtWidgets.QLabel("结束:"))
        filter_lay.addWidget(end_date)

        refresh_btn = QtWidgets.QPushButton("🔄 刷新生成图表")
        filter_lay.addWidget(refresh_btn)
        filter_lay.addStretch(1)

        fig = Figure(figsize=(10, 9), facecolor="white")
        canvas = FigureCanvas(fig)
        root.addWidget(canvas, 1)
        gs = gridspec.GridSpec(2, 2, height_ratios=[1, 1], figure=fig)

        def set_range_by_preset() -> None:
            now = datetime.now()
            val = preset.currentText()
            if val == "自定义范围":
                start_date.setEnabled(True)
                end_date.setEnabled(True)
                return

            start_date.setEnabled(False)
            end_date.setEnabled(False)

            if val == "今日":
                start_dt = now
                end_dt = now
            elif val == "最近一周":
                start_dt = now - timedelta(days=6)
                end_dt = now
            elif val == "最近一月":
                start_dt = now - timedelta(days=29)
                end_dt = now
            else:  # 全部记录
                earliest = now
                if data.get("first_use_date"):
                    try:
                        earliest = datetime.strptime(str(data.get("first_use_date")), "%Y-%m-%d")
                    except Exception:
                        earliest = now
                start_dt = earliest
                end_dt = now

            start_date.setDate(QtCore.QDate(start_dt.year, start_dt.month, start_dt.day))
            end_date.setDate(QtCore.QDate(end_dt.year, end_dt.month, end_dt.day))

        def update_charts() -> None:
            start_qd = start_date.date()
            end_qd = end_date.date()
            if end_qd < start_qd:
                QtWidgets.QMessageBox.warning(chart_win, "范围错误", "结束日期不能早于开始日期。")
                return

            start_str = start_qd.toString("yyyy-MM-dd")
            end_str = end_qd.toString("yyyy-MM-dd")

            hours_bins: dict[str, list[int]] = {"科研": [0] * 24, "理论/技术": [0] * 24, "改变自己": [0] * 24}
            totals: dict[str, int] = {"科研": 0, "理论/技术": 0, "改变自己": 0}

            for item in data.get("study_history", []) if isinstance(data.get("study_history"), list) else []:
                if not isinstance(item, dict):
                    continue
                cat = item.get("category", "")
                if cat not in ("科研", "理论/技术"):
                    continue
                dt_str = str(item.get("date", "") or "")
                try:
                    end_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                duration = int(item.get("study_time", item.get("duration", 0)) or 0)
                start_dt = end_dt - timedelta(minutes=duration)

                for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                    seg_date = seg_start.strftime("%Y-%m-%d")
                    if start_str <= seg_date <= end_str:
                        bins = self.split_time_to_bins(seg_start, seg_mins)
                        for h, val in enumerate(bins):
                            hours_bins[cat][h] += val
                        totals[cat] += seg_mins

            for item in data.get("exchange_history", []) if isinstance(data.get("exchange_history"), list) else []:
                if not isinstance(item, dict):
                    continue
                dt_str = str(item.get("date", "") or "")
                try:
                    start_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                duration = int(item.get("exchange_time", 0) or 0)
                for seg_start, seg_mins in self.split_duration_by_day(start_dt, duration):
                    seg_date = seg_start.strftime("%Y-%m-%d")
                    if start_str <= seg_date <= end_str:
                        bins = self.split_time_to_bins(seg_start, seg_mins)
                        for h, val in enumerate(bins):
                            hours_bins["改变自己"][h] += val
                        totals["改变自己"] += seg_mins

            fig.clf()
            colors = {"科研": "#87CEFA", "理论/技术": "#98FB98", "改变自己": "#FF69B4"}

            ax1 = fig.add_subplot(gs[0, :])
            x = list(range(24))
            width = 0.4

            bottom_study = [0] * 24
            for cat in ("科研", "理论/技术"):
                arr = hours_bins[cat]
                ax1.bar([i - width / 2 for i in x], arr, width, label=cat, bottom=bottom_study, color=colors[cat], edgecolor="white")
                bottom_study = [bottom_study[i] + arr[i] for i in range(24)]

            arr_game = hours_bins["改变自己"]
            ax1.bar([i + width / 2 for i in x], arr_game, width, label="改变自己", color=colors["改变自己"], edgecolor="white")

            for i in range(24):
                if bottom_study[i] > 0:
                    ax1.text(i - width / 2, bottom_study[i] + 0.5, f"{int(bottom_study[i])}", ha="center", va="bottom", fontsize=8)
                if arr_game[i] > 0:
                    ax1.text(i + width / 2, arr_game[i] + 0.5, f"{int(arr_game[i])}", ha="center", va="bottom", fontsize=8)

            max_val = max(max(bottom_study) if bottom_study else 0, max(arr_game) if arr_game else 0)
            if max_val > 180:
                ax1.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y/60:.1f}h"))
                ax1.set_ylabel("时间 (小时)")
            else:
                ax1.set_ylabel("时间 (分钟)")
            ax1.set_ylim(0, max_val + (max_val * 0.15 + 5))

            title_str = "所选范围内" if start_str != end_str else "今日"
            ax1.set_title(f"【{title_str}】24小时时间分布图", fontsize=12, fontweight="bold")
            ax1.set_xticks(x)
            ax1.set_xticklabels([f"{i}-{i+1}" for i in x], rotation=45, ha="right", fontsize=9)
            ax1.legend(loc="upper right")

            ax2 = fig.add_subplot(gs[1, 0])
            pie_labels: list[str] = []
            pie_sizes: list[int] = []
            pie_colors: list[str] = []
            for cat, val in totals.items():
                if val > 0:
                    pie_labels.append(cat)
                    pie_sizes.append(val)
                    pie_colors.append(colors[cat])

            def absolute_value_autopct(val: float) -> str:
                total = sum(pie_sizes) or 1
                a = int(round(val * total / 100.0))
                h, m = divmod(a, 60)
                if h > 0:
                    return f"{h}h{m}min\n({val:.1f}%)"
                return f"{m}min\n({val:.1f}%)"

            if not pie_sizes:
                ax2.text(0.5, 0.5, "暂无记录", ha="center", va="center")
                ax2.axis("off")
            else:
                ax2.pie(pie_sizes, labels=pie_labels, colors=pie_colors, autopct=absolute_value_autopct, startangle=90, textprops={"fontsize": 10})
            total_minutes = sum(totals.values())
            ax2.set_title(f"【{title_str}】任务类型耗时分布 (总计 {self.format_minutes(total_minutes)})", fontsize=11)

            ax3 = fig.add_subplot(gs[1, 1])
            history = data.get("daily_rewards_history", [])
            filtered = [item for item in history if isinstance(item, dict) and start_str <= str(item.get("date", "")) <= end_str]
            if not filtered:
                ax3.text(0.5, 0.5, "暂无完成率/奖惩记录", ha="center", va="center")
                ax3.axis("off")
            else:
                filtered = sorted(filtered, key=lambda x: str(x.get("date", "")))
                dates = [str(item.get("date", ""))[-5:] for item in filtered]
                rates = [float(item.get("rate", 0) or 0) for item in filtered]
                rewards = [float(item.get("reward", 0) or 0) for item in filtered]

                ax3.plot(dates, rates, marker="o", color="#1E90FF", linewidth=2, label="完成率(%)")
                ax3.set_ylim(0, 100)
                ax3.set_ylabel("完成率(%)")
                ax3.set_title("完成率与完成奖惩趋势", fontsize=11)
                ax3.grid(True, linestyle="--", alpha=0.6)

                ax3b = ax3.twinx()
                ax3b.plot(dates, rewards, marker="s", color="#FF8C00", linewidth=2, label="完成奖惩(分)")
                ax3b.set_ylabel("完成奖惩(分)")
                for tick in ax3.get_xticklabels():
                    tick.set_rotation(45)

                h1, l1 = ax3.get_legend_handles_labels()
                h2, l2 = ax3b.get_legend_handles_labels()
                ax3.legend(h1 + h2, l1 + l2, loc="upper right")

            fig.tight_layout()
            canvas.draw()

        preset.currentTextChanged.connect(lambda _=None: set_range_by_preset())
        refresh_btn.clicked.connect(update_charts)
        preset.setCurrentText("今日")
        set_range_by_preset()
        update_charts()

        chart_win.show()

    # ------------------- close -------------------
