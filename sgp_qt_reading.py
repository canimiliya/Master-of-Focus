from __future__ import annotations
from datetime import datetime
from typing import Any
import json
import os
import tempfile

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import app_config, calculate_book_pages, compute_read_pages_from_tree, global_data, save_data, save_app_config
from sgp_qt_api import (
    ApiError,
    classify_file,
    is_api_configured,
    smart_import_book,
    smart_import_paper,
)
from sgp_qt_prompts import DEFAULT_BOOK_JSON_PROMPT, DEFAULT_PAPER_JSON_PROMPT


class _CandyProgressBar(QtWidgets.QProgressBar):
    def __init__(self, tone: int = 0, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._tone = int(tone)
        self.setTextVisible(False)
        self.setRange(0, 100)

    def set_tone(self, tone: int) -> None:
        self._tone = int(tone)
        self.update()

    def _tone_colors(self) -> tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor]:
        # (light, mid, strong)
        if self._tone == 1:
            return (QtGui.QColor("#FFEDD5"), QtGui.QColor("#FDBA74"), QtGui.QColor("#F97316"))
        if self._tone == 2:
            return (QtGui.QColor("#DCFCE7"), QtGui.QColor("#86EFAC"), QtGui.QColor("#22C55E"))
        if self._tone == 3:
            return (QtGui.QColor("#FCE7F3"), QtGui.QColor("#F9A8D4"), QtGui.QColor("#EC4899"))
        return (QtGui.QColor("#E0F2FE"), QtGui.QColor("#93C5FD"), QtGui.QColor("#3B82F6"))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = max(2.0, rect.height() / 2.0)

        # Background
        bg = QtGui.QColor(255, 255, 255, 235)
        border = QtGui.QColor("#D0D7DE")
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, bg)

        # Fill with a full-bar anchored gradient, clipped to current progress width.
        rng = max(1, int(self.maximum() - self.minimum()))
        frac = float(int(self.value() - self.minimum())) / float(rng)
        frac = 0.0 if frac < 0 else 1.0 if frac > 1 else frac
        if frac > 0:
            fill_rect = QtCore.QRectF(rect)
            fill_rect.setWidth(rect.width() * frac)

            c0, c1, c2 = self._tone_colors()
            grad = QtGui.QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
            grad.setColorAt(0.0, c0)
            grad.setColorAt(0.55, c1)
            grad.setColorAt(1.0, c2)

            painter.save()
            painter.setClipPath(path)
            painter.setClipRect(fill_rect)
            painter.fillRect(rect, grad)

            # Subtle glossy highlight for a "candy" feel.
            gloss = QtGui.QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
            gloss.setColorAt(0.0, QtGui.QColor(255, 255, 255, 110))
            gloss.setColorAt(0.45, QtGui.QColor(255, 255, 255, 30))
            gloss.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
            painter.fillRect(rect, gloss)
            painter.restore()

        # Border on top.
        pen = QtGui.QPen(border)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)


class _LiteratureProgressBar(_CandyProgressBar):
    def _tone_colors(self) -> tuple[QtGui.QColor, QtGui.QColor, QtGui.QColor]:
        # Deeper blues as the phase advances.
        if self._tone == 1:
            return (QtGui.QColor("#BAE6FD"), QtGui.QColor("#38BDF8"), QtGui.QColor("#0EA5E9"))
        if self._tone >= 2:
            return (QtGui.QColor("#7DD3FC"), QtGui.QColor("#0EA5E9"), QtGui.QColor("#0284C7"))
        return (QtGui.QColor("#E0F2FE"), QtGui.QColor("#7DD3FC"), QtGui.QColor("#38BDF8"))


class StepProgressDialog(QtWidgets.QDialog):
    _DONE = "\u2713"
    _BUSY = "\u27f3"
    _TODO = "\u25cb"

    def __init__(self, title: str, steps: list[str], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMinimumHeight(350)
        self._steps = steps
        self._current = -1
        self._cancelled = False
        self._step_labels: list[QtWidgets.QLabel] = []
        self._step_icons: list[QtWidgets.QLabel] = []
        self._streaming_shown = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 12)
        root.setSpacing(6)

        for i, text in enumerate(self._steps):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(10)

            icon_lbl = QtWidgets.QLabel(self._TODO)
            icon_lbl.setFixedWidth(24)
            icon_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            font = icon_lbl.font()
            font.setPointSize(13)
            icon_lbl.setFont(font)
            icon_lbl.setStyleSheet("color:#9CA3AF;")
            self._step_icons.append(icon_lbl)

            lbl = QtWidgets.QLabel(text)
            lbl.setStyleSheet("color:#9CA3AF; font-size:13px;")
            self._step_labels.append(lbl)

            row.addWidget(icon_lbl)
            row.addWidget(lbl, 1)
            root.addLayout(row)

        root.addSpacing(8)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setRange(0, len(self._steps))
        self._bar.setValue(0)
        self._bar.setMaximumHeight(4)
        self._bar.setStyleSheet(
            "QProgressBar { border: none; background-color: #E5E7EB; border-radius: 2px; }"
            "QProgressBar::chunk { background-color: #3B82F6; border-radius: 2px; }"
        )
        root.addWidget(self._bar)

        self._stream_box = QtWidgets.QTextEdit()
        self._stream_box.setReadOnly(True)
        self._stream_box.setMaximumHeight(200)
        self._stream_box.setVisible(False)
        self._stream_box.setStyleSheet(
            "QTextEdit {"
            "  background-color: #F9FAFB;"
            "  border: 1px solid #E5E7EB;"
            "  border-radius: 6px;"
            "  padding: 8px;"
            "  font-family: 'Consolas', 'Microsoft YaHei', monospace;"
            "  font-size: 12px;"
            "  color: #374151;"
            "}"
        )
        root.addWidget(self._stream_box)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self._cancel_btn = QtWidgets.QPushButton("\u53d6\u6d88")
        self._cancel_btn.setFixedWidth(70)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

    def advance_to(self, step_index: int, detail: str = "") -> None:
        if step_index < 0 or step_index >= len(self._steps) or self._cancelled:
            return
        is_streaming_step = (
            step_index == self._current
            and step_index >= 0
            and detail
            and len(detail) > 30
        )
        if is_streaming_step:
            self._show_streaming(detail)
            return
        for i in range(len(self._steps)):
            if i < step_index:
                self._step_icons[i].setText(self._DONE)
                self._step_icons[i].setStyleSheet("color:#10B981; font-size:13px;")
                self._step_labels[i].setStyleSheet("color:#374151; font-size:13px;")
            elif i == step_index:
                self._step_icons[i].setText(self._BUSY)
                self._step_icons[i].setStyleSheet("color:#3B82F6; font-size:13px;")
                if detail:
                    self._step_labels[i].setText(f"{self._steps[i]} \u2014 {detail}")
                else:
                    self._step_labels[i].setText(self._steps[i])
                self._step_labels[i].setStyleSheet("color:#1D4ED8; font-weight:bold; font-size:13px;")
            else:
                self._step_icons[i].setText(self._TODO)
                self._step_icons[i].setStyleSheet("color:#9CA3AF; font-size:13px;")
                self._step_labels[i].setText(self._steps[i])
                self._step_labels[i].setStyleSheet("color:#9CA3AF; font-size:13px;")
        self._current = step_index
        self._bar.setValue(step_index + 1)
        self.repaint()

    def _show_streaming(self, text: str) -> None:
        if not self._streaming_shown:
            self._streaming_shown = True
            self._stream_box.setVisible(True)
            self._step_labels[self._current].setText(
                f"{self._steps[self._current]} \u2014 AI 正在输出..."
            )
        self._stream_box.setPlainText(text)
        scrollbar = self._stream_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.repaint()

    def finish_success(self) -> None:
        total = len(self._steps)
        for i in range(total):
            self._step_icons[i].setText(self._DONE)
            self._step_icons[i].setStyleSheet("color:#10B981; font-size:13px;")
            self._step_labels[i].setStyleSheet("color:#374151; font-size:13px;")
        self._bar.setValue(total)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("\u5b8c\u6210")
        self.repaint()

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("\u53d6\u6d88\u4e2d...")


class ReadingMixin:
    def show_reading_json_prompt_help(self) -> None:
        parent = self.reading_window or self

        prompt_text = app_config.get("reading_book_prompt", "") or DEFAULT_BOOK_JSON_PROMPT

        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📚 目录截图 → JSON 操作说明")
        dialog.resize(720, 560)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        steps = QtWidgets.QLabel(
            '使用方法：\n'
            '1) 将书籍目录页截图（确保包含标题和页码，按目录顺序）。\n'
            '2) 把目录截图 + 下方提示词发给支持图片的推理大模型。\n'
            '3) 让它输出「纯 JSON 文本」，保存为 .json 文件。\n'
            '4) 回到本窗口：拖拽该 .json 到上方区域，或点击【选择 JSON 文件导入】。\n\n'
            '💡 快捷方式：直接拖拽目录截图或 PDF 到上方区域，软件会自动调用 API 识别！'
        )
        steps.setWordWrap(True)
        root.addWidget(steps)

        status_label = QtWidgets.QLabel("提示：点击【复制提示词】后直接粘贴到大模型对话框即可。也可直接拖入图片使用智能导入。")
        status_label.setStyleSheet("color:#666666")
        status_label.setWordWrap(True)
        root.addWidget(status_label)

        edit = QtWidgets.QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(prompt_text)
        root.addWidget(edit, 1)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btn_edit = QtWidgets.QPushButton("修改提示词")
        btn_copy = QtWidgets.QPushButton("复制提示词")
        btn_close = QtWidgets.QPushButton("关闭")
        btns.addWidget(btn_edit)
        btns.addWidget(btn_copy)
        btns.addWidget(btn_close)
        root.addLayout(btns)

        prompt_holder = [prompt_text]

        def copy_prompt() -> None:
            QtWidgets.QApplication.clipboard().setText(prompt_holder[0])
            status_label.setText("提示词已复制到剪贴板。")

        def edit_prompt() -> None:
            edit_dlg = QtWidgets.QDialog(dialog)
            edit_dlg.setWindowTitle("修改提示词")
            edit_dlg.resize(720, 560)
            edit_dlg.setModal(True)

            edit_root = QtWidgets.QVBoxLayout(edit_dlg)
            edit_root.setContentsMargins(12, 12, 12, 12)
            edit_root.setSpacing(8)

            hint = QtWidgets.QLabel("修改下方提示词后点击「保存」，留空则恢复默认提示词。")
            hint.setStyleSheet("color:#666666")
            hint.setWordWrap(True)
            edit_root.addWidget(hint)

            text_edit = QtWidgets.QTextEdit()
            text_edit.setPlainText(prompt_holder[0])
            edit_root.addWidget(text_edit, 1)

            edit_btns = QtWidgets.QHBoxLayout()
            edit_btns.addStretch(1)
            btn_reset = QtWidgets.QPushButton("恢复默认")
            btn_save = QtWidgets.QPushButton("保存")
            btn_cancel = QtWidgets.QPushButton("取消")
            edit_btns.addWidget(btn_reset)
            edit_btns.addWidget(btn_save)
            edit_btns.addWidget(btn_cancel)
            edit_root.addLayout(edit_btns)

            def reset_default() -> None:
                text_edit.setPlainText(DEFAULT_BOOK_JSON_PROMPT)

            btn_reset.clicked.connect(reset_default)
            btn_save.clicked.connect(edit_dlg.accept)
            btn_cancel.clicked.connect(edit_dlg.reject)

            if edit_dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                new_text = text_edit.toPlainText()
                if new_text.strip() == DEFAULT_BOOK_JSON_PROMPT.strip() or not new_text.strip():
                    app_config.pop("reading_book_prompt", None)
                else:
                    app_config["reading_book_prompt"] = new_text
                save_app_config()
                prompt_holder[0] = new_text if new_text.strip() else DEFAULT_BOOK_JSON_PROMPT
                edit.setPlainText(prompt_holder[0])
                status_label.setText("提示词已保存。")

        btn_edit.clicked.connect(edit_prompt)
        btn_copy.clicked.connect(copy_prompt)
        btn_close.clicked.connect(dialog.accept)

        dialog.exec()

    def show_literature_json_prompt_help(self) -> None:
        parent = self.reading_window or self

        prompt_text = app_config.get("reading_paper_prompt", "") or DEFAULT_PAPER_JSON_PROMPT

        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📄 文献导读 → JSON 操作说明")
        dialog.resize(820, 720)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        steps = QtWidgets.QLabel(
            '使用方法：\n'
            '1) 准备论文全文或详细摘要文本。\n'
            '2) 把文本 + 下方提示词发给大模型。\n'
            '3) 让它输出「纯 JSON 文本」，保存为 .json 文件。\n'
            '4) 回到本窗口：拖拽该 .json 到上方区域，或点击【选择 JSON 文件导入】。\n\n'
            '💡 快捷方式：直接拖拽论文截图或 PDF 到上方区域，软件会自动调用 API 生成导读规划！'
        )
        steps.setWordWrap(True)
        root.addWidget(steps)

        status_label = QtWidgets.QLabel("提示：点击【复制提示词】后直接粘贴到大模型对话框即可。也可直接拖入图片/PDF使用智能导入。")
        status_label.setStyleSheet("color:#666666")
        status_label.setWordWrap(True)
        root.addWidget(status_label)

        edit = QtWidgets.QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(prompt_text)
        root.addWidget(edit, 1)


        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btn_edit = QtWidgets.QPushButton("修改提示词")
        btn_copy = QtWidgets.QPushButton("复制提示词")
        btn_close = QtWidgets.QPushButton("关闭")
        btns.addWidget(btn_edit)
        btns.addWidget(btn_copy)
        btns.addWidget(btn_close)
        root.addLayout(btns)

        prompt_holder = [prompt_text]

        def copy_prompt() -> None:
            QtWidgets.QApplication.clipboard().setText(prompt_holder[0])
            status_label.setText("提示词已复制到剪贴板。")

        def edit_prompt() -> None:
            edit_dlg = QtWidgets.QDialog(dialog)
            edit_dlg.setWindowTitle("修改提示词")
            edit_dlg.resize(820, 720)
            edit_dlg.setModal(True)

            edit_root = QtWidgets.QVBoxLayout(edit_dlg)
            edit_root.setContentsMargins(12, 12, 12, 12)
            edit_root.setSpacing(8)

            hint = QtWidgets.QLabel("修改下方提示词后点击「保存」，留空则恢复默认提示词。")
            hint.setStyleSheet("color:#666666")
            hint.setWordWrap(True)
            edit_root.addWidget(hint)

            text_edit = QtWidgets.QTextEdit()
            text_edit.setPlainText(prompt_holder[0])
            edit_root.addWidget(text_edit, 1)

            edit_btns = QtWidgets.QHBoxLayout()
            edit_btns.addStretch(1)
            btn_reset = QtWidgets.QPushButton("恢复默认")
            btn_save = QtWidgets.QPushButton("保存")
            btn_cancel = QtWidgets.QPushButton("取消")
            edit_btns.addWidget(btn_reset)
            edit_btns.addWidget(btn_save)
            edit_btns.addWidget(btn_cancel)
            edit_root.addLayout(edit_btns)

            def reset_default() -> None:
                text_edit.setPlainText(DEFAULT_PAPER_JSON_PROMPT)

            btn_reset.clicked.connect(reset_default)
            btn_save.clicked.connect(edit_dlg.accept)
            btn_cancel.clicked.connect(edit_dlg.reject)

            if edit_dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                new_text = text_edit.toPlainText()
                if new_text.strip() == DEFAULT_PAPER_JSON_PROMPT.strip() or not new_text.strip():
                    app_config.pop("reading_paper_prompt", None)
                else:
                    app_config["reading_paper_prompt"] = new_text
                save_app_config()
                prompt_holder[0] = new_text if new_text.strip() else DEFAULT_PAPER_JSON_PROMPT
                edit.setPlainText(prompt_holder[0])
                status_label.setText("提示词已保存。")

        btn_edit.clicked.connect(edit_prompt)
        btn_copy.clicked.connect(copy_prompt)
        btn_close.clicked.connect(dialog.accept)

        dialog.exec()

    def open_reading_library(self) -> None:
        if self.reading_window is not None:
            try:
                if self.reading_window.isVisible():
                    self.reading_window.raise_()
                    self.reading_window.activateWindow()
                    return
            except Exception:
                pass
            self.reading_window = None

        win = QtWidgets.QDialog(self)
        win.setWindowTitle("📚 阅读管理")
        win.resize(760, 620)
        win.setModal(False)
        win.setStyleSheet(
            """
            QDialog { background-color: #F5F7FB; }
            QScrollArea { border: none; }

            QPushButton {
                padding: 6px 10px;
                border: 1px solid #D0D7DE;
                border-radius: 8px;
                background-color: #FFFFFF;
            }
            QPushButton:hover { background-color: #F2F5FF; }
            QPushButton:pressed { background-color: #E8EEFF; }

            QLabel#ReadingDropArea {
                background-color: #EEF2FF;
                border: 1px dashed #93C5FD;
                border-radius: 10px;
                padding: 12px;
                color: #111827;
            }
            QLabel#ReadingEmptyHint { color: #4B5563; }

            QFrame#ReadingBookCard {
                background-color: #FFFFFF;
                border: 1px solid #D0D7DE;
                border-radius: 12px;
            }
            /* Stronger pastel tones for clearer separation */
            QFrame#ReadingBookCard[tone="0"] { background-color: #EFF6FF; border-color: #93C5FD; border-left: 10px solid #60A5FA; }
            QFrame#ReadingBookCard[tone="1"] { background-color: #FFEDD5; border-color: #FDBA74; border-left: 10px solid #FB923C; }
            QFrame#ReadingBookCard[tone="2"] { background-color: #DCFCE7; border-color: #86EFAC; border-left: 10px solid #34D399; }
            QFrame#ReadingBookCard[tone="3"] { background-color: #FCE7F3; border-color: #F9A8D4; border-left: 10px solid #F472B6; }
            QFrame#ReadingBookCard[complete="true"] { border: 2px solid #22C55E; }

            QFrame#LiteratureCard {
                background-color: #FFFFFF;
                border: 1px solid #D0D7DE;
                border-radius: 12px;
            }
            QFrame#LiteratureCard[tone="0"] { background-color: #ECFEFF; border-color: #67E8F9; border-left: 10px solid #22D3EE; }
            QFrame#LiteratureCard[tone="1"] { background-color: #FFF7ED; border-color: #FDBA74; border-left: 10px solid #FB923C; }
            QFrame#LiteratureCard[tone="2"] { background-color: #ECFCCB; border-color: #BEF264; border-left: 10px solid #84CC16; }
            QFrame#LiteratureCard[tone="3"] { background-color: #FCE7F3; border-color: #F9A8D4; border-left: 10px solid #F472B6; }

            QToolButton#ReadingBookHeader {
                padding: 6px 6px;
                border: none;
                text-align: left;
                font-weight: 600;
            }
            QToolButton#ReadingBookHeader:hover { background-color: rgba(59,130,246,0.10); border-radius: 6px; }
            QToolButton#ReadingBookHeader[tone="0"] { color: #1D4ED8; }
            QToolButton#ReadingBookHeader[tone="1"] { color: #9A3412; }
            QToolButton#ReadingBookHeader[tone="2"] { color: #166534; }
            QToolButton#ReadingBookHeader[tone="3"] { color: #9D174D; }

            QToolButton#LiteratureHeader {
                padding: 6px 6px;
                border: none;
                text-align: left;
                font-weight: 600;
            }
            QToolButton#LiteratureHeader:hover { background-color: rgba(59,130,246,0.10); border-radius: 6px; }
            QToolButton#LiteratureHeader[stage="0"] { color: #2563EB; }
            QToolButton#LiteratureHeader[stage="1"] { color: #1D4ED8; }
            QToolButton#LiteratureHeader[stage="2"] { color: #1E3A8A; }

            QLabel#LiteratureTitle { font-weight: 600; }
            QLabel#LiteratureTitle[stage="0"] { color: #2563EB; }
            QLabel#LiteratureTitle[stage="1"] { color: #1D4ED8; }
            QLabel#LiteratureTitle[stage="2"] { color: #1E3A8A; }
            QLabel#LiteratureMeta { color: #4B5563; }

            QLabel#LiteratureStatus[stage="0"] { color: #3B82F6; font-weight: 600; }
            QLabel#LiteratureStatus[stage="1"] { color: #2563EB; font-weight: 600; }
            QLabel#LiteratureStatus[stage="2"] { color: #1E3A8A; font-weight: 600; }

            QProgressBar { height: 14px; }

            QTreeWidget {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                alternate-background-color: #F9FAFB;
            }
            QTreeWidget::item { padding: 2px 4px; }
            QTreeWidget::item:alternate { background: #F9FAFB; }
            QTreeWidget::item:selected { background: #DBEAFE; color: #111827; }
            QHeaderView::section {
                background: #F3F4F6;
                padding: 4px 6px;
                border: none;
                border-bottom: 1px solid #E5E7EB;
                font-weight: 600;
            }
            """
        )
        self.reading_window = win

        def _on_finished(_code: int) -> None:
            if self.reading_window is win:
                self.reading_window = None
                self.reading_book_card_container = None
                self._reading_book_layout = None
                self._reading_book_scroll = None
                self.reading_paper_card_container = None
                self._reading_paper_layout = None
                self._reading_paper_scroll = None
                self._reading_card_margin_filter = None
                self.reading_tree_metas = {}

        win.finished.connect(_on_finished)

        root = QtWidgets.QVBoxLayout(win)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        class _FileDropLabel(QtWidgets.QLabel):
            def __init__(self, text: str, on_files):
                super().__init__(text)
                self._on_files = on_files
                self.setAcceptDrops(True)
                self.setObjectName("ReadingDropArea")
                self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.setMinimumHeight(46)

            def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()

            def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
                urls = event.mimeData().urls()
                paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
                if paths:
                    self._on_files(paths)
                event.acceptProposedAction()

        def import_book_paths(paths: list[str]) -> None:
            json_paths = []
            media_paths = []
            for file_path in paths:
                kind = classify_file(file_path)
                if kind == "json":
                    json_paths.append(file_path)
                elif kind in ("image", "pdf"):
                    media_paths.append(file_path)
                else:
                    ext = os.path.splitext(file_path)[1].lower()
                    QtWidgets.QMessageBox.warning(win, "格式错误", f"不支持的文件格式 ({ext})！")
            for fp in json_paths:
                self.open_book_import_dialog(fp)
            if media_paths:
                self._smart_import_book(media_paths)

        def import_paper_paths(paths: list[str]) -> None:
            json_paths = []
            media_paths = []
            for file_path in paths:
                kind = classify_file(file_path)
                if kind == "json":
                    json_paths.append(file_path)
                elif kind in ("image", "pdf"):
                    media_paths.append(file_path)
                else:
                    ext = os.path.splitext(file_path)[1].lower()
                    QtWidgets.QMessageBox.warning(win, "格式错误", f"不支持的文件格式 ({ext})！")
            for fp in json_paths:
                self.open_paper_import_dialog(fp)
            if media_paths:
                self._smart_import_paper(media_paths)

        tabs = QtWidgets.QTabWidget()
        root.addWidget(tabs, 1)

        book_tab = QtWidgets.QWidget()
        book_root = QtWidgets.QVBoxLayout(book_tab)
        book_root.setContentsMargins(0, 0, 0, 0)
        book_root.setSpacing(10)

        book_drop = _FileDropLabel("📥 拖拽 JSON / 图片 / PDF 到此处导入", import_book_paths)
        book_root.addWidget(book_drop)

        book_btn_row = QtWidgets.QHBoxLayout()
        btn_import_book = QtWidgets.QPushButton("选择 JSON 文件导入")
        btn_smart_book = QtWidgets.QPushButton("🖼️ 智能导入（图片/PDF）")
        btn_export_book = QtWidgets.QPushButton("导出阅读报表")
        btn_help_book = QtWidgets.QPushButton("操作说明")
        btn_api_settings = QtWidgets.QPushButton("⚙️ API设置")
        book_btn_row.addWidget(btn_import_book)
        book_btn_row.addWidget(btn_smart_book)
        book_btn_row.addWidget(btn_export_book)
        book_btn_row.addWidget(btn_help_book)
        book_btn_row.addWidget(btn_api_settings)
        book_btn_row.addStretch(1)
        book_root.addLayout(book_btn_row)

        book_scroll = QtWidgets.QScrollArea()
        book_scroll.setWidgetResizable(True)
        book_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        book_root.addWidget(book_scroll, 1)

        book_container = QtWidgets.QWidget()
        book_container.setStyleSheet("background: transparent;")
        book_scroll.setWidget(book_container)
        book_container_layout = QtWidgets.QVBoxLayout(book_container)
        book_container_layout.setContentsMargins(0, 0, 0, 0)
        book_container_layout.setSpacing(10)

        self.reading_book_card_container = book_container
        self._reading_book_layout = book_container_layout
        self._reading_book_scroll = book_scroll
        self.reading_tree_metas = {}

        btn_import_book.clicked.connect(self.open_book_file_dialog)
        btn_smart_book.clicked.connect(self._smart_import_book_file_dialog)
        btn_export_book.clicked.connect(self.export_reading_report)
        btn_help_book.clicked.connect(self.show_reading_json_prompt_help)
        btn_api_settings.clicked.connect(self.show_api_settings_dialog)

        tabs.addTab(book_tab, "书籍阅读")

        paper_tab = QtWidgets.QWidget()
        paper_root = QtWidgets.QVBoxLayout(paper_tab)
        paper_root.setContentsMargins(0, 0, 0, 0)
        paper_root.setSpacing(10)

        paper_drop = _FileDropLabel("📥 拖拽 JSON / 图片 / PDF 到此处导入", import_paper_paths)
        paper_root.addWidget(paper_drop)

        paper_btn_row = QtWidgets.QHBoxLayout()
        btn_import_paper = QtWidgets.QPushButton("选择 JSON 文件导入")
        btn_smart_paper = QtWidgets.QPushButton("🖼️ 智能导入（图片/PDF）")
        btn_help_paper = QtWidgets.QPushButton("操作说明")
        btn_api_settings_paper = QtWidgets.QPushButton("⚙️ API设置")
        paper_btn_row.addWidget(btn_import_paper)
        paper_btn_row.addWidget(btn_smart_paper)
        paper_btn_row.addWidget(btn_help_paper)
        paper_btn_row.addWidget(btn_api_settings_paper)
        paper_btn_row.addStretch(1)
        paper_root.addLayout(paper_btn_row)

        paper_scroll = QtWidgets.QScrollArea()
        paper_scroll.setWidgetResizable(True)
        paper_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        paper_root.addWidget(paper_scroll, 1)

        paper_container = QtWidgets.QWidget()
        paper_container.setStyleSheet("background: transparent;")
        paper_scroll.setWidget(paper_container)
        paper_container_layout = QtWidgets.QVBoxLayout(paper_container)
        paper_container_layout.setContentsMargins(0, 0, 0, 0)
        paper_container_layout.setSpacing(10)

        self.reading_paper_card_container = paper_container
        self._reading_paper_layout = paper_container_layout
        self._reading_paper_scroll = paper_scroll

        class _CardMarginFilter(QtCore.QObject):
            def __init__(self, callback):
                super().__init__()
                self._callback = callback

            def eventFilter(self, obj, event):  # noqa: N802
                if event.type() == QtCore.QEvent.Type.Resize:
                    self._callback()
                return False

        self._reading_card_margin_filter = _CardMarginFilter(self._sync_reading_card_margins)
        book_scroll.viewport().installEventFilter(self._reading_card_margin_filter)
        paper_scroll.viewport().installEventFilter(self._reading_card_margin_filter)
        QtCore.QTimer.singleShot(0, self._sync_reading_card_margins)

        btn_import_paper.clicked.connect(self.open_paper_file_dialog)
        btn_smart_paper.clicked.connect(self._smart_import_paper_file_dialog)
        btn_help_paper.clicked.connect(self.show_literature_json_prompt_help)
        btn_api_settings_paper.clicked.connect(self.show_api_settings_dialog)

        tabs.addTab(paper_tab, "文献导读")

        win.show()
        # Ensure the first render happens after Qt processes the show event.
        QtCore.QTimer.singleShot(0, self.refresh_reading_ui)

    def show_api_settings_dialog(self) -> None:
        parent = self.reading_window or self

        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("⚙️ API 设置")
        dialog.resize(440, 280)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(8)

        hint = QtWidgets.QLabel(
            "💡 默认使用硅基流动 + Kimi-K2.5（支持图片识别）\n"
            "也兼容 DeepSeek / OpenAI / Ollama 等接口\n"
            "首次使用需填写 API Key，保存后无需再次输入。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#4B5563; padding:4px 0;")
        root.addWidget(hint)

        form = QtWidgets.QFormLayout()
        form.setSpacing(6)

        entry_base_url = QtWidgets.QLineEdit(str(app_config.get("llm_api_base_url", "https://api.siliconflow.cn/v1") or ""))
        entry_api_key = QtWidgets.QLineEdit(str(app_config.get("llm_api_key", "") or ""))
        entry_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        entry_model = QtWidgets.QLineEdit(str(app_config.get("llm_api_model", "Pro/moonshotai/Kimi-K2.5") or ""))

        form.addRow("Base URL:", entry_base_url)
        form.addRow("API Key:", entry_api_key)
        form.addRow("模型:", entry_model)
        root.addLayout(form)

        preset_row = QtWidgets.QHBoxLayout()
        preset_label = QtWidgets.QLabel("快捷预设:")
        btn_preset_deepseek = QtWidgets.QPushButton("DeepSeek")
        btn_preset_openai = QtWidgets.QPushButton("OpenAI")
        btn_preset_silicon = QtWidgets.QPushButton("硅基流动")
        preset_row.addWidget(preset_label)
        preset_row.addWidget(btn_preset_deepseek)
        preset_row.addWidget(btn_preset_openai)
        preset_row.addWidget(btn_preset_silicon)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        def _apply_preset(base_url: str, model: str) -> None:
            entry_base_url.setText(base_url)
            entry_model.setText(model)

        btn_preset_deepseek.clicked.connect(lambda: _apply_preset("https://api.deepseek.com", "deepseek-chat"))
        btn_preset_openai.clicked.connect(lambda: _apply_preset("https://api.openai.com/v1", "gpt-4o"))
        btn_preset_silicon.clicked.connect(lambda: _apply_preset("https://api.siliconflow.cn/v1", "Pro/moonshotai/Kimi-K2.5"))

        status_label = QtWidgets.QLabel("")
        status_label.setWordWrap(True)
        root.addWidget(status_label)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btn_test = QtWidgets.QPushButton("测试连接")
        btn_save = QtWidgets.QPushButton("保存")
        btn_cancel = QtWidgets.QPushButton("取消")
        btns.addWidget(btn_test)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        root.addLayout(btns)

        def _test_connection() -> None:
            key = entry_api_key.text().strip()
            base = entry_base_url.text().strip()
            model = entry_model.text().strip()
            if not key:
                status_label.setText("❌ 请先填写 API Key")
                status_label.setStyleSheet("color:#DC2626;")
                return
            if not base:
                status_label.setText("❌ 请填写 Base URL")
                status_label.setStyleSheet("color:#DC2626;")
                return
            status_label.setText("正在测试连接...")
            status_label.setStyleSheet("color:#2563EB;")
            status_label.repaint()

            import urllib.request
            import ssl
            import json as _json
            url = f"{base.rstrip('/')}/chat/completions"
            payload = _json.dumps({
                "model": model or "deepseek-chat",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }, ensure_ascii=False).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    resp.read()
                status_label.setText("✅ 连接成功！")
                status_label.setStyleSheet("color:#16A34A;")
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    status_label.setText("❌ API Key 验证失败")
                else:
                    status_label.setText(f"❌ HTTP 错误 {e.code}")
                status_label.setStyleSheet("color:#DC2626;")
            except Exception as e:
                status_label.setText(f"❌ 连接失败: {e}")
                status_label.setStyleSheet("color:#DC2626;")

        def _save_settings() -> None:
            app_config["llm_api_key"] = entry_api_key.text().strip()
            app_config["llm_api_base_url"] = entry_base_url.text().strip() or "https://api.siliconflow.cn/v1"
            app_config["llm_api_model"] = entry_model.text().strip() or "Pro/moonshotai/Kimi-K2.5"
            save_app_config()
            status_label.setText("✅ 已保存")
            status_label.setStyleSheet("color:#16A34A;")
            QtCore.QTimer.singleShot(800, dialog.accept)

        btn_test.clicked.connect(_test_connection)
        btn_save.clicked.connect(_save_settings)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def _ensure_api_configured(self) -> bool:
        if is_api_configured():
            return True
        result = QtWidgets.QMessageBox.question(
            self.reading_window or self,
            "API 未配置",
            "智能导入需要配置 API Key。\n是否现在配置？",
        )
        if result == QtWidgets.QMessageBox.StandardButton.Yes:
            self.show_api_settings_dialog()
            return is_api_configured()
        return False

    def _run_with_progress(self, title: str, steps: list[str], worker_fn, on_done) -> None:
        parent = self.reading_window or self
        dialog = StepProgressDialog(title, steps, parent)

        class _ProgressSignal(QtCore.QObject):
            advance = QtCore.Signal(int, str)

        sig = _ProgressSignal()
        sig.advance.connect(dialog.advance_to)

        dialog.show()
        dialog.repaint()

        result_holder: list[Any] = []
        error_holder: list[str] = []

        def _work() -> None:
            try:
                def on_step(step_index: int, detail: str = "") -> None:
                    if not dialog.is_cancelled():
                        sig.advance.emit(step_index, detail)
                result = worker_fn(on_step)
                if not dialog.is_cancelled():
                    result_holder.append(result)
            except ApiError as e:
                if not dialog.is_cancelled():
                    msg = str(e)
                    if e.detail:
                        msg += f"\n\n详细信息:\n{e.detail[:500]}"
                    error_holder.append(msg)
            except Exception as e:
                if not dialog.is_cancelled():
                    error_holder.append(f"未知错误: {e}")

        def _finish() -> None:
            if dialog.is_cancelled():
                dialog.close()
                return
            dialog.finish_success()
            QtCore.QTimer.singleShot(600, dialog.close)
            if error_holder:
                QtWidgets.QMessageBox.critical(parent, "导入失败", error_holder[0])
                return
            if result_holder:
                on_done(result_holder[0])

        import threading
        thread = threading.Thread(target=_work, daemon=True)
        thread.start()

        def _poll() -> None:
            if thread.is_alive():
                QtCore.QTimer.singleShot(200, _poll)
            else:
                _finish()

        QtCore.QTimer.singleShot(200, _poll)

    def _smart_import_book(self, file_paths: list[str]) -> None:
        if not self._ensure_api_configured():
            return

        parent = self.reading_window or self
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📖 智能导入新书")
        dialog.resize(340, 260)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(8)

        file_hint = QtWidgets.QLabel(f"已选择 {len(file_paths)} 个文件")
        file_hint.setStyleSheet("color:#4B5563;")
        root.addWidget(file_hint)

        entry_title = QtWidgets.QLineEdit()
        entry_author = QtWidgets.QLineEdit()
        entry_version = QtWidgets.QLineEdit()
        root.addWidget(QtWidgets.QLabel("书名 (必填):"))
        root.addWidget(entry_title)
        root.addWidget(QtWidgets.QLabel("作者 (必填):"))
        root.addWidget(entry_author)
        root.addWidget(QtWidgets.QLabel("版本/版次 (选填):"))
        root.addWidget(entry_version)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("确认导入")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        def confirm_import() -> None:
            data = global_data
            if data is None:
                return
            title = entry_title.text().strip()
            author = entry_author.text().strip()
            version = entry_version.text().strip()

            if not title or not author:
                QtWidgets.QMessageBox.warning(dialog, "缺少信息", "书名和作者是必填项！")
                return

            books = data.setdefault("reading_books", {})
            if title in books:
                ans = QtWidgets.QMessageBox.question(dialog, "覆盖确认", f"已存在《{title}》，是否覆盖？")
                if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                    return

            dialog.accept()

            def worker(on_step) -> list[Any]:
                return smart_import_book(file_paths, progress_callback=on_step)

            def on_done(json_data: list[Any]) -> None:
                try:
                    book_tree, total_pages = calculate_book_pages(json_data)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(parent, "解析失败", f"API 返回的 JSON 解析出错: {e}")
                    return
                data["reading_books"][title] = {
                    "author": author,
                    "version": version,
                    "total_pages": total_pages,
                    "read_pages": 0,
                    "time_spent": 0,
                    "tree": book_tree,
                }
                self.sync_reading_book_progress(data["reading_books"][title])
                save_data()
                self.refresh_reading_ui()
                QtWidgets.QMessageBox.information(parent, "成功", f"《{title}》导入成功！共计 {total_pages} 页。")

            book_steps = [
                "\u8bfb\u53d6\u6587\u4ef6",
                "\u51c6\u5907\u56fe\u7247",
                "\u53d1\u9001\u8bf7\u6c42",
                "AI \u6b63\u5728\u8bc6\u522b\u76ee\u5f55",
                "\u89e3\u6790\u8fd4\u56de\u7ed3\u679c",
            ]
            self._run_with_progress("\u6b63\u5728\u8bc6\u522b\u76ee\u5f55...", book_steps, worker, on_done)

        ok_btn.clicked.connect(confirm_import)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _smart_import_book_file_dialog(self) -> None:
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self.reading_window or self,
            "选择书籍目录图片或PDF",
            filter="图片与PDF (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf);;所有文件 (*)",
        )
        if not file_paths:
            return
        self._smart_import_book(file_paths)

    def _smart_import_paper(self, file_paths: list[str]) -> None:
        if not self._ensure_api_configured():
            return

        parent = self.reading_window or self
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📄 智能导入文献导读")
        dialog.resize(360, 260)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(8)

        file_hint = QtWidgets.QLabel(f"已选择 {len(file_paths)} 个文件")
        file_hint.setStyleSheet("color:#4B5563;")
        root.addWidget(file_hint)

        entry_title = QtWidgets.QLineEdit()
        entry_author = QtWidgets.QLineEdit()
        entry_venue = QtWidgets.QLineEdit()
        root.addWidget(QtWidgets.QLabel("文献标题 (必填):"))
        root.addWidget(entry_title)
        root.addWidget(QtWidgets.QLabel("作者/团队 (选填):"))
        root.addWidget(entry_author)
        root.addWidget(QtWidgets.QLabel("会议/期刊/年份 (选填):"))
        root.addWidget(entry_venue)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("确认导入")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        def confirm_import() -> None:
            data = global_data
            if data is None:
                return
            title = entry_title.text().strip()
            author = entry_author.text().strip()
            venue = entry_venue.text().strip()

            if not title:
                QtWidgets.QMessageBox.warning(dialog, "缺少信息", "文献标题是必填项！")
                return

            papers = data.setdefault("reading_papers", {})
            if title in papers:
                ans = QtWidgets.QMessageBox.question(dialog, "覆盖确认", f"已存在《{title}》，是否覆盖？")
                if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                    return

            dialog.accept()

            def worker(on_step) -> list[Any]:
                return smart_import_paper(file_paths, progress_callback=on_step)

            def on_done(json_data: list[Any]) -> None:
                try:
                    total_hours = self._parse_paper_json_to_data(json_data, title, author, venue)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(parent, "解析失败", f"API 返回的 JSON 解析出错: {e}")
                    return
                self.refresh_reading_ui()
                QtWidgets.QMessageBox.information(parent, "成功", f"《{title}》导入成功！共计 {total_hours:.1f} 小时。")

            paper_steps = [
                "\u8bfb\u53d6\u6587\u4ef6",
                "\u51c6\u5907\u56fe\u7247",
                "\u53d1\u9001\u8bf7\u6c42",
                "AI \u6b63\u5728\u5206\u6790\u6587\u732e",
                "\u89e3\u6790\u8fd4\u56de\u7ed3\u679c",
            ]
            self._run_with_progress("\u6b63\u5728\u5206\u6790\u6587\u732e...", paper_steps, worker, on_done)

        ok_btn.clicked.connect(confirm_import)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _smart_import_paper_file_dialog(self) -> None:
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self.reading_window or self,
            "选择文献图片或PDF",
            filter="图片与PDF (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf);;所有文件 (*)",
        )
        if not file_paths:
            return
        self._smart_import_paper(file_paths)

    def _parse_paper_json_to_data(self, json_data: list[Any], title: str, author: str, venue: str) -> float:
        if not isinstance(json_data, list):
            raise ValueError("JSON 顶层必须是数组")

        def _coerce_hours(value: Any) -> float:
            try:
                return float(value)
            except Exception:
                return 0.0

        phases: list[dict[str, Any]] = []
        total_hours = 0.0
        for phase in json_data:
            if not isinstance(phase, dict):
                continue
            phase_title = str(phase.get("phase", "") or "").strip()
            if not phase_title:
                raise ValueError("阶段名称缺失")

            tasks: list[dict[str, Any]] = []
            phase_hours = 0.0
            for task in phase.get("tasks", []) if isinstance(phase.get("tasks"), list) else []:
                if not isinstance(task, dict):
                    continue
                task_title = str(task.get("title", "") or "").strip()
                if not task_title:
                    raise ValueError(f"阶段《{phase_title}》中存在空任务标题")
                subtasks: list[dict[str, Any]] = []
                task_hours = 0.0
                for sub in task.get("subtasks", []) if isinstance(task.get("subtasks"), list) else []:
                    if not isinstance(sub, dict):
                        continue
                    sub_title = str(sub.get("title", "") or "").strip()
                    if not sub_title:
                        raise ValueError(f"任务《{task_title}》存在空子任务标题")
                    sub_hours = _coerce_hours(sub.get("hours", 0) or 0)
                    task_hours += sub_hours
                    subtasks.append({"title": sub_title, "hours": sub_hours, "done": False, "time_spent": 0})

                task_hours = float(task_hours)
                tasks.append({"title": task_title, "hours": task_hours, "done": False, "subtasks": subtasks})
                phase_hours += task_hours

            phase_hours = float(phase_hours)
            phases.append({"phase": phase_title, "total_hours": phase_hours, "done": False, "tasks": tasks})
            total_hours += phase_hours

        if not phases:
            raise ValueError("未找到有效阶段数据")

        data = global_data
        data.setdefault("reading_papers", {})
        data["reading_papers"][title] = {
            "author": author,
            "venue": venue,
            "total_hours": total_hours,
            "done_hours": 0,
            "time_spent": 0,
            "phases": phases,
        }
        self.sync_literature_progress(data["reading_papers"][title])
        save_data()
        return total_hours

    def open_book_file_dialog(self) -> None:
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self.reading_window or self, "选择书籍 JSON 文件", filter="JSON 文件 (*.json)")
        if not file_paths:
            return
        for file_path in file_paths:
            self.open_book_import_dialog(file_path)

    def open_book_import_dialog(self, file_path: str) -> None:
        if not os.path.isfile(file_path):
            QtWidgets.QMessageBox.warning(self.reading_window or self, "文件不存在", "未找到该文件。")
            return

        parent = self.reading_window or self
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📖 导入新书")
        dialog.resize(340, 260)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(8)

        entry_title = QtWidgets.QLineEdit()
        entry_author = QtWidgets.QLineEdit()
        entry_version = QtWidgets.QLineEdit()
        root.addWidget(QtWidgets.QLabel("书名 (必填):"))
        root.addWidget(entry_title)
        root.addWidget(QtWidgets.QLabel("作者 (必填):"))
        root.addWidget(entry_author)
        root.addWidget(QtWidgets.QLabel("版本/版次 (选填):"))
        root.addWidget(entry_version)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("确认导入")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        def confirm_import() -> None:
            data = global_data
            if data is None:
                return
            title = entry_title.text().strip()
            author = entry_author.text().strip()
            version = entry_version.text().strip()

            if not title or not author:
                QtWidgets.QMessageBox.warning(dialog, "缺少信息", "书名和作者是必填项！")
                return

            books = data.setdefault("reading_books", {})
            if title in books:
                ans = QtWidgets.QMessageBox.question(dialog, "覆盖确认", f"已存在《{title}》，是否覆盖？")
                if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                    return

            try:
                total_pages = self.import_book_from_json(file_path, title, author, version)
            except Exception as e:
                QtWidgets.QMessageBox.critical(dialog, "解析失败", f"文件解析出错: {e}")
                return

            QtWidgets.QMessageBox.information(dialog, "成功", f"《{title}》导入成功！共计 {total_pages} 页。")
            dialog.accept()

        ok_btn.clicked.connect(confirm_import)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def import_book_from_json(self, file_path: str, title: str, author: str, version: str) -> int:
        with open(file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        book_tree, total_pages = calculate_book_pages(json_data)
        data = global_data
        if data is None:
            raise RuntimeError("数据未初始化")
        data.setdefault("reading_books", {})
        data["reading_books"][title] = {
            "author": author,
            "version": version,
            "total_pages": total_pages,
            "read_pages": 0,
            "time_spent": 0,
            "tree": book_tree,
        }
        self.sync_reading_book_progress(data["reading_books"][title])
        save_data()
        self.refresh_reading_ui()
        return total_pages

    def open_paper_file_dialog(self) -> None:
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self.reading_window or self,
            "选择文献导读 JSON 文件",
            filter="JSON 文件 (*.json)",
        )
        if not file_paths:
            return
        for file_path in file_paths:
            self.open_paper_import_dialog(file_path)

    def open_paper_import_dialog(self, file_path: str) -> None:
        if not os.path.isfile(file_path):
            QtWidgets.QMessageBox.warning(self.reading_window or self, "文件不存在", "未找到该文件。")
            return

        parent = self.reading_window or self
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📄 导入文献导读")
        dialog.resize(360, 260)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(8)

        entry_title = QtWidgets.QLineEdit()
        entry_author = QtWidgets.QLineEdit()
        entry_venue = QtWidgets.QLineEdit()
        root.addWidget(QtWidgets.QLabel("文献标题 (必填):"))
        root.addWidget(entry_title)
        root.addWidget(QtWidgets.QLabel("作者/团队 (选填):"))
        root.addWidget(entry_author)
        root.addWidget(QtWidgets.QLabel("会议/期刊/年份 (选填):"))
        root.addWidget(entry_venue)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        ok_btn = QtWidgets.QPushButton("确认导入")
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

        def confirm_import() -> None:
            data = global_data
            if data is None:
                return
            title = entry_title.text().strip()
            author = entry_author.text().strip()
            venue = entry_venue.text().strip()

            if not title:
                QtWidgets.QMessageBox.warning(dialog, "缺少信息", "文献标题是必填项！")
                return

            papers = data.setdefault("reading_papers", {})
            if title in papers:
                ans = QtWidgets.QMessageBox.question(dialog, "覆盖确认", f"已存在《{title}》，是否覆盖？")
                if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                    return

            try:
                total_hours = self.import_paper_from_json(file_path, title, author, venue)
            except Exception as e:
                QtWidgets.QMessageBox.critical(dialog, "解析失败", f"文件解析出错: {e}")
                return

            QtWidgets.QMessageBox.information(dialog, "成功", f"《{title}》导入成功！共计 {total_hours:.1f} 小时。")
            dialog.accept()

        ok_btn.clicked.connect(confirm_import)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def import_paper_from_json(self, file_path: str, title: str, author: str, venue: str) -> float:
        with open(file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        if not isinstance(json_data, list):
            raise ValueError("JSON 顶层必须是数组")

        def _coerce_hours(value: Any) -> float:
            try:
                return float(value)
            except Exception:
                return 0.0

        phases: list[dict[str, Any]] = []
        total_hours = 0.0
        for phase in json_data:
            if not isinstance(phase, dict):
                continue
            phase_title = str(phase.get("phase", "") or "").strip()
            if not phase_title:
                raise ValueError("阶段名称缺失")

            tasks: list[dict[str, Any]] = []
            phase_hours = 0.0
            for task in phase.get("tasks", []) if isinstance(phase.get("tasks"), list) else []:
                if not isinstance(task, dict):
                    continue
                task_title = str(task.get("title", "") or "").strip()
                if not task_title:
                    raise ValueError(f"阶段《{phase_title}》中存在空任务标题")
                subtasks: list[dict[str, Any]] = []
                task_hours = 0.0
                for sub in task.get("subtasks", []) if isinstance(task.get("subtasks"), list) else []:
                    if not isinstance(sub, dict):
                        continue
                    sub_title = str(sub.get("title", "") or "").strip()
                    if not sub_title:
                        raise ValueError(f"任务《{task_title}》存在空子任务标题")
                    sub_hours = _coerce_hours(sub.get("hours", 0) or 0)
                    task_hours += sub_hours
                    subtasks.append({"title": sub_title, "hours": sub_hours, "done": False, "time_spent": 0})

                task_hours = float(task_hours)
                tasks.append({"title": task_title, "hours": task_hours, "done": False, "subtasks": subtasks})
                phase_hours += task_hours

            phase_hours = float(phase_hours)
            phases.append({"phase": phase_title, "total_hours": phase_hours, "done": False, "tasks": tasks})
            total_hours += phase_hours

        if not phases:
            raise ValueError("未找到有效阶段数据")

        data = global_data
        if data is None:
            raise RuntimeError("数据未初始化")
        data.setdefault("reading_papers", {})
        data["reading_papers"][title] = {
            "author": author,
            "venue": venue,
            "total_hours": total_hours,
            "done_hours": 0,
            "phases": phases,
        }
        self.sync_literature_progress(data["reading_papers"][title])
        save_data()
        self.refresh_reading_ui()
        return total_hours

    def refresh_reading_ui(self) -> None:
        self._refresh_reading_books_ui()
        self.refresh_literature_ui()

    def _refresh_reading_books_ui(self) -> None:
        win = self.reading_window
        container = getattr(self, "reading_book_card_container", None)
        layout = getattr(self, "_reading_book_layout", None)
        if win is None or container is None or layout is None:
            return

        def delete_book(title: str) -> None:
            data = global_data
            if data is None:
                return
            books = data.get("reading_books", {})
            if not isinstance(books, dict) or title not in books:
                return
            ans = QtWidgets.QMessageBox.question(
                win,
                "确认删除",
                f"确认删除《{title}》？该书的阅读进度将被移除，且无法恢复。",
            )
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            books.pop(title, None)

            tasks = data.get("today_structured_tasks", {})
            if isinstance(tasks, dict):
                for cat, items in list(tasks.items()):
                    if not isinstance(items, list):
                        continue
                    tasks[cat] = [
                        t for t in items if not (isinstance(t, dict) and t.get("meta_book") == title)
                    ]

            save_data()
            self.update_task_buttons()
            self.update_task_status_label()
            self.refresh_task_viewer_if_open()
            self.refresh_reading_ui()

        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        self.reading_tree_metas = {}
        data = global_data or {}
        books = data.get("reading_books", {})
        if not isinstance(books, dict) or not books:
            lab = QtWidgets.QLabel("暂无书籍，请先导入 JSON 目录文件。")
            lab.setObjectName("ReadingEmptyHint")
            lab.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(lab)
            layout.addStretch(1)
            return

        def set_item_done_style(item: QtWidgets.QTreeWidgetItem, done: bool) -> None:
            f = self._font(size=9, bold=False)
            f.setStrikeOut(done)
            base_color = QtGui.QColor("#6B7280" if done else "#111827")
            status_color = QtGui.QColor("#16A34A" if done else "#111827")
            for col in range(3):
                item.setFont(col, f)
                item.setForeground(col, QtGui.QBrush(status_color if col == 2 else base_color))

        for idx, book_title in enumerate(sorted(books.keys())):
            book_info = books.get(book_title)
            if not isinstance(book_info, dict):
                continue
            self.sync_reading_book_progress(book_info)

            total_pages = int(book_info.get("total_pages", 0) or 0)
            read_pages = int(book_info.get("read_pages", 0) or 0)
            time_spent = int(book_info.get("time_spent", 0) or 0)
            progress_pct = (read_pages / total_pages * 100) if total_pages > 0 else 0

            author = str(book_info.get("author", "") or "").strip()
            version = str(book_info.get("version", "") or "").strip()
            info_parts = [p for p in (author, version) if p]
            info_text = " / ".join(info_parts)

            tone_idx = int(idx % 4)
            tone = str(tone_idx)

            card = QtWidgets.QFrame()
            card.setObjectName("ReadingBookCard")
            card.setProperty("tone", tone)
            card.setProperty("complete", bool(total_pages > 0 and read_pages >= total_pages))
            card.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            card.setMinimumWidth(0)
            try:
                card.style().unpolish(card)
                card.style().polish(card)
            except Exception:
                pass
            card_lay = QtWidgets.QVBoxLayout(card)
            card_lay.setContentsMargins(10, 8, 10, 10)
            card_lay.setSpacing(6)

            title_text = f"📖 {book_title}" + (f" ({info_text})" if info_text else "")
            header_btn = QtWidgets.QToolButton()
            header_btn.setObjectName("ReadingBookHeader")
            header_btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            header_btn.setText(title_text)
            header_btn.setCheckable(True)
            header_btn.setChecked(False)
            header_btn.setArrowType(QtCore.Qt.ArrowType.RightArrow)
            header_btn.setFont(self._font(size=11, bold=True))
            header_btn.setProperty("tone", tone)
            try:
                header_btn.style().unpolish(header_btn)
                header_btn.style().polish(header_btn)
            except Exception:
                pass
            header_btn.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Ignored,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            header_btn.setMinimumWidth(0)
            header_row = QtWidgets.QWidget()
            header_row_lay = QtWidgets.QHBoxLayout(header_row)
            header_row_lay.setContentsMargins(0, 0, 0, 0)
            header_row_lay.setSpacing(6)
            header_row_lay.addWidget(header_btn, 1)

            btn_del = QtWidgets.QPushButton("删除")
            btn_del.setFixedWidth(60)
            btn_del.clicked.connect(lambda _=False, t=book_title: delete_book(t))
            header_row_lay.addWidget(btn_del, 0)

            card_lay.addWidget(header_row)

            prog = _CandyProgressBar(tone=tone_idx)
            prog.setValue(int(progress_pct))
            card_lay.addWidget(prog)

            card_lay.addWidget(QtWidgets.QLabel(f"进度: {read_pages} / {total_pages} 页 ({progress_pct:.1f}%)"))
            estimate_text = self.build_reading_estimate_text(book_info)
            time_label = QtWidgets.QLabel(f"已专注: {self.format_minutes(time_spent)} | {estimate_text}")
            time_label.setStyleSheet("color:#4B5563")
            card_lay.addWidget(time_label)

            tree = QtWidgets.QTreeWidget()
            tree.setColumnCount(3)
            tree.setHeaderLabels(["目录结构", "页数", "状态"])
            tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            tree.setAlternatingRowColors(True)
            tree.setUniformRowHeights(False)
            tree.setWordWrap(True)
            tree.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
            try:
                hdr = tree.header()
                hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
                hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
                hdr.setStretchLastSection(False)
            except Exception:
                pass

            tree.setIndentation(8)

            def _sync_tree_columns(tr: QtWidgets.QTreeWidget = tree) -> None:
                hdr = tr.header()
                if hdr is None:
                    return
                fm = tr.fontMetrics()
                hours_w = max(
                    fm.horizontalAdvance("预计小时"),
                    fm.horizontalAdvance("88.8h"),
                ) + 12
                status_w = max(
                    fm.horizontalAdvance("状态"),
                    fm.horizontalAdvance("未完成"),
                    fm.horizontalAdvance("已完成"),
                ) + 12
                viewport = tr.viewport()
                avail = viewport.width() if viewport is not None else tr.width()
                col0 = max(180, avail - hours_w - status_w)
                tr.setColumnWidth(1, hours_w)
                tr.setColumnWidth(2, status_w)
                tr.setColumnWidth(0, col0)

            # Make the directory tree grow with its contents, so long catalogs are not clipped by a
            # fixed viewport height (avoid nested scrolling inside cards).
            tree.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            tree.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

            class _TreeResizeFilter(QtCore.QObject):
                def __init__(self, callback):
                    super().__init__()
                    self._callback = callback

                def eventFilter(self, obj, event):  # noqa: N802
                    if event.type() == QtCore.QEvent.Type.Resize:
                        self._callback()
                    return False

            def _calc_tree_height(tr: QtWidgets.QTreeWidget) -> int:
                header_h = tr.header().sizeHint().height() if tr.header() is not None else 0
                frame = tr.frameWidth() * 2
                fallback_h = tr.sizeHintForRow(0)
                if fallback_h <= 0:
                    fallback_h = max(18, tr.fontMetrics().height() + 8)

                def _collect_visible(item: QtWidgets.QTreeWidgetItem, bucket: list[QtWidgets.QTreeWidgetItem]) -> None:
                    bucket.append(item)
                    if item.isExpanded():
                        for idx in range(item.childCount()):
                            child = item.child(idx)
                            if child is not None:
                                _collect_visible(child, bucket)

                visible_items: list[QtWidgets.QTreeWidgetItem] = []
                for i in range(tr.topLevelItemCount()):
                    top = tr.topLevelItem(i)
                    if top is not None:
                        _collect_visible(top, visible_items)

                rows_h = 0
                for item in visible_items:
                    idx = tr.indexFromItem(item, 0)
                    hint = tr.sizeHintForIndex(idx).height() if idx.isValid() else 0
                    rows_h += hint if hint > 0 else fallback_h

                return header_h + frame + rows_h + 6

            def _sync_tree_height(tr: QtWidgets.QTreeWidget = tree, card_widget: QtWidgets.QWidget = card) -> None:
                # Debounce: avoid recalculating hundreds of times when expandAll() triggers many signals.
                if getattr(tr, "_sgp_height_sync_pending", False):
                    return
                tr._sgp_height_sync_pending = True  # type: ignore[attr-defined]

                def _apply() -> None:
                    tr._sgp_height_sync_pending = False  # type: ignore[attr-defined]
                    h = _calc_tree_height(tr)
                    tr.setMinimumHeight(h)
                    tr.setMaximumHeight(h)
                    card_widget.adjustSize()
                    if container is not None:
                        container.adjustSize()

                QtCore.QTimer.singleShot(0, _apply)
            card_lay.addWidget(tree)

            def _toggle_tree(expanded: bool, tr: QtWidgets.QTreeWidget = tree, btn: QtWidgets.QToolButton = header_btn) -> None:
                tr.setVisible(expanded)
                btn.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)
                if expanded:
                    _sync_tree_height(tr)

            header_btn.toggled.connect(_toggle_tree)

            # Default: collapse the card content (tree hidden).
            tree.setVisible(False)
            _toggle_tree(False)

            def on_menu(pos: QtCore.QPoint, tr: QtWidgets.QTreeWidget = tree) -> None:
                item = tr.itemAt(pos)
                if item is None:
                    return
                meta = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(meta, dict) or meta.get("node_type") != "node":
                    return
                menu = QtWidgets.QMenu(tr)
                act_research = menu.addAction("加入今日任务（科研）")
                act_theory = menu.addAction("加入今日任务（理论/技术）")
                chosen = menu.exec(tr.viewport().mapToGlobal(pos))
                if chosen == act_research:
                    self.add_reading_task_from_meta(meta, cat="科研")
                elif chosen == act_theory:
                    self.add_reading_task_from_meta(meta, cat="理论/技术")

            tree.customContextMenuRequested.connect(on_menu)

            def _add_book_node(
                node: dict[str, Any],
                parent_item: QtWidgets.QTreeWidgetItem | None,
                path: list[str],
            ) -> None:
                if not isinstance(node, dict):
                    return
                title = str(node.get("title", "") or "").strip()
                if not title:
                    return
                children = self._get_book_children(node)
                pages = int(node.get("pages_count", 0) or 0)
                done = bool(node.get("done"))
                status = "已读" if done else "未读"

                item = QtWidgets.QTreeWidgetItem([title, f"{pages}页", status])
                item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {
                        "node_type": "node",
                        "book": book_title,
                        "path": path,
                        "pages": pages,
                        "has_children": bool(children),
                        "chapter": path[0] if path else "",
                        "section": path[1] if len(path) > 1 else "",
                    },
                )
                set_item_done_style(item, done)
                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                item.setExpanded(False)

                for child in children:
                    child_title = str(child.get("title", "") or "").strip()
                    if not child_title:
                        continue
                    _add_book_node(child, item, path + [child_title])

            for chap in book_info.get("tree", []) or []:
                if not isinstance(chap, dict):
                    continue
                chap_title = str(chap.get("title", "") or "").strip()
                if not chap_title:
                    continue
                _add_book_node(chap, None, [chap_title])

            # Default behavior: keep the catalog collapsed on entry; still auto-fit height when user expands/collapses.
            tree.itemExpanded.connect(lambda _it, tr=tree: _sync_tree_height(tr))
            tree.itemCollapsed.connect(lambda _it, tr=tree: _sync_tree_height(tr))
            tree.viewport().installEventFilter(_TreeResizeFilter(lambda: _sync_tree_height(tree)))
            _sync_tree_height(tree)

            layout.addWidget(card)

        layout.addStretch(1)

    def refresh_literature_ui(self) -> None:
        win = self.reading_window
        container = getattr(self, "reading_paper_card_container", None)
        layout = getattr(self, "_reading_paper_layout", None)
        if win is None or container is None or layout is None:
            return

        def delete_paper(title: str) -> None:
            data = global_data
            if data is None:
                return
            papers = data.get("reading_papers", {})
            if not isinstance(papers, dict) or title not in papers:
                return
            ans = QtWidgets.QMessageBox.question(
                win,
                "确认删除",
                f"确认删除《{title}》？该文献导读记录将被移除，且无法恢复。",
            )
            if ans != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            papers.pop(title, None)
            save_data()
            self.refresh_literature_ui()

        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        data = global_data or {}
        papers = data.get("reading_papers", {})
        if not isinstance(papers, dict) or not papers:
            lab = QtWidgets.QLabel("暂无文献导读，请先导入 JSON 规划文件。")
            lab.setObjectName("ReadingEmptyHint")
            lab.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(lab)
            layout.addStretch(1)
            return

        def set_item_done_style(item: QtWidgets.QTreeWidgetItem, done: bool) -> None:
            f = self._font(size=9, bold=False)
            f.setStrikeOut(done)
            base_color = QtGui.QColor("#6B7280" if done else "#111827")
            status_color = QtGui.QColor("#16A34A" if done else "#111827")
            for col in range(3):
                item.setFont(col, f)
                item.setForeground(col, QtGui.QBrush(status_color if col == 2 else base_color))

        class _HeaderLabel(QtWidgets.QLabel):
            def __init__(self, text: str, toggle_btn: QtWidgets.QToolButton):
                super().__init__(text)
                self._toggle_btn = toggle_btn
                self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

            def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._toggle_btn.toggle()
                super().mouseReleaseEvent(event)

        for idx, paper_title in enumerate(sorted(papers.keys())):
            paper_info = papers.get(paper_title)
            if not isinstance(paper_info, dict):
                continue
            self.sync_literature_progress(paper_info)

            total_hours = float(paper_info.get("total_hours", 0) or 0)
            done_hours = float(paper_info.get("done_hours", 0) or 0)
            progress_pct = (done_hours / total_hours * 100) if total_hours > 0 else 0
            time_spent = int(paper_info.get("time_spent", 0) or 0)
            estimate_text = self.build_literature_estimate_text(paper_info)

            author = str(paper_info.get("author", "") or "").strip()
            venue = str(paper_info.get("venue", "") or "").strip()
            info_parts = [p for p in (author, venue) if p]
            info_text = " / ".join(info_parts)

            status_text, stage_idx = self.get_literature_stage(paper_info)
            stage = str(stage_idx)
            tone_idx = int(idx % 4)
            tone = str(tone_idx)

            card = QtWidgets.QFrame()
            card.setObjectName("LiteratureCard")
            card.setProperty("stage", stage)
            card.setProperty("tone", tone)
            card.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            card.setMinimumWidth(0)
            try:
                card.style().unpolish(card)
                card.style().polish(card)
            except Exception:
                pass
            card_lay = QtWidgets.QVBoxLayout(card)
            card_lay.setContentsMargins(10, 8, 10, 10)
            card_lay.setSpacing(6)

            header_btn = QtWidgets.QToolButton()
            header_btn.setObjectName("LiteratureHeader")
            header_btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
            header_btn.setCheckable(True)
            header_btn.setChecked(False)
            header_btn.setArrowType(QtCore.Qt.ArrowType.RightArrow)
            header_btn.setProperty("stage", stage)
            try:
                header_btn.style().unpolish(header_btn)
                header_btn.style().polish(header_btn)
            except Exception:
                pass
            header_btn.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            header_btn.setFixedWidth(24)
            header_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

            header_row = QtWidgets.QWidget()
            header_row_lay = QtWidgets.QHBoxLayout(header_row)
            header_row_lay.setContentsMargins(0, 0, 0, 0)
            header_row_lay.setSpacing(6)

            title_label = _HeaderLabel(f"📄 {paper_title}", header_btn)
            title_label.setObjectName("LiteratureTitle")
            title_label.setProperty("stage", stage)
            title_label.setFont(self._font(size=11, bold=True))
            title_label.setWordWrap(True)

            meta_label = None
            if info_text:
                meta_label = _HeaderLabel(info_text, header_btn)
                meta_label.setObjectName("LiteratureMeta")
                meta_label.setWordWrap(True)

            text_box = QtWidgets.QWidget()
            text_lay = QtWidgets.QVBoxLayout(text_box)
            text_lay.setContentsMargins(0, 0, 0, 0)
            text_lay.setSpacing(2)
            text_lay.addWidget(title_label)
            if meta_label is not None:
                text_lay.addWidget(meta_label)

            header_row_lay.addWidget(header_btn, 0)
            header_row_lay.addWidget(text_box, 1)

            btn_del = QtWidgets.QPushButton("删除")
            btn_del.setFixedWidth(60)
            btn_del.clicked.connect(lambda _=False, t=paper_title: delete_paper(t))
            header_row_lay.addWidget(btn_del, 0)
            card_lay.addWidget(header_row)

            prog = _LiteratureProgressBar(tone=stage_idx)
            prog.setValue(int(progress_pct))
            card_lay.addWidget(prog)

            card_lay.addWidget(
                QtWidgets.QLabel(
                    f"进度: {done_hours:.1f} / {total_hours:.1f} 小时 ({progress_pct:.1f}%)"
                )
            )
            time_label = QtWidgets.QLabel(f"已专注: {self.format_minutes(time_spent)} | {estimate_text}")
            time_label.setStyleSheet("color:#4B5563")
            card_lay.addWidget(time_label)
            status_label = QtWidgets.QLabel(f"当前阶段: {status_text}")
            status_label.setObjectName("LiteratureStatus")
            status_label.setProperty("stage", stage)
            try:
                status_label.style().unpolish(status_label)
                status_label.style().polish(status_label)
            except Exception:
                pass
            card_lay.addWidget(status_label)

            tree = QtWidgets.QTreeWidget()
            tree.setColumnCount(3)
            tree.setHeaderLabels(["学习任务", "预计小时", "状态"])
            tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            tree.setAlternatingRowColors(True)
            tree.setUniformRowHeights(False)
            tree.setWordWrap(True)
            tree.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
            try:
                hdr = tree.header()
                hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)
                hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Fixed)
                hdr.setStretchLastSection(False)
            except Exception:
                pass

            tree.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            tree.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            tree.setIndentation(8)

            def _sync_tree_columns(tr: QtWidgets.QTreeWidget = tree) -> None:
                hdr = tr.header()
                if hdr is None:
                    return
                fm = tr.fontMetrics()
                hours_w = max(
                    fm.horizontalAdvance("预计小时"),
                    fm.horizontalAdvance("88.8h"),
                ) + 12
                status_w = max(
                    fm.horizontalAdvance("状态"),
                    fm.horizontalAdvance("未完成"),
                    fm.horizontalAdvance("已完成"),
                ) + 12
                viewport = tr.viewport()
                avail = viewport.width() if viewport is not None else tr.width()
                col0 = max(180, avail - hours_w - status_w)
                tr.setColumnWidth(1, hours_w)
                tr.setColumnWidth(2, status_w)
                tr.setColumnWidth(0, col0)

            def _calc_tree_height(tr: QtWidgets.QTreeWidget) -> int:
                header_h = tr.header().sizeHint().height() if tr.header() is not None else 0
                frame = tr.frameWidth() * 2
                fallback_h = tr.sizeHintForRow(0)
                if fallback_h <= 0:
                    fallback_h = max(18, tr.fontMetrics().height() + 8)

                def _collect_visible(item: QtWidgets.QTreeWidgetItem, bucket: list[QtWidgets.QTreeWidgetItem]) -> None:
                    bucket.append(item)
                    if item.isExpanded():
                        for idx in range(item.childCount()):
                            child = item.child(idx)
                            if child is not None:
                                _collect_visible(child, bucket)

                visible_items: list[QtWidgets.QTreeWidgetItem] = []
                for i in range(tr.topLevelItemCount()):
                    top = tr.topLevelItem(i)
                    if top is not None:
                        _collect_visible(top, visible_items)

                rows_h = 0
                for item in visible_items:
                    idx = tr.indexFromItem(item, 0)
                    hint = tr.sizeHintForIndex(idx).height() if idx.isValid() else 0
                    rows_h += hint if hint > 0 else fallback_h

                return header_h + frame + rows_h + 6

            def _sync_tree_height(tr: QtWidgets.QTreeWidget = tree, card_widget: QtWidgets.QWidget = card) -> None:
                if getattr(tr, "_sgp_height_sync_pending", False):
                    return
                tr._sgp_height_sync_pending = True  # type: ignore[attr-defined]

                def _apply() -> None:
                    tr._sgp_height_sync_pending = False  # type: ignore[attr-defined]
                    h = _calc_tree_height(tr)
                    tr.setMinimumHeight(h)
                    tr.setMaximumHeight(h)
                    card_widget.adjustSize()
                    if container is not None:
                        container.adjustSize()

                QtCore.QTimer.singleShot(0, _apply)

            def _sync_tree_layout(tr: QtWidgets.QTreeWidget = tree) -> None:
                _sync_tree_columns(tr)
                _sync_tree_height(tr)

            card_lay.addWidget(tree)

            def _toggle_tree(expanded: bool, tr: QtWidgets.QTreeWidget = tree, btn: QtWidgets.QToolButton = header_btn) -> None:
                tr.setVisible(expanded)
                btn.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)
                if expanded:
                    _sync_tree_layout(tr)

            header_btn.toggled.connect(_toggle_tree)
            tree.setVisible(False)
            _toggle_tree(False)

            def on_menu(pos: QtCore.QPoint, tr: QtWidgets.QTreeWidget = tree) -> None:
                item = tr.itemAt(pos)
                if item is None:
                    return
                meta = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(meta, dict) or meta.get("node_type") != "subtask":
                    return
                menu = QtWidgets.QMenu(tr)
                act_research = menu.addAction("加入今日任务（科研）")
                act_theory = menu.addAction("加入今日任务（理论/技术）")
                chosen = menu.exec(tr.viewport().mapToGlobal(pos))
                if chosen == act_research:
                    self.add_literature_task_from_meta(meta, cat="科研")
                elif chosen == act_theory:
                    self.add_literature_task_from_meta(meta, cat="理论/技术")

            tree.customContextMenuRequested.connect(on_menu)

            class _TreeResizeFilter(QtCore.QObject):
                def __init__(self, callback):
                    super().__init__()
                    self._callback = callback

                def eventFilter(self, obj, event):  # noqa: N802
                    if event.type() == QtCore.QEvent.Type.Resize:
                        self._callback()
                    return False

            def apply_check_state(meta: dict[str, Any], checked: bool) -> None:
                phases = paper_info.get("phases", []) if isinstance(paper_info.get("phases"), list) else []
                p_idx = meta.get("phase_idx")
                t_idx = meta.get("task_idx")
                s_idx = meta.get("sub_idx")
                if not isinstance(p_idx, int) or p_idx < 0 or p_idx >= len(phases):
                    return
                phase = phases[p_idx]
                if not isinstance(phase, dict):
                    return
                tasks = phase.get("tasks", []) if isinstance(phase.get("tasks"), list) else []

                if meta.get("node_type") == "phase":
                    for task in tasks:
                        if not isinstance(task, dict):
                            continue
                        task["done"] = bool(checked)
                        for sub in task.get("subtasks", []) if isinstance(task.get("subtasks"), list) else []:
                            if isinstance(sub, dict):
                                sub["done"] = bool(checked)
                                if not checked:
                                    sub["time_spent"] = 0
                elif meta.get("node_type") == "task":
                    if not isinstance(t_idx, int) or t_idx < 0 or t_idx >= len(tasks):
                        return
                    task = tasks[t_idx]
                    if not isinstance(task, dict):
                        return
                    task["done"] = bool(checked)
                    for sub in task.get("subtasks", []) if isinstance(task.get("subtasks"), list) else []:
                        if isinstance(sub, dict):
                            sub["done"] = bool(checked)
                            if not checked:
                                sub["time_spent"] = 0
                elif meta.get("node_type") == "subtask":
                    if not isinstance(t_idx, int) or t_idx < 0 or t_idx >= len(tasks):
                        return
                    task = tasks[t_idx]
                    subs = task.get("subtasks", []) if isinstance(task.get("subtasks"), list) else []
                    if not isinstance(s_idx, int) or s_idx < 0 or s_idx >= len(subs):
                        return
                    sub = subs[s_idx]
                    if isinstance(sub, dict):
                        sub["done"] = bool(checked)
                        if not checked:
                            sub["time_spent"] = 0

            def on_item_changed(item: QtWidgets.QTreeWidgetItem, col: int) -> None:
                if col != 0:
                    return
                meta = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(meta, dict):
                    return
                checked = item.checkState(0) == QtCore.Qt.CheckState.Checked
                apply_check_state(meta, checked)
                self.sync_literature_progress(paper_info)
                save_data()
                self.refresh_literature_ui()

            tree.blockSignals(True)
            for p_idx, phase in enumerate(paper_info.get("phases", []) or []):
                if not isinstance(phase, dict):
                    continue
                phase_title = str(phase.get("phase", "") or "")
                phase_hours = float(phase.get("total_hours", 0) or 0)
                phase_done = bool(phase.get("done"))
                phase_item = QtWidgets.QTreeWidgetItem([phase_title, f"{phase_hours:.1f}h", "已完成" if phase_done else "未完成"])
                phase_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {"node_type": "phase", "phase_idx": p_idx, "paper": paper_title, "phase": phase_title},
                )
                phase_item.setFlags(phase_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                phase_item.setCheckState(0, QtCore.Qt.CheckState.Checked if phase_done else QtCore.Qt.CheckState.Unchecked)
                set_item_done_style(phase_item, phase_done)
                tree.addTopLevelItem(phase_item)

                for t_idx, task in enumerate(phase.get("tasks", []) or []):
                    if not isinstance(task, dict):
                        continue
                    task_title = str(task.get("title", "") or "")
                    task_hours = float(task.get("hours", 0) or 0)
                    task_done = bool(task.get("done"))
                    task_item = QtWidgets.QTreeWidgetItem([task_title, f"{task_hours:.1f}h", "已完成" if task_done else "未完成"])
                    task_item.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole,
                        {
                            "node_type": "task",
                            "phase_idx": p_idx,
                            "task_idx": t_idx,
                            "paper": paper_title,
                            "phase": phase_title,
                            "task": task_title,
                        },
                    )
                    task_item.setFlags(task_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    task_item.setCheckState(0, QtCore.Qt.CheckState.Checked if task_done else QtCore.Qt.CheckState.Unchecked)
                    set_item_done_style(task_item, task_done)
                    phase_item.addChild(task_item)

                    for s_idx, sub in enumerate(task.get("subtasks", []) or []):
                        if not isinstance(sub, dict):
                            continue
                        sub_title = str(sub.get("title", "") or "")
                        sub_hours = float(sub.get("hours", 0) or 0)
                        sub_done = bool(sub.get("done"))
                        sub_item = QtWidgets.QTreeWidgetItem([sub_title, f"{sub_hours:.1f}h", "已完成" if sub_done else "未完成"])
                        sub_item.setData(
                            0,
                            QtCore.Qt.ItemDataRole.UserRole,
                            {
                                "node_type": "subtask",
                                "phase_idx": p_idx,
                                "task_idx": t_idx,
                                "sub_idx": s_idx,
                                "paper": paper_title,
                                "phase": phase_title,
                                "task": task_title,
                                "subtask": sub_title,
                                "hours": sub_hours,
                            },
                        )
                        sub_item.setFlags(sub_item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                        sub_item.setCheckState(0, QtCore.Qt.CheckState.Checked if sub_done else QtCore.Qt.CheckState.Unchecked)
                        set_item_done_style(sub_item, sub_done)
                        task_item.addChild(sub_item)

                phase_item.setExpanded(False)

            tree.blockSignals(False)
            tree.itemChanged.connect(on_item_changed)
            tree.itemExpanded.connect(lambda _it, tr=tree: _sync_tree_layout(tr))
            tree.itemCollapsed.connect(lambda _it, tr=tree: _sync_tree_layout(tr))
            tree.viewport().installEventFilter(_TreeResizeFilter(lambda: _sync_tree_layout(tree)))
            _sync_tree_layout(tree)

            layout.addWidget(card)

        layout.addStretch(1)

    def sync_literature_progress(self, paper_info: dict[str, Any]) -> None:
        phases = paper_info.get("phases", [])
        if not isinstance(phases, list):
            return

        def _coerce_hours(value: Any) -> float:
            try:
                return float(value)
            except Exception:
                return 0.0

        total = 0.0
        done = 0.0
        total_time = 0.0
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            tasks = phase.get("tasks", []) if isinstance(phase.get("tasks"), list) else []
            phase_total = 0.0
            phase_done = True
            phase_time = 0.0
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                subs = task.get("subtasks", []) if isinstance(task.get("subtasks"), list) else []
                task_total = 0.0
                task_done = True
                task_time = 0.0
                for sub in subs:
                    if not isinstance(sub, dict):
                        continue
                    hours = _coerce_hours(sub.get("hours", 0) or 0)
                    sub_time = _coerce_hours(sub.get("time_spent", 0) or 0)
                    task_total += hours
                    total += hours
                    task_time += sub_time
                    total_time += sub_time
                    if sub.get("done"):
                        done += hours
                    else:
                        task_done = False
                task["hours"] = float(task_total)
                task["done"] = bool(task_done and task_total > 0)
                task["time_spent"] = float(task_time)
                phase_total += task_total
                phase_time += task_time
                if not task["done"]:
                    phase_done = False
            phase["total_hours"] = float(phase_total)
            phase["done"] = bool(phase_done and phase_total > 0)
            phase["time_spent"] = float(phase_time)

        paper_info["total_hours"] = float(total)
        paper_info["done_hours"] = float(done)
        paper_info["time_spent"] = float(total_time)

    def get_literature_stage(self, paper_info: dict[str, Any]) -> tuple[str, int]:
        phases = paper_info.get("phases", []) if isinstance(paper_info.get("phases"), list) else []
        done_flags = [bool(p.get("done")) for p in phases if isinstance(p, dict)]
        stage = 0
        if len(done_flags) >= 1 and done_flags[0]:
            stage = 1
        if len(done_flags) >= 2 and done_flags[0] and done_flags[1]:
            stage = 2
        if len(done_flags) >= 3 and all(done_flags[:3]):
            stage = 2

        label = "泛读"
        if stage == 1:
            label = "半精读"
        elif stage == 2:
            label = "精读"
        if done_flags and all(done_flags):
            label = "精读（完成）"
        return label, stage

    def build_literature_estimate_text(self, paper_info: dict[str, Any]) -> str:
        total_hours = float(paper_info.get("total_hours", 0) or 0)
        done_hours = float(paper_info.get("done_hours", 0) or 0)
        time_spent = float(paper_info.get("time_spent", 0) or 0)
        if total_hours <= 0:
            return "预计还需: 未知"
        if done_hours <= 0 or time_spent <= 0:
            return "预计还需: 请先完成部分子任务以生成预测"
        remaining = total_hours - done_hours
        if remaining <= 0:
            return "预计还需: 已完成"
        minutes_per_hour = time_spent / max(done_hours, 0.1)
        estimate = remaining * minutes_per_hour
        return f"预计还需: {self.format_minutes(estimate)}"

    def _calc_card_side_margin(self, width: int) -> int:
        return 0

    def _sync_reading_card_margins(self) -> None:
        layouts = [
            (getattr(self, "_reading_book_scroll", None), getattr(self, "_reading_book_layout", None)),
            (getattr(self, "_reading_paper_scroll", None), getattr(self, "_reading_paper_layout", None)),
        ]
        for scroll, layout in layouts:
            if scroll is None or layout is None:
                continue
            viewport = scroll.viewport() if hasattr(scroll, "viewport") else None
            width = viewport.width() if viewport is not None else scroll.width()
            h_margin = self._calc_card_side_margin(int(width))
            layout.setContentsMargins(h_margin, 0, h_margin, 0)

    def _get_book_children(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        children = node.get("children")
        if isinstance(children, list) and children:
            return [c for c in children if isinstance(c, dict)]
        sections = node.get("sections")
        if isinstance(sections, list):
            return [c for c in sections if isinstance(c, dict)]
        return children if isinstance(children, list) else []

    def calculate_chapter_time_spent(self, chapter: dict[str, Any]) -> int:
        children = self._get_book_children(chapter)
        if children:
            return sum(self.calculate_chapter_time_spent(child) for child in children if isinstance(child, dict))
        return int(chapter.get("time_spent", 0) or 0)

    def calculate_book_time_spent(self, book_info: dict[str, Any]) -> int:
        total = 0
        for chap in book_info.get("tree", []) or []:
            if isinstance(chap, dict):
                total += self.calculate_chapter_time_spent(chap)
        return total

    def build_reading_estimate_text(self, book_info: dict[str, Any]) -> str:
        total_pages = int(book_info.get("total_pages", 0) or 0)
        read_pages = int(book_info.get("read_pages", 0) or 0)
        time_spent = int(book_info.get("time_spent", 0) or 0)
        if total_pages <= 0:
            return "预计还需: 未知"
        if read_pages <= 0 or time_spent <= 0:
            return "预计还需: 请先阅读几页以生成预测"
        remaining = total_pages - read_pages
        if remaining <= 0:
            return "预计还需: 已读完"
        minutes_per_page = time_spent / max(read_pages, 1)
        estimate = remaining * minutes_per_page
        return f"预计还需: {self.format_minutes(estimate)}"

    def sync_reading_book_progress(self, book_info: dict[str, Any]) -> None:
        tree = book_info.get("tree", [])
        if not isinstance(tree, list):
            return

        def _sync_node(node: dict[str, Any]) -> None:
            children = self._get_book_children(node)
            if not children:
                return
            for child in children:
                if isinstance(child, dict):
                    _sync_node(child)
            node["done"] = all(ch.get("done") for ch in children if isinstance(ch, dict))
            node["pages_count"] = sum(int(ch.get("pages_count", 0) or 0) for ch in children if isinstance(ch, dict))
            node["time_spent"] = sum(int(ch.get("time_spent", 0) or 0) for ch in children if isinstance(ch, dict))

        for chap in tree:
            if isinstance(chap, dict):
                _sync_node(chap)

        book_info["read_pages"] = compute_read_pages_from_tree(tree)
        book_info["time_spent"] = self.calculate_book_time_spent(book_info)
        total_pages = int(book_info.get("total_pages", 0) or 0)
        if total_pages and int(book_info.get("read_pages", 0) or 0) > total_pages:
            book_info["read_pages"] = total_pages

    def export_reading_report(self) -> None:
        import csv

        data_dir = app_config.get("data_dir")
        if not data_dir or not os.path.isdir(data_dir):
            QtWidgets.QMessageBox.warning(self.reading_window or self, "导出失败", "未找到数据目录，无法导出。")
            return

        file_name = f"阅读进度报表_{datetime.now().strftime('%Y%m%d')}.csv"
        file_path = os.path.join(data_dir, file_name)

        data = global_data or {}
        books = data.get("reading_books", {})
        if not isinstance(books, dict) or not books:
            QtWidgets.QMessageBox.information(self.reading_window or self, "暂无数据", "当前没有可导出的阅读数据。")
            return

        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "书名",
                        "作者",
                        "版本",
                        "总页数",
                        "已读页数",
                        "进度",
                        "章节",
                        "小节",
                        "章节页数",
                        "小节页数",
                        "章节状态",
                        "小节状态",
                        "章节耗时(分钟)",
                        "小节耗时(分钟)",
                        "书籍累计耗时(分钟)",
                    ]
                )

                for book_title in sorted(books.keys()):
                    book_info = books.get(book_title)
                    if not isinstance(book_info, dict):
                        continue
                    self.sync_reading_book_progress(book_info)

                    author = book_info.get("author", "")
                    version = book_info.get("version", "")
                    total_pages = int(book_info.get("total_pages", 0) or 0)
                    read_pages = int(book_info.get("read_pages", 0) or 0)
                    progress_pct = (read_pages / total_pages * 100) if total_pages > 0 else 0
                    book_time = int(book_info.get("time_spent", 0) or 0)

                    def _write_node_rows(
                        node: dict[str, Any],
                        path: list[str],
                        chapter_meta: dict[str, Any] | None = None,
                    ) -> None:
                        if not isinstance(node, dict):
                            return
                        title = str(node.get("title", "") or "").strip()
                        if not title:
                            return

                        node_pages = int(node.get("pages_count", 0) or 0)
                        node_done = bool(node.get("done"))
                        node_time = self.calculate_chapter_time_spent(node)

                        if chapter_meta is None:
                            chapter_meta = {
                                "title": title,
                                "pages": node_pages,
                                "done": node_done,
                                "time": node_time,
                            }
                            writer.writerow(
                                [
                                    book_title,
                                    author,
                                    version,
                                    total_pages,
                                    read_pages,
                                    f"{progress_pct:.1f}%",
                                    chapter_meta["title"],
                                    "",
                                    chapter_meta["pages"],
                                    "",
                                    "已读" if chapter_meta["done"] else "未读",
                                    "",
                                    chapter_meta["time"],
                                    "",
                                    book_time,
                                ]
                            )
                        else:
                            section_path = " / ".join(path[1:]) if len(path) > 1 else title
                            writer.writerow(
                                [
                                    book_title,
                                    author,
                                    version,
                                    total_pages,
                                    read_pages,
                                    f"{progress_pct:.1f}%",
                                    chapter_meta["title"],
                                    section_path,
                                    chapter_meta["pages"],
                                    node_pages,
                                    "已读" if chapter_meta["done"] else "未读",
                                    "已读" if node_done else "未读",
                                    chapter_meta["time"],
                                    node_time,
                                    book_time,
                                ]
                            )

                        for child in self._get_book_children(node):
                            child_title = str(child.get("title", "") or "").strip()
                            if not child_title:
                                continue
                            _write_node_rows(child, path + [child_title], chapter_meta)

                    for chap in book_info.get("tree", []) or []:
                        if not isinstance(chap, dict):
                            continue
                        chap_title = str(chap.get("title", "") or "").strip()
                        if not chap_title:
                            continue
                        _write_node_rows(chap, [chap_title])

            QtWidgets.QMessageBox.information(self.reading_window or self, "导出成功", f"阅读报表已导出到:\n{file_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.reading_window or self, "导出失败", f"写入失败: {e}")

    def add_reading_task_from_meta(self, meta: dict[str, Any], cat: str | None = None) -> None:
        data = global_data
        if data is None:
            return
        book_title = str(meta.get("book", "") or "")
        pages = int(meta.get("pages", 0) or 0)

        path = meta.get("path") if isinstance(meta.get("path"), list) else []
        if not path:
            chapter_title = str(meta.get("chapter", "") or "")
            section_title = str(meta.get("section", "") or "")
            if chapter_title:
                path = [chapter_title]
                if section_title:
                    path.append(section_title)

        if not book_title or not path:
            return
        if meta.get("has_children"):
            QtWidgets.QMessageBox.warning(
                self.reading_window or self,
                "请选择子条目",
                "该条目包含子目录，请在最末级条目上右键加入任务。",
            )
            return

        task_text = f"阅读：{book_title} | " + " / ".join(path)

        if self.is_duplicate_task_text(task_text):
            QtWidgets.QMessageBox.warning(self.reading_window or self, "重复任务", "该阅读任务已在今日清单中。")
            return

        chosen_cat = str(cat or "科研").strip()
        if chosen_cat not in ("科研", "理论/技术"):
            chosen_cat = "科研"

        data.setdefault("today_structured_tasks", {}).setdefault(chosen_cat, []).append(
            {
                "text": task_text,
                "done": False,
                "req_time": 0,
                "meta_book": book_title,
                "meta_path": path,
                "meta_chapter": path[0] if path else "",
                "meta_section": path[1] if len(path) > 1 else "",
                "meta_pages": pages,
            }
        )
        save_data()
        self.update_task_buttons()
        self.update_task_status_label()
        self.refresh_task_viewer_if_open()

        if data.get("today_task_submitted"):
            QtWidgets.QMessageBox.information(self.reading_window or self, "已加入", "阅读任务已加入今日清单，可在任务看板中打卡。")
        else:
            QtWidgets.QMessageBox.information(self.reading_window or self, "已加入", "阅读任务已加入今日清单，请到【制定每日清单】中提交后使用。")

    def add_literature_task_from_meta(self, meta: dict[str, Any], cat: str | None = None) -> None:
        data = global_data
        if data is None:
            return
        paper_title = str(meta.get("paper", "") or "")
        phase_title = str(meta.get("phase", "") or "")
        task_title = str(meta.get("task", "") or "")
        sub_title = str(meta.get("subtask", "") or "")
        hours = float(meta.get("hours", 0) or 0)

        if not paper_title or not sub_title:
            return

        task_text = f"文献导读：{paper_title} | {phase_title} / {task_title} / {sub_title}"

        if self.is_duplicate_task_text(task_text):
            QtWidgets.QMessageBox.warning(self.reading_window or self, "重复任务", "该导读任务已在今日清单中。")
            return

        chosen_cat = str(cat or "科研").strip()
        if chosen_cat not in ("科研", "理论/技术"):
            chosen_cat = "科研"

        data.setdefault("today_structured_tasks", {}).setdefault(chosen_cat, []).append(
            {
                "text": task_text,
                "done": False,
                "req_time": 0,
                "meta_paper": paper_title,
                "meta_phase": phase_title,
                "meta_task": task_title,
                "meta_subtask": sub_title,
                "meta_hours": hours,
            }
        )
        save_data()
        self.update_task_buttons()
        self.update_task_status_label()
        self.refresh_task_viewer_if_open()

        if data.get("today_task_submitted"):
            QtWidgets.QMessageBox.information(self.reading_window or self, "已加入", "导读任务已加入今日清单，可在任务看板中打卡。")
        else:
            QtWidgets.QMessageBox.information(self.reading_window or self, "已加入", "导读任务已加入今日清单，请到【制定每日清单】中提交后使用。")

    def get_study_minutes_for_task(self, task_text: str) -> int:
        data = global_data or {}
        total = 0
        for item in data.get("study_history", []) if isinstance(data.get("study_history"), list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("task") != task_text:
                continue
            total += int(item.get("study_time", item.get("duration", 0)) or 0)
        return total

    def apply_literature_task_status(self, task_item: dict[str, Any], is_done: bool) -> bool:
        paper_title = task_item.get("meta_paper")
        if not paper_title:
            return False

        data = global_data or {}
        papers = data.get("reading_papers", {})
        paper_info = papers.get(paper_title) if isinstance(papers, dict) else None
        if not isinstance(paper_info, dict):
            return False

        phase_title = task_item.get("meta_phase") or ""
        task_title = task_item.get("meta_task") or ""
        sub_title = task_item.get("meta_subtask") or ""
        if not task_title or not sub_title:
            return False

        target_sub: dict[str, Any] | None = None
        for phase in paper_info.get("phases", []) or []:
            if not isinstance(phase, dict):
                continue
            if phase_title and phase.get("phase") != phase_title:
                continue
            for task in phase.get("tasks", []) or []:
                if not isinstance(task, dict):
                    continue
                if task.get("title") != task_title:
                    continue
                for sub in task.get("subtasks", []) or []:
                    if isinstance(sub, dict) and sub.get("title") == sub_title:
                        target_sub = sub
                        break
                if target_sub is not None:
                    break
            if target_sub is not None:
                break

        if target_sub is None:
            return False

        target_sub["done"] = bool(is_done)
        if is_done:
            minutes = self.get_study_minutes_for_task(str(task_item.get("text", "") or ""))
            if minutes > 0:
                existing = int(target_sub.get("time_spent", 0) or 0)
                if minutes > existing:
                    target_sub["time_spent"] = minutes
        else:
            target_sub["time_spent"] = 0

        self.sync_literature_progress(paper_info)
        return True

    def apply_reading_task_status(self, task_item: dict[str, Any], is_done: bool) -> bool:
        book_title = task_item.get("meta_book")
        if not book_title:
            return False

        data = global_data or {}
        books = data.get("reading_books", {})
        book_info = books.get(book_title) if isinstance(books, dict) else None
        if not isinstance(book_info, dict):
            return False

        path = task_item.get("meta_path") if isinstance(task_item.get("meta_path"), list) else []
        if not path:
            chapter_title = task_item.get("meta_chapter") or ""
            section_title = task_item.get("meta_section") or ""
            if not chapter_title:
                return False
            path = [str(chapter_title)]
            if section_title:
                path.append(str(section_title))

        def _find_node(nodes: list[dict[str, Any]], path_parts: list[str]) -> dict[str, Any] | None:
            if not path_parts:
                return None
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("title") != path_parts[0]:
                    continue
                if len(path_parts) == 1:
                    return node
                return _find_node(self._get_book_children(node), path_parts[1:])
            return None

        target_node = _find_node(book_info.get("tree", []) or [], path)
        if target_node is None:
            return False

        minutes = self.get_study_minutes_for_task(str(task_item.get("text", "") or ""))
        children = self._get_book_children(target_node)
        if children:
            leaves: list[dict[str, Any]] = []

            def _collect_leaves(node: dict[str, Any]) -> None:
                kids = self._get_book_children(node)
                if kids:
                    for child in kids:
                        if isinstance(child, dict):
                            _collect_leaves(child)
                else:
                    leaves.append(node)

            _collect_leaves(target_node)
            if not leaves:
                return False
            for leaf in leaves:
                leaf["done"] = bool(is_done)
                if not is_done:
                    leaf["time_spent"] = 0
            if is_done and minutes > 0:
                target_leaf = leaves[0]
                existing = int(target_leaf.get("time_spent", 0) or 0)
                if minutes > existing:
                    target_leaf["time_spent"] = minutes
        else:
            target_node["done"] = bool(is_done)
            if is_done:
                if minutes > 0:
                    existing = int(target_node.get("time_spent", 0) or 0)
                    if minutes > existing:
                        target_node["time_spent"] = minutes
            else:
                target_node["time_spent"] = 0

        self.sync_reading_book_progress(book_info)
        return True

    # ===================== charts =====================
