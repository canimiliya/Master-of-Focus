"""Qt dialog widgets used by the main window."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass
class FocusTask:
    cat: str
    text: str


class TaskSelectDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, tasks: list[FocusTask]):
        super().__init__(parent)
        self.setWindowTitle("🎯 选择专注任务")
        self.setModal(True)
        self._tasks = tasks
        self.selected_task: FocusTask | None = None

        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("请选择本次番茄钟要执行的任务：")
        title.setFont(self._font(size=10, bold=True))
        layout.addWidget(title)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        for t in tasks:
            self.list_widget.addItem(f"[{t.cat}] {t.text}")
        if tasks:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        self.selected_label = QtWidgets.QLabel("")
        self.selected_label.setWordWrap(True)
        self.selected_label.setStyleSheet("color:#666666")
        layout.addWidget(self.selected_label)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        ok_btn = QtWidgets.QPushButton("开始倒计时")
        ok_btn.setDefault(True)
        cancel_btn = QtWidgets.QPushButton("取消")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

        self.list_widget.currentRowChanged.connect(self._sync_selected)
        ok_btn.clicked.connect(self._accept)
        cancel_btn.clicked.connect(self.reject)

        self._sync_selected()

    @staticmethod
    def _font(size: int, bold: bool = False) -> QtGui.QFont:
        f = QtGui.QFont("Microsoft YaHei")
        f.setPointSize(size)
        f.setBold(bold)
        return f

    def _sync_selected(self) -> None:
        idx = self.list_widget.currentRow()
        if idx < 0 or idx >= len(self._tasks):
            self.selected_label.setText("")
            return
        t = self._tasks[idx]
        self.selected_label.setText(f"[{t.cat}] {t.text}")

    def _accept(self) -> None:
        idx = self.list_widget.currentRow()
        if idx < 0 or idx >= len(self._tasks):
            return
        self.selected_task = self._tasks[idx]
        self.accept()
