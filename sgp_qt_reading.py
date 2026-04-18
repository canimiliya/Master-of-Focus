from __future__ import annotations
from datetime import datetime
from typing import Any
import json
import os

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import app_config, calculate_book_pages, compute_read_pages_from_tree, global_data, save_data


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


class ReadingMixin:
    def show_reading_json_prompt_help(self) -> None:
        parent = self.reading_window or self

        prompt_text = (
            "你是“目录截图 → 正文目录 JSON”生成器。输入是目录截图（可多张，按目录顺序）。输出必须是可直接保存为 .json 的“纯 JSON 文本”（不要解释、不要 Markdown、不要代码块标记）。\n\n"
            "输出格式（严格遵守）：\n"
            "- 顶层：JSON 数组\n"
            "- 每项：{\"title\": 字符串, \"page\": 整数}\n"
            "- 必须在最后额外包含：{\"title\":\"全书结束\",\"page\": 正文最后一页页码整数}\n\n"
            "抽取规则：\n"
            "1) 按截图从上到下的目录顺序输出，不要自行排序。\n"
            "2) page：取每行最右侧/最后出现的阿拉伯数字；如果是范围(如 12-15 / 12~15 / 12—15)，取起始页 12；page 必须输出为整数。\n"
            "3) title：只保留目录文字，去掉点点点/引导符/多余空白/页码。\n\n"
            "层级规则（用于章节/小节）：\n"
            "- 章节：title 不含“§”\n"
            "- 小节：在 title 最前面加“§”，并且小节必须紧跟在所属章节后面出现。\n\n"
            "正文过滤规则（去掉与正文无关的部分）：\n"
            "- 若目录中出现明显的“非正文板块”（例如：附录、参考文献/参考资料、索引、致谢、后记、答案/习题答案、解答、解析等），从该条开始及其后全部不输出到 JSON。\n"
            "- 同时将“全书结束”的 page 设为：该条非正文板块的起始页码 - 1（表示正文结束页）。\n\n"
            "不确定性处理：\n"
            "- 如果无法可靠读出某条目页码，或无法确定“正文结束页码”，不要猜；先向用户提问要缺失的页码信息，得到后再输出最终 JSON。\n"
        )

        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("📚 目录截图 → JSON 操作说明")
        dialog.resize(720, 560)
        dialog.setModal(True)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        steps = QtWidgets.QLabel(
            "使用方法：\n"
            "1) 将书籍目录页截图（确保包含标题和页码，按目录顺序）。\n"
            "2) 把目录截图 + 下方提示词发给支持图片的推理大模型。\n"
            "3) 让它输出“纯 JSON 文本”，保存为 .json 文件。\n"
            "4) 回到本窗口：拖拽该 .json 到上方区域，或点击【选择 JSON 文件导入】。"
        )
        steps.setWordWrap(True)
        root.addWidget(steps)

        status_label = QtWidgets.QLabel("提示：点击【复制提示词】后直接粘贴到大模型对话框即可。")
        status_label.setStyleSheet("color:#666666")
        status_label.setWordWrap(True)
        root.addWidget(status_label)

        edit = QtWidgets.QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(prompt_text)
        root.addWidget(edit, 1)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btn_copy = QtWidgets.QPushButton("复制提示词")
        btn_close = QtWidgets.QPushButton("关闭")
        btns.addWidget(btn_copy)
        btns.addWidget(btn_close)
        root.addLayout(btns)

        def copy_prompt() -> None:
            QtWidgets.QApplication.clipboard().setText(prompt_text)
            status_label.setText("提示词已复制到剪贴板。")

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
                self.reading_card_container = None
                self.reading_tree_metas = {}

        win.finished.connect(_on_finished)

        root = QtWidgets.QVBoxLayout(win)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        class _BookDropLabel(QtWidgets.QLabel):
            def __init__(self, on_files):
                super().__init__("📥 将书籍 JSON 文件拖拽到此处导入")
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

        def import_paths(paths: list[str]) -> None:
            for file_path in paths:
                if not file_path.lower().endswith(".json"):
                    QtWidgets.QMessageBox.warning(win, "格式错误", "请拖拽标准的 .json 文件！")
                    continue
                self.open_book_import_dialog(file_path)

        drop_area = _BookDropLabel(import_paths)
        root.addWidget(drop_area)

        btn_row = QtWidgets.QHBoxLayout()
        btn_import = QtWidgets.QPushButton("选择 JSON 文件导入")
        btn_export = QtWidgets.QPushButton("导出阅读报表")
        btn_help = QtWidgets.QPushButton("操作说明")
        btn_row.addWidget(btn_import)
        btn_row.addWidget(btn_export)
        btn_row.addWidget(btn_help)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        container = QtWidgets.QWidget()
        container.setStyleSheet("background: transparent;")
        scroll.setWidget(container)
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(10)

        self.reading_card_container = container
        self._reading_card_layout = container_layout
        self.reading_tree_metas = {}

        btn_import.clicked.connect(self.open_book_file_dialog)
        btn_export.clicked.connect(self.export_reading_report)
        btn_help.clicked.connect(self.show_reading_json_prompt_help)

        win.show()
        # Ensure the first render happens after Qt processes the show event.
        QtCore.QTimer.singleShot(0, self.refresh_reading_ui)

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

    def refresh_reading_ui(self) -> None:
        win = self.reading_window
        container = getattr(self, "reading_card_container", None)
        layout = getattr(self, "_reading_card_layout", None)
        if win is None or container is None or layout is None:
            return

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
            header_btn.setChecked(True)
            header_btn.setArrowType(QtCore.Qt.ArrowType.DownArrow)
            header_btn.setFont(self._font(size=11, bold=True))
            header_btn.setProperty("tone", tone)
            try:
                header_btn.style().unpolish(header_btn)
                header_btn.style().polish(header_btn)
            except Exception:
                pass
            header_btn.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            card_lay.addWidget(header_btn)

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
            try:
                hdr = tree.header()
                hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
                hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            except Exception:
                pass
            card_lay.addWidget(tree)

            def _toggle_tree(expanded: bool, tr: QtWidgets.QTreeWidget = tree, btn: QtWidgets.QToolButton = header_btn) -> None:
                tr.setVisible(expanded)
                btn.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)

            header_btn.toggled.connect(_toggle_tree)

            def on_menu(pos: QtCore.QPoint, tr: QtWidgets.QTreeWidget = tree) -> None:
                item = tr.itemAt(pos)
                if item is None:
                    return
                meta = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(meta, dict) or meta.get("node_type") == "book":
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

            for chap in book_info.get("tree", []) or []:
                if not isinstance(chap, dict):
                    continue
                chap_title = str(chap.get("title", "") or "")
                chap_pages = int(chap.get("pages_count", 0) or 0)
                chap_done = bool(chap.get("done"))
                chap_status = "已读" if chap_done else "未读"
                chap_item = QtWidgets.QTreeWidgetItem([chap_title, f"{chap_pages}页", chap_status])
                chap_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole,
                    {
                        "node_type": "chapter",
                        "book": book_title,
                        "chapter": chap_title,
                        "pages": chap_pages,
                        "has_sections": bool(chap.get("sections")),
                    },
                )
                set_item_done_style(chap_item, chap_done)
                tree.addTopLevelItem(chap_item)
                chap_item.setExpanded(True)

                for sec in chap.get("sections", []) or []:
                    if not isinstance(sec, dict):
                        continue
                    sec_title = str(sec.get("title", "") or "")
                    sec_pages = int(sec.get("pages_count", 0) or 0)
                    sec_done = bool(sec.get("done"))
                    sec_status = "已读" if sec_done else "未读"
                    sec_item = QtWidgets.QTreeWidgetItem([sec_title, f"{sec_pages}页", sec_status])
                    sec_item.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole,
                        {
                            "node_type": "section",
                            "book": book_title,
                            "chapter": chap_title,
                            "section": sec_title,
                            "pages": sec_pages,
                        },
                    )
                    set_item_done_style(sec_item, sec_done)
                    chap_item.addChild(sec_item)

            layout.addWidget(card)

        layout.addStretch(1)

    def calculate_chapter_time_spent(self, chapter: dict[str, Any]) -> int:
        sections = chapter.get("sections", []) or []
        if sections:
            return sum(int(sec.get("time_spent", 0) or 0) for sec in sections if isinstance(sec, dict))
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
        for chap in tree:
            if not isinstance(chap, dict):
                continue
            sections = chap.get("sections", [])
            if sections:
                chap["done"] = all(sec.get("done") for sec in sections if isinstance(sec, dict))
                chap["pages_count"] = sum(int(sec.get("pages_count", 0) or 0) for sec in sections if isinstance(sec, dict))
                chap["time_spent"] = sum(int(sec.get("time_spent", 0) or 0) for sec in sections if isinstance(sec, dict))

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

                    for chap in book_info.get("tree", []) or []:
                        if not isinstance(chap, dict):
                            continue
                        chap_title = chap.get("title", "")
                        chap_pages = int(chap.get("pages_count", 0) or 0)
                        chap_done = "已读" if chap.get("done") else "未读"
                        chap_time = self.calculate_chapter_time_spent(chap)

                        writer.writerow(
                            [
                                book_title,
                                author,
                                version,
                                total_pages,
                                read_pages,
                                f"{progress_pct:.1f}%",
                                chap_title,
                                "",
                                chap_pages,
                                "",
                                chap_done,
                                "",
                                chap_time,
                                "",
                                book_time,
                            ]
                        )

                        for sec in chap.get("sections", []) or []:
                            if not isinstance(sec, dict):
                                continue
                            sec_title = sec.get("title", "")
                            sec_pages = int(sec.get("pages_count", 0) or 0)
                            sec_done = "已读" if sec.get("done") else "未读"
                            sec_time = int(sec.get("time_spent", 0) or 0)
                            writer.writerow(
                                [
                                    book_title,
                                    author,
                                    version,
                                    total_pages,
                                    read_pages,
                                    f"{progress_pct:.1f}%",
                                    chap_title,
                                    sec_title,
                                    chap_pages,
                                    sec_pages,
                                    chap_done,
                                    sec_done,
                                    chap_time,
                                    sec_time,
                                    book_time,
                                ]
                            )

            QtWidgets.QMessageBox.information(self.reading_window or self, "导出成功", f"阅读报表已导出到:\n{file_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.reading_window or self, "导出失败", f"写入失败: {e}")

    def add_reading_task_from_meta(self, meta: dict[str, Any], cat: str | None = None) -> None:
        data = global_data
        if data is None:
            return
        book_title = str(meta.get("book", "") or "")
        chapter_title = str(meta.get("chapter", "") or "")
        section_title = str(meta.get("section", "") or "")
        pages = int(meta.get("pages", 0) or 0)

        if not book_title or not chapter_title:
            return
        if meta.get("node_type") == "chapter" and meta.get("has_sections"):
            QtWidgets.QMessageBox.warning(self.reading_window or self, "请选择小节", "该章节包含小节，请在小节上右键加入任务。")
            return

        task_text = f"阅读：{book_title} | {chapter_title}"
        if section_title:
            task_text = f"阅读：{book_title} | {chapter_title} / {section_title}"

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
                "meta_chapter": chapter_title,
                "meta_section": section_title,
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

    def apply_reading_task_status(self, task_item: dict[str, Any], is_done: bool) -> bool:
        book_title = task_item.get("meta_book")
        if not book_title:
            return False

        data = global_data or {}
        books = data.get("reading_books", {})
        book_info = books.get(book_title) if isinstance(books, dict) else None
        if not isinstance(book_info, dict):
            return False

        chapter_title = task_item.get("meta_chapter") or ""
        section_title = task_item.get("meta_section") or ""
        if not chapter_title:
            return False

        target_node: dict[str, Any] | None = None
        for chap in book_info.get("tree", []) or []:
            if not isinstance(chap, dict):
                continue
            if chap.get("title") != chapter_title:
                continue
            if section_title:
                for sec in chap.get("sections", []) or []:
                    if isinstance(sec, dict) and sec.get("title") == section_title:
                        target_node = sec
                        break
            else:
                target_node = chap
            if target_node is not None:
                break

        if target_node is None:
            return False

        target_node["done"] = bool(is_done)
        if is_done:
            minutes = self.get_study_minutes_for_task(str(task_item.get("text", "") or ""))
            if minutes > 0:
                existing = int(target_node.get("time_spent", 0) or 0)
                if minutes > existing:
                    target_node["time_spent"] = minutes
        else:
            target_node["time_spent"] = 0

        self.sync_reading_book_progress(book_info)
        return True

    # ===================== charts =====================
