"""
XFund — 基金数据分析与建议系统
入口脚本：默认启动桌面 GUI
"""

import sys

from loguru import logger

# 禁用终端输出
logger.remove()
logger.add(lambda _: None, level="ERROR")


def desktop():
    """启动桌面 GUI（默认模式）"""
    from src.ui.app import main as gui_main
    gui_main()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scheduler":
        from src.scheduler.jobs import JobScheduler
        JobScheduler().run_daily(hour=15, minute=30)
    else:
        desktop()
