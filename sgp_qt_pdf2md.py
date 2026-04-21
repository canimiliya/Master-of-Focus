from __future__ import annotations

import os
import re
import sys
import traceback
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import app_config, save_app_config


class _DropListWidget(QtWidgets.QListWidget):
    files_dropped = QtCore.Signal(list)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(QtCore.Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            paths: list[str] = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p and os.path.isfile(p) and p.lower().endswith(".pdf"):
                    paths.append(p)
                elif p and os.path.isdir(p):
                    for name in os.listdir(p):
                        if name.lower().endswith(".pdf"):
                            paths.append(os.path.join(p, name))
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class ApiSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🔑 API 设置")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._setup_ui()
        self._load_settings()

    @staticmethod
    def _mk_btn(text: str, bg: str, fg: str, w: int = 0, h: int = 36) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        b.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        b.setMinimumHeight(h)
        if w:
            b.setMinimumWidth(w)
        b.setFont(Pdf2MdWindow._font(size=11, bold=True))
        b.setStyleSheet(
            "QPushButton{" f"background:{bg};color:{fg};border:none;border-radius:6px;padding:6px 14px;" "}"
            "QPushButton:hover{opacity:0.9;}"
        )
        return b

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        mineru_group = QtWidgets.QGroupBox("MinerU API (PDF解析)")
        mineru_group.setStyleSheet(
            "QGroupBox{font-weight:bold;font-size:12px;color:#FF69B4;"
            "border:2px solid #FFB6C1;border-radius:8px;margin-top:10px;padding-top:16px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;}"
        )
        mineru_layout = QtWidgets.QVBoxLayout(mineru_group)
        mineru_layout.setSpacing(8)

        m_row = QtWidgets.QHBoxLayout()
        m_label = QtWidgets.QLabel("Token：")
        m_label.setStyleSheet("font-size:12px;")
        m_label.setFixedWidth(55)
        self._edit_mineru_token = QtWidgets.QLineEdit()
        self._edit_mineru_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._edit_mineru_token.setPlaceholderText("MinerU API Token (JWT)")
        self._edit_mineru_token.setStyleSheet("QLineEdit{border:1px solid #E5E7EB;border-radius:4px;padding:6px;font-size:12px;}")
        self._btn_toggle_m = self._mk_btn("👁", "#E5E7EB", "#333", w=36, h=30)
        m_row.addWidget(m_label)
        m_row.addWidget(self._edit_mineru_token, 1)
        m_row.addWidget(self._btn_toggle_m)
        mineru_layout.addLayout(m_row)

        layout.addWidget(mineru_group)

        llm_group = QtWidgets.QGroupBox("翻译 LLM API (SiliconFlow)")
        llm_group.setStyleSheet(
            "QGroupBox{font-weight:bold;font-size:12px;color:#20B2AA;"
            "border:2px solid #87CEFA;border-radius:8px;margin-top:10px;padding-top:16px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;}"
        )
        llm_layout = QtWidgets.QVBoxLayout(llm_group)
        llm_layout.setSpacing(8)

        k_row = QtWidgets.QHBoxLayout()
        k_label = QtWidgets.QLabel("Key：")
        k_label.setStyleSheet("font-size:12px;")
        k_label.setFixedWidth(55)
        self._edit_llm_key = QtWidgets.QLineEdit()
        self._edit_llm_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._edit_llm_key.setPlaceholderText("SiliconFlow API Key")
        self._edit_llm_key.setStyleSheet("QLineEdit{border:1px solid #E5E7EB;border-radius:4px;padding:6px;font-size:12px;}")
        self._btn_toggle_k = self._mk_btn("👁", "#E5E7EB", "#333", w=36, h=30)
        k_row.addWidget(k_label)
        k_row.addWidget(self._edit_llm_key, 1)
        k_row.addWidget(self._btn_toggle_k)
        llm_layout.addLayout(k_row)

        mod_row = QtWidgets.QHBoxLayout()
        mod_label = QtWidgets.QLabel("模型：")
        mod_label.setStyleSheet("font-size:12px;")
        mod_label.setFixedWidth(55)
        self._edit_llm_model = QtWidgets.QLineEdit()
        self._edit_llm_model.setPlaceholderText("如: Pro/deepseek-ai/DeepSeek-V3.2")
        self._edit_llm_model.setStyleSheet("QLineEdit{border:1px solid #E5E7EB;border-radius:4px;padding:6px;font-size:12px;}")
        mod_row.addWidget(mod_label)
        mod_row.addWidget(self._edit_llm_model, 1)
        llm_layout.addLayout(mod_row)

        base_row = QtWidgets.QHBoxLayout()
        base_label = QtWidgets.QLabel("Base：")
        base_label.setStyleSheet("font-size:12px;")
        base_label.setFixedWidth(55)
        self._edit_llm_base = QtWidgets.QLineEdit()
        self._edit_llm_base.setPlaceholderText("https://api.siliconflow.cn/v1")
        self._edit_llm_base.setStyleSheet("QLineEdit{border:1px solid #E5E7EB;border-radius:4px;padding:6px;font-size:12px;}")
        base_row.addWidget(base_label)
        base_row.addWidget(self._edit_llm_base, 1)
        llm_layout.addLayout(base_row)

        layout.addWidget(llm_group)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch()
        ok_btn = self._mk_btn("✅ 保存并关闭", "#FF69B4", "white", w=140, h=38)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)

        self._btn_toggle_m.clicked.connect(self._on_toggle_m)
        self._btn_toggle_k.clicked.connect(self._on_toggle_k)
        ok_btn.clicked.connect(self.accept)

    def _on_toggle_m(self) -> None:
        if self._edit_mineru_token.echoMode() == QtWidgets.QLineEdit.EchoMode.Password:
            self._edit_mineru_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
        else:
            self._edit_mineru_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

    def _on_toggle_k(self) -> None:
        if self._edit_llm_key.echoMode() == QtWidgets.QLineEdit.EchoMode.Password:
            self._edit_llm_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
        else:
            self._edit_llm_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

    def _load_settings(self) -> None:
        cfg = app_config.get("pdf2md", {})
        if not isinstance(cfg, dict):
            cfg = {}
        self._edit_mineru_token.setText(cfg.get("mineru_token", ""))
        self._edit_llm_key.setText(cfg.get("llm_key", ""))
        self._edit_llm_model.setText(cfg.get("llm_model", "Pro/deepseek-ai/DeepSeek-V3.2"))
        self._edit_llm_base.setText(cfg.get("llm_base", "https://api.siliconflow.cn/v1"))

    def save_settings(self) -> None:
        cfg = {
            "mineru_token": self._edit_mineru_token.text().strip(),
            "llm_key": self._edit_llm_key.text().strip(),
            "llm_model": self._edit_llm_model.text().strip(),
            "llm_base": self._edit_llm_base.text().strip(),
        }
        app_config["pdf2md"] = cfg
        save_app_config()


class _StdoutRedirector:
    def __init__(self, signal: QtCore.Signal) -> None:
        self._signal = signal
        self._buffer = ""

    def write(self, text: str) -> int:
        if text:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.rstrip()
                if line:
                    self._signal.emit(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._signal.emit(self._buffer.rstrip())
            self._buffer = ""


class BatchWorker(QtCore.QThread):
    log_signal = QtCore.Signal(str)
    progress_signal = QtCore.Signal(int, str)
    finished_signal = QtCore.Signal(bool)
    error_signal = QtCore.Signal(str)

    def __init__(
        self,
        pdf_list: list[str],
        output_dir: str,
        mineru_token: str,
        llm_key: str,
        llm_base: str,
        llm_model: str,
        model_version: str,
    ) -> None:
        super().__init__()
        self._pdf_list = pdf_list
        self._output_dir = output_dir
        self._mineru_token = mineru_token
        self._llm_key = llm_key
        self._llm_base = llm_base
        self._llm_model = llm_model
        self._model_version = model_version
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from pdf2md_poc import (
            detect_language,
            mineru_parse_local_file,
            mineru_parse_url,
            translate_to_chinese,
        )

        _redirect = _StdoutRedirector(self.log_signal)
        _old_stdout = sys.stdout
        sys.stdout = _redirect

        try:
            os.makedirs(self._output_dir, exist_ok=True)
            total = len(self._pdf_list)

            for idx, pdf_source in enumerate(self._pdf_list):
                if self._cancelled:
                    self.log_signal.emit("⚠️ 处理已取消")
                    break

                self.log_signal.emit(f"\n{'='*50}")
                self.log_signal.emit(f"📄 [{idx+1}/{total}] {os.path.basename(pdf_source)}")
                self.log_signal.emit(f"{'='*50}")

                pct_base = int(idx / total * 100)
                pct_next = int((idx + 1) / total * 100)
                self.progress_signal.emit(pct_base, f"[{idx+1}/{total}] 准备中...")

                try:
                    is_url = pdf_source.startswith("http://") or pdf_source.startswith("https://")

                    self.log_signal.emit("⏳ MinerU 解析中...")
                    self.progress_signal.emit(pct_base, f"[{idx+1}/{total}] MinerU 解析中...")

                    if is_url:
                        markdown = mineru_parse_url(pdf_source, self._mineru_token, self._model_version, self._output_dir)
                    else:
                        if not os.path.isfile(pdf_source):
                            self.log_signal.emit(f"❌ 文件不存在: {pdf_source}")
                            continue
                        file_size = os.path.getsize(pdf_source)
                        if file_size > 200 * 1024 * 1024:
                            self.log_signal.emit(f"❌ 文件超过200MB限制 ({file_size/1024/1024:.1f}MB)")
                            continue
                        markdown = mineru_parse_local_file(pdf_source, self._mineru_token, self._model_version, self._output_dir)

                    self.log_signal.emit(f"✅ MinerU 解析完成, Markdown长度: {len(markdown)}")

                    lang = detect_language(markdown)
                    is_chinese = lang == "zh"
                    self.log_signal.emit(f"🔍 语言检测: {'中文' if is_chinese else '英文'}")

                    basename = os.path.splitext(os.path.basename(pdf_source))[0]
                    basename = re.sub(r'[^\w\-.]', '_', basename)
                    if basename.startswith("_"):
                        basename = basename.lstrip("_")
                    if not basename:
                        basename = f"output_{idx}"

                    if is_chinese:
                        out_path = os.path.join(self._output_dir, f"{basename}.md")
                        with open(out_path, "w", encoding="utf-8") as f:
                            f.write(markdown)
                        self.log_signal.emit(f"💾 中文版已保存: {basename}.md")
                    else:
                        en_path = os.path.join(self._output_dir, f"{basename}.md")
                        with open(en_path, "w", encoding="utf-8") as f:
                            f.write(markdown)
                        self.log_signal.emit(f"💾 英文版已保存: {basename}.md")

                        if self._cancelled:
                            continue

                        self.log_signal.emit(f"🔄 正在翻译 ({self._llm_model})...")
                        translate_pct_start = pct_base + int((pct_next - pct_base) * 0.3)
                        self.progress_signal.emit(translate_pct_start, f"[{idx+1}/{total}] 翻译中...")

                        zh_markdown = translate_to_chinese(markdown, self._llm_key, self._llm_base, self._llm_model)

                        zh_path = os.path.join(self._output_dir, f"{basename}_zh.md")
                        with open(zh_path, "w", encoding="utf-8") as f:
                            f.write(zh_markdown)
                        self.log_signal.emit(f"💾 中文翻译版已保存: {basename}_zh.md")

                    self.progress_signal.emit(pct_next, f"[{idx+1}/{total}] ✅ 完成")

                except Exception as e:
                    self.log_signal.emit(f"❌ 处理失败: {e}")
                    traceback.print_exc()
                    continue

            if self._cancelled:
                self.finished_signal.emit(False)
            else:
                self.progress_signal.emit(100, "✅ 全部完成")
                self.log_signal.emit(f"\n🎉 批量处理完成！输出目录: {self._output_dir}")
                self.finished_signal.emit(True)

        except Exception as e:
            self.error_signal.emit(str(e))
            traceback.print_exc()
        finally:
            sys.stdout = _old_stdout


class Pdf2MdWindow(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("📄 批量翻译 / 文本处理")
        self.setMinimumWidth(720)
        self.setMinimumHeight(500)
        self.setModal(False)
        self._running = False
        self._cancelled = False
        self._worker: BatchWorker | None = None
        self._setup_ui()
        self._load_settings()
        self.adjustSize()

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._log_box.clear()
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("0%")
        self._running = False
        self._cancelled = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setText("⏹️ 取消")
        self.adjustSize()

    @staticmethod
    def _font(family: str = "Microsoft YaHei", size: int = 10, bold: bool = False) -> QtGui.QFont:
        f = QtGui.QFont(family)
        f.setPointSize(size)
        f.setBold(bold)
        return f

    @staticmethod
    def _mk_btn(text: str, bg: str, fg: str, w: int = 0, h: int = 36) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        b.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        b.setMinimumHeight(h)
        if w:
            b.setMinimumWidth(w)
        b.setFont(Pdf2MdWindow._font(size=11, bold=True))
        b.setStyleSheet(
            "QPushButton{" f"background:{bg};color:{fg};border:none;border-radius:6px;padding:6px 14px;" "}"
            "QPushButton:disabled{background:#DDDDDD;color:#888888;}"
            "QPushButton:hover{opacity:0.9;}"
        )
        return b

    def _setup_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        header = QtWidgets.QLabel("📄 PDF 批量转 Markdown & 翻译")
        header.setFont(self._font(size=14, bold=True))
        header.setStyleSheet("color:#FF69B4;")
        header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(header)

        desc = QtWidgets.QLabel("将 PDF 论文转为结构化 Markdown，英文论文自动翻译为中文并输出双版本")
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#888888; font-size:11px;")
        desc.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(desc)

        file_group = QtWidgets.QGroupBox(" 📁 文件列表 ")
        file_group.setStyleSheet(
            "QGroupBox{font-weight:bold;font-size:12px;color:#FF69B4;"
            "border:2px solid #FFB6C1;border-radius:8px;margin-top:10px;padding-top:16px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;}"
        )
        file_layout = QtWidgets.QVBoxLayout(file_group)
        file_layout.setSpacing(6)

        self._file_list = _DropListWidget()
        self._file_list.setMinimumHeight(80)
        self._file_list.setStyleSheet(
            "QListWidget{border:1px solid #E5E7EB;border-radius:6px;padding:4px;"
            "font-size:12px;background:#FAFAFA;}"
            "QListWidget::item{padding:4px;border-bottom:1px solid #F0F0F0;}"
            "QListWidget::item:selected{background:#FFE4E1;color:#333;}"
        )
        file_layout.addWidget(self._file_list)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_add = self._mk_btn("➕ 添加文件", "#87CEFA", "white")
        self._btn_add_dir = self._mk_btn("📂 添加文件夹", "#87CEFA", "white")
        self._btn_remove = self._mk_btn("🗑️ 移除选中", "#FFB07C", "black")
        self._btn_clear = self._mk_btn("🧹 清空列表", "#FFB07C", "black")
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_add_dir)
        btn_row.addWidget(self._btn_remove)
        btn_row.addWidget(self._btn_clear)
        btn_row.addStretch()
        file_layout.addLayout(btn_row)

        root.addWidget(file_group)

        output_row = QtWidgets.QHBoxLayout()
        output_row.setSpacing(8)
        out_label = QtWidgets.QLabel("📂 输出目录：")
        out_label.setStyleSheet("font-size:12px;font-weight:bold;color:#FF69B4;")
        self._edit_output_dir = QtWidgets.QLineEdit()
        self._edit_output_dir.setPlaceholderText("选择 Markdown 输出目录...")
        self._edit_output_dir.setStyleSheet(
            "QLineEdit{border:1px solid #E5E7EB;border-radius:4px;padding:6px;font-size:12px;}"
        )
        self._btn_browse_output = self._mk_btn("浏览...", "#B0C4DE", "white", w=70)
        model_label = QtWidgets.QLabel("模型：")
        model_label.setStyleSheet("font-size:12px;")
        self._combo_model = QtWidgets.QComboBox()
        self._combo_model.addItems(["vlm (推荐)", "pipeline"])
        self._combo_model.setStyleSheet(
            "QComboBox{border:1px solid #E5E7EB;border-radius:4px;padding:6px;font-size:12px;}"
        )
        self._btn_api = self._mk_btn("🔑 API 设置", "#DDA0DD", "white", w=110)

        output_row.addWidget(out_label)
        output_row.addWidget(self._edit_output_dir, 2)
        output_row.addWidget(self._btn_browse_output)
        output_row.addSpacing(16)
        output_row.addWidget(model_label)
        output_row.addWidget(self._combo_model, 1)
        output_row.addWidget(self._btn_api)
        root.addLayout(output_row)

        progress_group = QtWidgets.QGroupBox(" 📊 处理进度 ")
        progress_group.setStyleSheet(
            "QGroupBox{font-weight:bold;font-size:12px;color:#20B2AA;"
            "border:2px solid #87CEFA;border-radius:8px;margin-top:10px;padding-top:16px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;}"
        )
        progress_layout = QtWidgets.QVBoxLayout(progress_group)
        progress_layout.setSpacing(6)

        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumHeight(22)
        self._progress_bar.setStyleSheet(
            "QProgressBar{border:1px solid #E5E7EB;border-radius:6px;background:#F0F0F0;"
            "text-align:center;font-size:11px;color:#333;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #FFB6C1,stop:0.5 #FF69B4,stop:1 #FF1493);border-radius:5px;}"
        )
        progress_layout.addWidget(self._progress_bar)

        self._log_box = QtWidgets.QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setMinimumHeight(120)
        self._log_box.setMaximumHeight(180)
        self._log_box.setStyleSheet(
            "QTextEdit{background:#FAFAFA;border:1px solid #E5E7EB;border-radius:6px;"
            "padding:8px;font-family:'Consolas','Microsoft YaHei',monospace;"
            "font-size:11px;color:#374151;}"
        )
        progress_layout.addWidget(self._log_box)

        root.addWidget(progress_group)

        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(10)
        self._btn_start = self._mk_btn("🚀 开始处理", "#FF69B4", "white", w=160, h=42)
        self._btn_cancel = self._mk_btn("⏹️ 取消", "#CCCCCC", "black", w=100, h=42)
        self._btn_cancel.setEnabled(False)
        self._btn_open_dir = self._mk_btn("📂 打开输出目录", "#B0C4DE", "white", w=140, h=42)
        action_row.addStretch()
        action_row.addWidget(self._btn_start)
        action_row.addWidget(self._btn_cancel)
        action_row.addWidget(self._btn_open_dir)
        action_row.addStretch()
        root.addLayout(action_row)

        self._btn_add.clicked.connect(self._on_add_files)
        self._btn_add_dir.clicked.connect(self._on_add_dir)
        self._btn_remove.clicked.connect(self._on_remove_selected)
        self._btn_clear.clicked.connect(self._on_clear_list)
        self._file_list.files_dropped.connect(self._on_files_dropped)
        self._btn_browse_output.clicked.connect(self._on_browse_output)
        self._btn_api.clicked.connect(self._on_open_api_settings)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_open_dir.clicked.connect(self._on_open_output_dir)
        self._edit_output_dir.textChanged.connect(self._save_settings)

    def _load_settings(self) -> None:
        cfg = app_config.get("pdf2md", {})
        if not isinstance(cfg, dict):
            cfg = {}
        self._edit_output_dir.setText(cfg.get("output_dir", ""))
        idx = cfg.get("model_version_idx", 0)
        if 0 <= idx < self._combo_model.count():
            self._combo_model.setCurrentIndex(idx)

    def _save_settings(self) -> None:
        cfg = app_config.get("pdf2md", {})
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["output_dir"] = self._edit_output_dir.text().strip()
        cfg["model_version_idx"] = self._combo_model.currentIndex()
        app_config["pdf2md"] = cfg
        save_app_config()

    def _on_open_api_settings(self) -> None:
        dlg = ApiSettingsDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            dlg.save_settings()

    def _on_add_files(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", "", "PDF 文件 (*.pdf);;所有文件 (*.*)"
        )
        for f in files:
            if not self._file_exists(f):
                self._file_list.addItem(f)

    def _on_add_dir(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "选择包含 PDF 的文件夹")
        if not d:
            return
        for name in os.listdir(d):
            if name.lower().endswith(".pdf"):
                full = os.path.join(d, name)
                if not self._file_exists(full):
                    self._file_list.addItem(full)

    def _file_exists(self, path: str) -> bool:
        for i in range(self._file_list.count()):
            if self._file_list.item(i).text() == path:
                return True
        return False

    def _on_remove_selected(self) -> None:
        rows = sorted(set(i.row() for i in self._file_list.selectedIndexes()), reverse=True)
        for r in rows:
            self._file_list.takeItem(r)

    def _on_clear_list(self) -> None:
        self._file_list.clear()

    def _on_files_dropped(self, paths: list[str]) -> None:
        for p in paths:
            if not self._file_exists(p):
                self._file_list.addItem(p)

    def _on_browse_output(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._edit_output_dir.setText(d)

    def _on_open_output_dir(self) -> None:
        d = self._edit_output_dir.text().strip()
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            QtWidgets.QMessageBox.warning(self, "提示", "输出目录不存在，请先设置。")

    def _log(self, msg: str) -> None:
        self._log_box.append(msg)
        sb = self._log_box.verticalScrollBar()
        sb.setValue(sb.maximum())
        QtWidgets.QApplication.processEvents()

    def _set_progress(self, value: int, text: str = "") -> None:
        self._progress_bar.setValue(value)
        if text:
            self._progress_bar.setFormat(text)
        else:
            self._progress_bar.setFormat(f"{value}%")
        QtWidgets.QApplication.processEvents()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setText("取消中...")
        self._log("⚠️ 用户请求取消...")

    def _on_start(self) -> None:
        if self._running or (self._worker and self._worker.isRunning()):
            return

        pdf_list = [self._file_list.item(i).text() for i in range(self._file_list.count())]
        if not pdf_list:
            QtWidgets.QMessageBox.warning(self, "提示", "请先添加 PDF 文件！")
            return

        mineru_token = app_config.get("pdf2md", {}).get("mineru_token", "").strip()
        if not mineru_token:
            QtWidgets.QMessageBox.warning(self, "提示", "请先点击「🔑 API 设置」配置 MinerU Token！")
            return

        llm_key = app_config.get("pdf2md", {}).get("llm_key", "").strip()
        if not llm_key:
            QtWidgets.QMessageBox.warning(self, "提示", "请先点击「🔑 API 设置」配置翻译 LLM Key！")
            return

        output_dir = self._edit_output_dir.text().strip()
        if not output_dir:
            QtWidgets.QMessageBox.warning(self, "提示", "请设置输出目录！")
            return

        self._running = True
        self._cancelled = False
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._log_box.clear()
        self._set_progress(0, "准备中...")

        self._save_settings()

        model_version = "vlm" if self._combo_model.currentIndex() == 0 else "pipeline"
        llm_cfg = app_config.get("pdf2md", {})
        llm_model = llm_cfg.get("llm_model", "").strip() or "Pro/deepseek-ai/DeepSeek-V3.2"
        llm_base = llm_cfg.get("llm_base", "").strip() or "https://api.siliconflow.cn/v1"

        self._worker = BatchWorker(
            pdf_list, output_dir, mineru_token,
            llm_key, llm_base, llm_model, model_version,
        )
        self._worker.log_signal.connect(self._log)
        self._worker.progress_signal.connect(self._set_progress)
        self._worker.finished_signal.connect(self._on_worker_finished)
        self._worker.error_signal.connect(self._on_worker_error)
        self._worker.start()

    def _on_worker_finished(self, success: bool) -> None:
        self._running = False
        self._worker = None
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setText("⏹️ 取消")

    def _on_worker_error(self, err_msg: str) -> None:
        self._log(f"❌ 处理出错: {err_msg}")
        self._on_worker_finished(False)


class Pdf2MdMixin:
    def open_pdf2md_window(self) -> None:
        if not hasattr(self, "_pdf2md_window") or self._pdf2md_window is None:
            self._pdf2md_window = Pdf2MdWindow(self)
        self._pdf2md_window.show()
        self._pdf2md_window.raise_()
        self._pdf2md_window.activateWindow()
