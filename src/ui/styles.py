"""
全局样式表与颜色映射
"""

import matplotlib

# ─── 全局样式表 ───────────────────────────────────────────
STYLE = """
QMainWindow { background: transparent; }
QMenuBar { background-color: #1a1a2e; color: white; padding: 4px; font-size: 13px; border-radius: 0px; }
QMenuBar::item:selected { background-color: #16213e; }
QMenu { background-color: #1a1a2e; color: white; border: 1px solid #0f3460; }
QMenu::item:selected { background-color: #0f3460; }
QListWidget { background-color: white; border: none; border-radius: 6px; font-size: 13px; padding: 0px; outline: none; }
QListWidget::item { border: none; background: transparent; padding: 0px; margin: 0px; }
QListWidget::item:hover { background-color: #eef2f7; }
QTabWidget::pane { background-color: white; border: 1px solid #ddd; border-radius: 6px; }
QTabBar::tab { background-color: #e8ecf1; padding: 10px 24px; margin-right: 2px; font-size: 13px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background-color: white; font-weight: bold; color: #2c3e50; }
QTabWidget#pageTabs::pane { border: none; background-color: white; }
QTabWidget#pageTabs QTabBar::tab { background: transparent; padding: 10px 28px; font-size: 16px; color: #7f8c8d; border: none; margin-right: 0px; }
QTabWidget#pageTabs QTabBar::tab:selected { color: #2c3e50; font-weight: bold; background: transparent; border-bottom: 2px solid #3498db; }
QPushButton { background-color: #3498db; color: white; border: none; padding: 10px 24px; border-radius: 6px; font-size: 13px; font-weight: bold; }
QPushButton:hover { background-color: #2980b9; }
QPushButton:pressed { background-color: #2471a3; }
QPushButton#refreshBtn { background-color: #27ae60; }
QPushButton#refreshBtn:hover { background-color: #219a52; }
QGroupBox { font-size: 15px; font-weight: bold; color: #2c3e50; border: 1px solid #ddd; border-radius: 8px; margin-top: 12px; padding-top: 20px; background-color: white; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLabel#metricValue { font-size: 22px; font-weight: bold; color: #2c3e50; }
QLabel#metricLabel { font-size: 12px; color: #7f8c8d; }
QSplitter::handle { background: transparent; }
QProgressBar { border: none; border-radius: 4px; background-color: #e0e0e0; height: 4px; }
QProgressBar::chunk { background-color: #3498db; border-radius: 4px; }
"""

# ─── 级别颜色映射 ─────────────────────────────────────────
LEVEL_COLORS = {
    "【积极买入】": ("#27ae60", "#d5f5e3"),
    "【建议加仓】": ("#2ecc71", "#d5f5e3"),
    "【持有观望】": ("#f39c12", "#fef9e7"),
    "【适度减仓】": ("#e67e22", "#fdebd0"),
    "【果断离场】": ("#c0392b", "#f5b7b1"),
    "【持有】": ("#f39c12", "#fef9e7"),
}

# ─── 中文 matplotlib 配置 ─────────────────────────────────
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
matplotlib.rcParams["axes.unicode_minus"] = False
