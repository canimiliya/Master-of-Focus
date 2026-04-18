"""Qt entry point for Study Game Pro (PySide6).

Run:
  pip install pyside6 matplotlib
  python study_game_pro_qt.py

Data/config format is kept compatible with the legacy Tkinter version.
"""

from __future__ import annotations

import sys

from PySide6 import QtWidgets

from sgp_qt_main_window import StudyGameQt
from sgp_qt_platform import enforce_single_instance


def main() -> None:
    enforce_single_instance()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Study Game Pro (Qt)")

    win = StudyGameQt()
    win.show()

    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
