from __future__ import annotations
from datetime import datetime
import os
import shutil

from PySide6 import QtCore, QtGui, QtWidgets

from sgp_qt_core import app_config, save_app_config


class MemoMixin:
    def open_memo_window(self) -> None:
        if not app_config.get("memo_dir"):
            if not app_config.get("data_dir"):
                self.ensure_storage_directory()
            app_config["memo_dir"] = app_config.get("data_dir", "")
            save_app_config()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("💡 随手记归档面板")
        dialog.resize(500, 360)
        dialog.setMinimumSize(500, 360)
        dialog.setModal(True)

        memo_file_paths: list[str] = []
        memo_img_paths: list[str] = []

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(20, 15, 20, 15)
        root.setSpacing(10)

        lbl = QtWidgets.QLabel("✏️ 文本内容 (必填):")
        lbl.setFont(self._font(size=10, bold=True))
        root.addWidget(lbl)

        text_input = QtWidgets.QTextEdit()
        text_input.setMinimumHeight(120)
        root.addWidget(text_input)

        class _DropLabel(QtWidgets.QLabel):
            def __init__(self, on_files):
                super().__init__("拖拽文件/图片到这里（可多选）")
                self._on_files = on_files
                self.setAcceptDrops(True)
                self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.setStyleSheet("color:#777777;border:1px dashed #BBBBBB;border-radius:6px;padding:10px;")

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

        file_label = QtWidgets.QLabel("")
        file_label.setStyleSheet("color:blue")
        file_label.setWordWrap(True)
        img_label = QtWidgets.QLabel("")
        img_label.setStyleSheet("color:green")
        img_label.setWordWrap(True)

        def update_labels() -> None:
            if memo_file_paths:
                names = [os.path.basename(p) for p in memo_file_paths]
                file_label.setText(f"📎 已选文件({len(names)}):\n" + "\n".join(names))
            else:
                file_label.setText("")
            if memo_img_paths:
                names = [os.path.basename(p) for p in memo_img_paths]
                img_label.setText(f"🖼️ 已选图片({len(names)}):\n" + "\n".join(names))
            else:
                img_label.setText("")

        img_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

        def add_paths(paths: list[str]) -> None:
            for p in paths:
                if not p:
                    continue
                ext = os.path.splitext(p)[1].lower()
                if ext in img_exts:
                    if p not in memo_img_paths:
                        memo_img_paths.append(p)
                else:
                    if p not in memo_file_paths:
                        memo_file_paths.append(p)
            update_labels()

        drop_area = _DropLabel(add_paths)
        root.addWidget(drop_area)

        pick_btn = QtWidgets.QPushButton("选择文件/图片")
        pick_btn.setMinimumHeight(32)
        root.addWidget(pick_btn)

        root.addWidget(file_label)
        root.addWidget(img_label)

        save_btn = QtWidgets.QPushButton("🚀 一键归档至随手记")
        save_btn.setMinimumHeight(40)
        save_btn.setFont(self._font(size=12, bold=True))
        root.addWidget(save_btn)

        def pick_files() -> None:
            paths, _ = QtWidgets.QFileDialog.getOpenFileNames(dialog, "选择文件/图片")
            if paths:
                add_paths(paths)

        pick_btn.clicked.connect(pick_files)

        def save_memo_entry() -> None:
            content = text_input.toPlainText().strip()
            has_attachment = bool(memo_file_paths or memo_img_paths)

            if has_attachment and not content:
                QtWidgets.QMessageBox.warning(dialog, "⚠️ 格式错误", "按照规则，上传文件或图片必须附加文字说明才可以上传！")
                return
            if not content and not has_attachment:
                QtWidgets.QMessageBox.warning(dialog, "⚠️ 内容为空", "请填写记录内容！")
                return

            today_str = datetime.now().strftime("%Y-%m-%d")
            memo_base = app_config.get("memo_dir") or app_config.get("data_dir") or ""
            if not memo_base:
                QtWidgets.QMessageBox.warning(dialog, "错误", "未找到随手记目录。")
                return

            memo_txt_path = os.path.join(memo_base, "随手记.txt")
            memo_folder_path = os.path.join(memo_base, "随手记", today_str)

            is_new_day = app_config.get("memo_date") != today_str
            if is_new_day:
                app_config["memo_date"] = today_str
                app_config["memo_count"] = 0

                mode = "a" if os.path.exists(memo_txt_path) else "w"
                os.makedirs(memo_base, exist_ok=True)
                with open(memo_txt_path, mode, encoding="utf-8") as f:
                    if mode == "a":
                        f.write("\n\n\n")
                    f.write(f"【{today_str}】\n")
                save_app_config()

            app_config["memo_count"] = int(app_config.get("memo_count", 0) or 0) + 1
            save_app_config()
            idx = int(app_config.get("memo_count", 0) or 0)

            attach_msg = ""
            if has_attachment:
                os.makedirs(memo_folder_path, exist_ok=True)

                file_names: list[str] = []
                for file_path in memo_file_paths:
                    try:
                        fname = os.path.basename(file_path)
                        shutil.copy(file_path, os.path.join(memo_folder_path, fname))
                        file_names.append(fname)
                    except Exception:
                        pass
                if file_names:
                    attach_msg += f"，对应文件《{'、'.join(file_names)}》在 {memo_folder_path} 可以查看"

                img_names: list[str] = []
                for img_path in memo_img_paths:
                    try:
                        iname = os.path.basename(img_path)
                        shutil.copy(img_path, os.path.join(memo_folder_path, iname))
                        img_names.append(iname)
                    except Exception:
                        pass
                if img_names:
                    attach_msg += f"，对应图片《{'、'.join(img_names)}》在 {memo_folder_path} 可以查看"

            line_str = f"{idx}、{content}{attach_msg}\n"
            os.makedirs(os.path.dirname(memo_txt_path) or memo_base, exist_ok=True)
            with open(memo_txt_path, "a", encoding="utf-8") as f:
                f.write(line_str)

            QtWidgets.QMessageBox.information(dialog, "🎉 归档成功", "内容已成功写入随手记，附件已分发至日期文件夹！")
            dialog.accept()

        save_btn.clicked.connect(save_memo_entry)
        dialog.exec()
