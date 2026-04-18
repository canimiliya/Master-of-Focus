from __future__ import annotations
from datetime import datetime
import random

from PySide6 import QtCore, QtWidgets

from sgp_qt_core import global_data, save_data


class ExchangeMixin:
    def open_exchange_shop(self) -> None:
        shop = QtWidgets.QDialog(self)
        shop.setWindowTitle("🎮 兑换商店")
        shop.resize(360, 240)
        shop.setModal(True)

        root = QtWidgets.QVBoxLayout(shop)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QtWidgets.QLabel("请选择兑换方式")
        title.setFont(self._font(size=11, bold=True))
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(title)

        btn_points = QtWidgets.QPushButton("🎮 兑换【改变自己】时间")
        btn_incentive = QtWidgets.QPushButton("⭐ 激励计划")
        btn_close = QtWidgets.QPushButton("关闭")
        for b in (btn_points, btn_incentive):
            b.setMinimumHeight(40)
            b.setFont(self._font(size=10, bold=True))
        btn_close.setMinimumHeight(34)
        root.addWidget(btn_points)
        root.addWidget(btn_incentive)
        root.addStretch(1)
        root.addWidget(btn_close)

        btn_points.clicked.connect(lambda: self.exchange_points(parent=shop))
        btn_incentive.clicked.connect(lambda: self.open_incentive_plan(parent=shop))
        btn_close.clicked.connect(shop.accept)

        shop.exec()

    def open_incentive_plan(self, parent: QtWidgets.QWidget | None = None) -> None:
        dialog = QtWidgets.QDialog(parent or self)
        dialog.setWindowTitle("⭐ 激励计划")
        dialog.resize(460, 320)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(10)

        header = QtWidgets.QLabel("选择激励选项领取奖励")
        header.setFont(self._font(size=10, bold=True))
        root.addWidget(header)

        pool_label = QtWidgets.QLabel("")
        pool_label.setStyleSheet("color:#555555")
        root.addWidget(pool_label)

        btn_night = QtWidgets.QPushButton("前一天晚上没有带手机上床且醒了立即下床")
        btn_noon = QtWidgets.QPushButton("中午没有带手机上床且醒了立即下床")
        btn_redeem = QtWidgets.QPushButton("兑换激励分钟 (改变自己)")
        for b in (btn_night, btn_noon, btn_redeem):
            b.setMinimumHeight(36)
            b.setFont(self._font(size=9, bold=True))
            b.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        root.addWidget(btn_night)
        root.addWidget(btn_noon)
        root.addWidget(btn_redeem)
        root.addStretch(1)

        def refresh_state() -> None:
            data = global_data or {}
            today_str = datetime.now().strftime("%Y-%m-%d")
            claims = data.get("incentive_claims", {}) if isinstance(data.get("incentive_claims"), dict) else {}
            night_claimed = claims.get("night") == today_str
            noon_claimed = claims.get("noon") == today_str
            pool = int(data.get("today_incentive_pool", 0) or 0)

            pool_label.setText(f"当前激励可兑换: {pool} 分钟 (改变自己)")
            btn_night.setEnabled(not night_claimed)
            btn_noon.setEnabled(not noon_claimed)
            btn_redeem.setEnabled(pool > 0)

        def claim_night() -> None:
            data = global_data
            if data is None:
                return
            today_str = datetime.now().strftime("%Y-%m-%d")
            claims = data.get("incentive_claims", {}) if isinstance(data.get("incentive_claims"), dict) else {}
            if claims.get("night") == today_str:
                return
            reward = random.randint(1, 2)
            data["today_incentive_pool"] = int(data.get("today_incentive_pool", 0) or 0) + reward
            claims["night"] = today_str
            data["incentive_claims"] = claims
            save_data()
            QtWidgets.QMessageBox.information(dialog, "激励奖励", f"抽中 {reward} 分钟【改变自己】时间，已加入可兑换池。")
            refresh_state()
            self.update_dashboard()

        def claim_noon() -> None:
            data = global_data
            if data is None:
                return
            today_str = datetime.now().strftime("%Y-%m-%d")
            claims = data.get("incentive_claims", {}) if isinstance(data.get("incentive_claims"), dict) else {}
            if claims.get("noon") == today_str:
                return
            reward = 1
            data["today_incentive_pool"] = int(data.get("today_incentive_pool", 0) or 0) + reward
            claims["noon"] = today_str
            data["incentive_claims"] = claims
            save_data()
            QtWidgets.QMessageBox.information(dialog, "激励奖励", "获得 1 分钟【改变自己】时间，已加入可兑换池。")
            refresh_state()
            self.update_dashboard()

        def redeem_incentive() -> None:
            data = global_data
            if data is None:
                return
            pool = int(data.get("today_incentive_pool", 0) or 0)
            if pool <= 0:
                return
            count = 1
            if pool > 1:
                count, ok = QtWidgets.QInputDialog.getInt(
                    dialog,
                    "兑换激励分钟 (改变自己)",
                    f"当前可兑换 {pool} 分钟 (改变自己)，想兑换几分钟 (改变自己)？",
                    1,
                    1,
                    pool,
                )
                if not ok:
                    return

            ans = QtWidgets.QMessageBox.question(dialog, "兑换确认", f"确定兑换 {count} 分钟【改变自己】时间吗？")
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            data["today_exchanged_time"] = int(data.get("today_exchanged_time", 0) or 0) + count
            data.setdefault("exchange_history", [])
            for _ in range(count):
                data["exchange_history"].append(
                    {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "exchange_time": 1,
                        "used_points": 0,
                        "source": "incentive",
                    }
                )
            data["today_incentive_pool"] = pool - count
            save_data()
            self.update_dashboard()
            QtWidgets.QMessageBox.information(dialog, "兑换成功", f"已兑换 {count} 分钟【改变自己】时间。")
            refresh_state()

        btn_night.clicked.connect(claim_night)
        btn_noon.clicked.connect(claim_noon)
        btn_redeem.clicked.connect(redeem_incentive)
        refresh_state()
        dialog.exec()

    def exchange_points(self, parent: QtWidgets.QWidget | None = None) -> None:
        data = global_data
        if data is None:
            return
        if not data.get("today_task_submitted"):
            QtWidgets.QMessageBox.warning(parent or self, "拦截", "请先提交今天的任务清单！")
            return

        monthly_prefix = datetime.now().strftime("%Y-%m")
        monthly_tomatoes = sum(
            1
            for item in data.get("study_history", [])
            if isinstance(item, dict) and str(item.get("date", "")).startswith(monthly_prefix)
        )
        bonus = (monthly_tomatoes // 40) * 5
        rate = 25 + bonus
        cost_per_minute = 100 / rate

        pts = int(data.get("total_points", 0) or 0)
        max_mins = int(pts / cost_per_minute) if cost_per_minute > 0 else 0
        if max_mins < 1:
            QtWidgets.QMessageBox.warning(parent or self, "积分不足", f"换1分钟【改变自己】时间需要 {cost_per_minute:.1f} 积分，先去赚积分吧！")
            return

        count, ok = QtWidgets.QInputDialog.getInt(
            parent or self,
            "兑换时间",
            f"当前积分可兑换最多 {max_mins} 分钟【改变自己】。\n你想兑换多少分钟？",
            1,
            1,
            max_mins,
        )
        if not ok or count <= 0:
            return
        total_cost = int(count * cost_per_minute)

        ans = QtWidgets.QMessageBox.question(parent or self, "兑换确认", f"确定消耗 {total_cost} 积分兑换 {count} 分钟【改变自己】时间吗？")
        if ans != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        data["total_points"] = int(data.get("total_points", 0) or 0) - total_cost
        data["today_exchanged_time"] = int(data.get("today_exchanged_time", 0) or 0) + count
        data.setdefault("exchange_history", []).append(
            {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exchange_time": count,
                "used_points": total_cost,
                "source": "points",
            }
        )
        save_data()
        self.update_dashboard()
        QtWidgets.QMessageBox.information(parent or self, "兑换成功", f"成功消耗 {total_cost} 积分，兑换了 {count} 分钟！")

    # ===================== windows: memo / work log =====================
