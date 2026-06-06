"""
XFund 桌面版 — 入口脚本
"""

import sys
import traceback
from pathlib import Path

import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont, QIcon

from src.ui.main_window import MainWindow


def main():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("XFund")

        icon_path = Path(__file__).parent.parent.parent / "assets" / "xfund.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        font = QFont("Microsoft YaHei", 10)
        QApplication.setFont(font)

        window = MainWindow()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(None, "启动失败", f"程序启动时发生错误：\n\n{e}\n\n详情请查看终端输出。")
        sys.exit(1)


if __name__ == "__main__":
    main()
