"""
XFund 桌面版 — PySide6 专业 GUI 界面
提供基金净值走势图、技术指标分析、投资建议
"""

import sys
import traceback
from datetime import datetime

import matplotlib
matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QTabWidget, QLabel, QPushButton,
    QMenuBar, QMenu, QGroupBox, QGridLayout, QFrame,
    QSplitter, QMessageBox, QProgressBar, QScrollArea, QSizePolicy,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QInputDialog,
    QRadioButton, QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QPoint
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QGraphicsDropShadowEffect
import re

from config.settings import THRESHOLDS
from src.data.fetcher import FundFetcher
from src.analysis.calculator import FundAnalyzer
from src.strategy.advisor import FundAdvisor, Position, AdviceResult
from src.storage.database import DataStore

# ─── 全局样式表 ───────────────────────────────────────────
STYLE = """
QMainWindow { background: transparent; }
QMenuBar { background-color: #1a1a2e; color: white; padding: 4px; font-size: 13px; border-radius: 0px; }
QMenuBar::item:selected { background-color: #16213e; }
QMenu { background-color: #1a1a2e; color: white; border: 1px solid #0f3460; }
QMenu::item:selected { background-color: #0f3460; }
QListWidget { background-color: white; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; padding: 1px 1px 1px 0px; outline: none; }
QListWidget::item { border: none; background: transparent; padding: 0px; margin: 0px; }
QListWidget::item:hover { background-color: #eef2f7; }
QTabWidget::pane { background-color: white; border: 1px solid #ddd; border-radius: 6px; }
QTabBar::tab { background-color: #e8ecf1; padding: 10px 24px; margin-right: 2px; font-size: 13px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background-color: white; font-weight: bold; color: #2c3e50; }
QPushButton { background-color: #3498db; color: white; border: none; padding: 10px 24px; border-radius: 6px; font-size: 13px; font-weight: bold; }
QPushButton:hover { background-color: #2980b9; }
QPushButton:pressed { background-color: #2471a3; }
QPushButton#refreshBtn { background-color: #27ae60; }
QPushButton#refreshBtn:hover { background-color: #219a52; }
QGroupBox { font-size: 14px; font-weight: bold; color: #2c3e50; border: 1px solid #ddd; border-radius: 8px; margin-top: 12px; padding-top: 20px; background-color: white; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLabel#metricValue { font-size: 22px; font-weight: bold; color: #2c3e50; }
QLabel#metricLabel { font-size: 12px; color: #7f8c8d; }
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


class DCADialog(QDialog):
    """定投设置对话框：金额 + 频率"""
    def __init__(self, current_base: float = 1000, parent=None):
        super().__init__(parent)
        self.setWindowTitle("同步定投")
        self.setFixedSize(360, 220)
        self.setStyleSheet("QDialog { background-color: white; }")

        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText(f"每期定投金额，如 {current_base:.0f}")
        self.amount_input.setText(f"{current_base:.0f}")
        self.amount_input.setStyleSheet("padding: 8px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px;")
        layout.addRow("定投金额(元):", self.amount_input)

        freq_layout = QHBoxLayout()
        self.freq_group = QButtonGroup(self)
        self.radio_daily = QRadioButton("每天")
        self.radio_weekly = QRadioButton("每周")
        self.radio_monthly = QRadioButton("每月")
        self.radio_monthly.setChecked(True)
        self.freq_group.addButton(self.radio_daily, 0)
        self.freq_group.addButton(self.radio_weekly, 1)
        self.freq_group.addButton(self.radio_monthly, 2)
        freq_layout.addWidget(self.radio_daily)
        freq_layout.addWidget(self.radio_weekly)
        freq_layout.addWidget(self.radio_monthly)
        freq_layout.addStretch()
        layout.addRow("定投频率:", freq_layout)

        hint = QLabel("定投金额将直接计入持有金额")
        hint.setStyleSheet("font-size: 11px; color: #95a5a6;")
        layout.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认定投")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_accept(self):
        try:
            amount = float(self.amount_input.text().strip())
            if amount <= 0:
                QMessageBox.warning(self, "提示", "定投金额必须大于 0。")
                return
        except ValueError:
            QMessageBox.warning(self, "提示", "请输入有效的定投金额。")
            return
        self.accept()

    def get_result(self):
        """返回 (金额, 频率key)"""
        freq_map = {0: "daily", 1: "weekly", 2: "monthly"}
        freq_id = self.freq_group.checkedId()
        return float(self.amount_input.text().strip()), freq_map.get(freq_id, "monthly")


class FetchThread(QThread):
    """后台线程：异步获取基金数据，避免界面卡顿"""
    finished = Signal(str, object)
    error = Signal(str, str)

    def __init__(self, fund_code: str):
        super().__init__()
        self.fund_code = fund_code

    def run(self):
        try:
            fetcher = FundFetcher()
            df = fetcher.get_fund_nav(self.fund_code)
            self.finished.emit(self.fund_code, df)
        except Exception as e:
            self.error.emit(self.fund_code, str(e))


class SummaryFetchThread(QThread):
    """后台线程：异步加载账户汇总所需的板块、重仓股数据"""
    finished = Signal(dict, dict, dict)  # (sector_map, fund_holdings_map, stock_changes)

    def __init__(self, funds: list):
        super().__init__()
        self.funds = funds

    def run(self):
        fetcher = FundFetcher()
        sector_map = fetcher.get_sector_performance()
        all_stock_codes = set()
        fund_holdings_map = {}

        for fund in self.funds:
            holdings = fetcher.get_fund_holdings(fund["code"])
            fund_holdings_map[fund["code"]] = holdings
            for s in holdings.get("stocks", []):
                all_stock_codes.add(s["code"])

        stock_changes = fetcher.get_stock_daily_change(list(all_stock_codes)) if all_stock_codes else {}
        self.finished.emit(sector_map, fund_holdings_map, stock_changes)


class MplCanvas(FigureCanvas):
    """Matplotlib 画布，嵌入 Qt（高性能优化）"""
    def __init__(self, figsize=(10, 4.5)):
        self.fig = Figure(figsize=figsize, dpi=72, facecolor="white")
        # 不用 constrained_layout（极其缓慢），改用手动 subplots_adjust
        self.fig.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.15)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(200)
        self.setStyleSheet("background: white;")

        # 防抖 resize：300ms 后才重绘
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_debounced)
        self._needs_redraw = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._needs_redraw = True
        self._resize_timer.start(300)

    def _on_resize_debounced(self):
        if self._needs_redraw:
            self._needs_redraw = False
            try:
                super().draw()
            except Exception:
                pass


class AddFundDialog(QDialog):
    """添加自选基金对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加自选基金")
        self.setFixedSize(380, 200)
        self.setStyleSheet("QDialog { background-color: white; }")

        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("必填，例如：161725")
        self.code_input.setMaxLength(6)
        self.code_input.setStyleSheet("padding: 8px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px;")
        layout.addRow("基金代码 *:", self.code_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("可选，留空则自动获取名称")
        self.name_input.setStyleSheet("padding: 8px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px;")
        layout.addRow("基金名称:", self.name_input)

        hint = QLabel("💡 只需填写代码即可添加，名称会自动获取")
        hint.setStyleSheet("font-size: 11px; color: #95a5a6;")
        layout.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_accept(self):
        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "提示", "请输入基金代码。")
            return
        if not code.isdigit() or len(code) != 6:
            QMessageBox.warning(self, "提示", "基金代码应为 6 位数字。")
            return
        self.accept()

    def get_fund(self):
        return self.code_input.text().strip(), self.name_input.text().strip()


def simplify_fund_name(name: str) -> str:
    """把 akshare 返回的超长基金名压缩为简称"""
    # 先提取末尾份额类别 A/B/C/D/E
    share = ""
    m = re.search(r"[ABCDE]$", name)
    if m:
        share = m.group()
        name = name[:-1]

    # 去掉冗长后缀
    name = re.sub(r"(型)?(发起式)?证券投资基金$", "", name)
    name = re.sub(r"分级$", "", name)

    # 处理 "混合C型" → "混合C"（份额字母嵌入在型字前的情况）
    m = re.search(r"([ABCDE])型$", name)
    if m:
        name = name[:-2] + m.group(1)

    name = name.rstrip("型类")
    return name + share


class MainWindow(QMainWindow):
    """XFund 主窗口 — 无边框圆角现代风格"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XFund")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)

        # 无边框 + 透明背景（圆角需要）
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.fetcher = FundFetcher()
        self.analyzer = FundAnalyzer()
        self.advisor = FundAdvisor()
        self.store = DataStore()

        self.funds = self.store.load_watchlist()
        self.current_df = None
        self.current_summary = None
        self.current_code = None
        self.fetch_thread = None
        self.summary_thread = None
        self._summary_loading = False
        self._drag_pos = None

        self._setup_ui()
        self.setStyleSheet(STYLE)

        # 启动时自动加载账户汇总
        QTimer.singleShot(300, self._refresh_account_summary)

    # ─── 菜单栏 ──────────────────────────────────────────
    # ─── 主界面布局 ──────────────────────────────────────
    def _setup_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(0)

        # ── 圆角容器（所有内容放这里）──
        container = QWidget()
        container.setObjectName("mainContainer")
        container.setStyleSheet(
            "#mainContainer {"
            "  background-color: #f0f2f5;"
            "  border-radius: 14px;"
            "}"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── 自定义标题栏 ──
        title_bar = QWidget()
        title_bar.setFixedHeight(42)
        title_bar.setStyleSheet(
            "background: #1a1a2e; border-top-left-radius: 14px; border-top-right-radius: 14px;"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(14, 0, 8, 0)

        logo = QLabel("XFund")
        logo.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: transparent;")
        tb_layout.addWidget(logo)

        # 标题栏菜单按钮
        menu_btn_style = (
            "QPushButton { background: transparent; color: #ccc; border: none; "
            "padding: 6px 14px; font-size: 12px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.10); color: white; }"
        )

        def make_menu(text, actions: list):
            btn = QPushButton(text)
            btn.setStyleSheet(menu_btn_style)
            menu = QMenu(btn)
            menu.setStyleSheet(
                "QMenu { background: #1a1a2e; color: white; border: 1px solid #0f3460; padding: 4px; }"
                "QMenu::item { padding: 6px 24px; }"
                "QMenu::item:selected { background: #0f3460; }"
            )
            for label, slot, shortcut in actions:
                if slot is None:
                    menu.addSeparator()
                else:
                    act = menu.addAction(label)
                    if shortcut:
                        act.setShortcut(shortcut)
                    act.triggered.connect(slot)
            btn.setMenu(menu)
            return btn

        file_menu = make_menu("文件", [
            ("添加基金...", self._add_fund, ""),
            ("刷新数据", self._refresh, "F5"),
            ("导出数据...", self._export, ""),
            ("", None, ""),
            ("退出", self.close, "Ctrl+Q"),
        ])
        tb_layout.addWidget(file_menu)

        settings_menu = make_menu("设置", [
            ("告警阈值...", self._edit_thresholds, ""),
        ])
        tb_layout.addWidget(settings_menu)

        help_menu = make_menu("帮助", [
            ("关于 XFund", self._about, ""),
        ])
        tb_layout.addWidget(help_menu)

        tb_layout.addStretch()

        btn_style = (
            "QPushButton { background: transparent; color: #ccc; border: none; "
            "font-size: 16px; padding: 6px 12px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); color: white; }"
        )
        btn_min = QPushButton("─")
        btn_min.setStyleSheet(btn_style)
        btn_min.clicked.connect(self.showMinimized)
        tb_layout.addWidget(btn_min)

        btn_max = QPushButton("□")
        btn_max.setStyleSheet(btn_style)
        btn_max.clicked.connect(self._toggle_maximize)
        tb_layout.addWidget(btn_max)

        btn_close = QPushButton("✕")
        btn_close.setStyleSheet(btn_style + "QPushButton:hover { background: #e74c3c; color: white; }")
        btn_close.clicked.connect(self.close)
        tb_layout.addWidget(btn_close)

        # 标题栏拖动
        title_bar.mousePressEvent = self._title_bar_press
        title_bar.mouseMoveEvent = self._title_bar_move

        container_layout.addWidget(title_bar)

        # ── 页面内容区 ──
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ── 顶层页面 Tab ──
        self.page_tabs = QTabWidget()
        self.page_tabs.setStyleSheet(
            "QTabBar::tab { padding: 12px 32px; font-size: 15px; font-weight: bold; }"
            "QTabBar::tab:selected { color: #3498db; }"
        )

        # ===== Page 0: 账户汇总 =====
        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        summary_layout.setSpacing(8)

        summary_toolbar = QHBoxLayout()
        summary_title = QLabel("📊 账户汇总")
        summary_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a1a2e;")
        summary_toolbar.addWidget(summary_title)
        summary_toolbar.addStretch()

        refresh_summary_btn = QPushButton("↻ 刷新汇总")
        refresh_summary_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 8px 20px; border-radius: 5px; font-size: 13px; }"
            "QPushButton:hover { background: #2980b9; }"
        )
        refresh_summary_btn.clicked.connect(self._refresh_account_summary)
        summary_toolbar.addWidget(refresh_summary_btn)
        summary_layout.addLayout(summary_toolbar)

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(9)
        self.summary_table.setHorizontalHeaderLabels([
            "基金名称", "持有金额", "持有收益", "持有收益率",
            "当日收益", "当日收益率", "关联板块", "板块涨幅", "重仓均涨幅",
        ])
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 9):
            self.summary_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.setStyleSheet(
            "QTableWidget { background: white; border: 1px solid #ddd; border-radius: 6px; "
            "gridline-color: #eee; font-size: 13px; }"
            "QTableWidget::item { padding: 8px 12px; }"
            "QHeaderView::section { background: #f0f2f5; padding: 10px 8px; "
            "font-weight: bold; color: #2c3e50; border: none; border-bottom: 2px solid #ddd; }"
            "QTableWidget::item:alternate { background: #fafbfc; }"
        )
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        summary_layout.addWidget(self.summary_table)

        total_bar = QHBoxLayout()
        self.total_amount_label = QLabel("总持仓: —")
        self.total_amount_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; padding: 4px 8px;")
        self.total_profit_label = QLabel("总收益: —")
        self.total_profit_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px 8px;")
        self.total_daily_label = QLabel("今日收益: —")
        self.total_daily_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px 8px;")
        total_bar.addWidget(self.total_amount_label)
        total_bar.addWidget(self.total_profit_label)
        total_bar.addWidget(self.total_daily_label)
        total_bar.addStretch()
        summary_hint = QLabel("关联板块根据基金名称推测，仅供参考")
        summary_hint.setStyleSheet("font-size: 11px; color: #95a5a6;")
        total_bar.addWidget(summary_hint)
        summary_layout.addLayout(total_bar)

        self.page_tabs.addTab(summary_page, "📊 账户汇总")

        # ===== Page 1: 自选基金 =====
        fund_page = QWidget()
        fund_layout = QHBoxLayout(fund_page)
        fund_layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 左侧面板：基金列表 ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 标题行
        title_label = QLabel("📈 自选基金")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a1a2e; padding: 8px 4px;")
        left_layout.addWidget(title_label)

        # 三个图标按钮（正方形，无文字）
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        sq_style = (
            "QPushButton { background: white; border: 1px solid #d5d8dc; border-radius: 5px; "
            "min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; "
            "font-size: 14px; padding: 0px; }"
        )
        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("刷新数据 (F5)")
        refresh_btn.setStyleSheet(sq_style + "QPushButton { color: #2980b9; } QPushButton:hover { background: #eaf2f8; }")
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)

        add_btn = QPushButton("+")
        add_btn.setToolTip("添加基金")
        add_btn.setStyleSheet(sq_style + "QPushButton { color: #27ae60; } QPushButton:hover { background: #eafaf1; }")
        add_btn.clicked.connect(self._add_fund)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("−")
        del_btn.setToolTip("删除选中基金")
        del_btn.setStyleSheet(sq_style + "QPushButton { color: #95a5a6; } QPushButton:hover { background: #f0f0f0; color: #e74c3c; }")
        del_btn.clicked.connect(self._delete_fund)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        left_layout.addLayout(btn_row)

        # 基金列表
        self.fund_list = QListWidget()
        self._populate_list()
        self.fund_list.currentRowChanged.connect(self._on_fund_selected)
        left_layout.addWidget(self.fund_list)

        # 右键菜单
        self.fund_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fund_list.customContextMenuRequested.connect(self._on_context_menu)

        # ── 右侧面板 ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.fund_title = QLabel("👈 点击「＋ 添加基金」开始，然后选择基金即可查看")
        self.fund_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7f8c8d; padding: 4px 0;")
        self.fund_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.fund_title)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMinimum(0)
        self.progress.setMaximum(0)
        right_layout.addWidget(self.progress)

        self.tabs = QTabWidget()

        # --- Tab 0: 净值走势 ---
        self.chart_tab = QWidget()
        chart_layout = QVBoxLayout(self.chart_tab)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(4)

        # 两张图使用相同的 figsize 确保左右对齐
        self.nav_canvas = MplCanvas(figsize=(10, 4.5))
        self._draw_empty_chart(self.nav_canvas, "选择基金并刷新后显示净值走势")
        chart_layout.addWidget(self.nav_canvas, stretch=1)

        self.bar_canvas = MplCanvas(figsize=(10, 4.0))
        self._draw_empty_chart(self.bar_canvas, "选择基金并刷新后显示日涨跌幅")
        chart_layout.addWidget(self.bar_canvas, stretch=1)

        self.tabs.addTab(self.chart_tab, "📊 净值走势")

        # --- Tab 2: 基金数据 ---
        self.analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(self.analysis_tab)
        analysis_layout.setContentsMargins(0, 0, 0, 0)

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(12)
        self.metrics_grid.setContentsMargins(8, 8, 8, 8)
        analysis_layout.addLayout(self.metrics_grid)
        analysis_layout.addStretch()

        self.tabs.addTab(self.analysis_tab, "📋 基金数据")

        # --- Tab 3: 持仓操作 ---
        self.position_tab = QWidget()
        pos_tab_layout = QVBoxLayout(self.position_tab)
        pos_tab_layout.setSpacing(12)

        # 当前持仓展示
        cur_group = QGroupBox("📌 当前持仓")
        cur_layout = QGridLayout(cur_group)
        cur_layout.setSpacing(10)
        self.cur_amount_label = QLabel("—")
        self.cur_amount_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        self.cur_profit_label = QLabel("—")
        self.cur_profit_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.cur_shares_label = QLabel("—")
        self.cur_cost_label = QLabel("—")
        cur_layout.addWidget(QLabel("持仓金额:"), 0, 0)
        cur_layout.addWidget(self.cur_amount_label, 0, 1)
        cur_layout.addWidget(QLabel("持仓收益:"), 0, 2)
        cur_layout.addWidget(self.cur_profit_label, 0, 3)
        cur_layout.addWidget(QLabel("持有份额:"), 1, 0)
        cur_layout.addWidget(self.cur_shares_label, 1, 1)
        cur_layout.addWidget(QLabel("成本价:"), 1, 2)
        cur_layout.addWidget(self.cur_cost_label, 1, 3)
        pos_tab_layout.addWidget(cur_group)

        # 修改持仓
        edit_group = QGroupBox("✏️ 修改持仓")
        edit_layout = QGridLayout(edit_group)
        edit_layout.setSpacing(8)

        edit_layout.addWidget(QLabel("持有金额(元):"), 0, 0)
        self.edit_amount = QLineEdit()
        self.edit_amount.setPlaceholderText("如 50000")
        self.edit_amount.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        edit_layout.addWidget(self.edit_amount, 0, 1)

        edit_layout.addWidget(QLabel("持有收益(元):"), 0, 2)
        self.edit_profit = QLineEdit()
        self.edit_profit.setPlaceholderText("如 +2500 或 -1500")
        self.edit_profit.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        edit_layout.addWidget(self.edit_profit, 0, 3)

        edit_layout.addWidget(QLabel("定投基准(元):"), 1, 0)
        self.edit_base = QLineEdit()
        self.edit_base.setPlaceholderText("如 1000")
        self.edit_base.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        edit_layout.addWidget(self.edit_base, 1, 1)

        save_btn = QPushButton("💾 同步到分析")
        save_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 8px 16px; border-radius: 5px; font-size: 13px; }"
            "QPushButton:hover { background: #2980b9; }"
        )
        save_btn.clicked.connect(self._save_position)
        edit_layout.addWidget(save_btn, 1, 2, 1, 2)

        pos_tab_layout.addWidget(edit_group)

        # 快捷操作
        action_group = QGroupBox("⚡ 快捷操作")
        action_layout = QHBoxLayout(action_group)
        action_layout.setSpacing(12)

        btn_action_style = (
            "QPushButton { color: white; border: none; padding: 12px 20px; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
        )
        self.btn_add_pos = QPushButton("📥 同步加仓")
        self.btn_add_pos.setStyleSheet(btn_action_style + "QPushButton { background: #27ae60; } QPushButton:hover { background: #219a52; }")
        self.btn_add_pos.clicked.connect(self._sync_add)
        action_layout.addWidget(self.btn_add_pos)

        self.btn_reduce_pos = QPushButton("📤 同步减仓")
        self.btn_reduce_pos.setStyleSheet(btn_action_style + "QPushButton { background: #e67e22; } QPushButton:hover { background: #d35400; }")
        self.btn_reduce_pos.clicked.connect(self._sync_reduce)
        action_layout.addWidget(self.btn_reduce_pos)

        self.btn_dca = QPushButton("📊 同步定投")
        self.btn_dca.setStyleSheet(btn_action_style + "QPushButton { background: #3498db; } QPushButton:hover { background: #2980b9; }")
        self.btn_dca.clicked.connect(self._sync_dca)
        action_layout.addWidget(self.btn_dca)

        pos_tab_layout.addWidget(action_group)

        pos_tab_layout.addStretch()

        self.tabs.addTab(self.position_tab, "💰 持仓操作")

        # --- Tab 4: 投资建议 ---
        self.advice_scroll = QScrollArea()
        self.advice_scroll.setWidgetResizable(True)
        self.advice_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.advice_tab = QWidget()
        self.advice_scroll.setWidget(self.advice_tab)
        advice_layout = QVBoxLayout(self.advice_tab)

        # 持仓管理区域
        pos_group = QGroupBox("💰 持仓管理")
        pos_layout = QVBoxLayout(pos_group)

        pos_input_row = QHBoxLayout()
        pos_input_row.addWidget(QLabel("持有份额:"))
        self.pos_shares = QLineEdit()
        self.pos_shares.setPlaceholderText("例: 10000")
        self.pos_shares.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        pos_input_row.addWidget(self.pos_shares)

        pos_input_row.addWidget(QLabel("成本价:"))
        self.pos_cost = QLineEdit()
        self.pos_cost.setPlaceholderText("例: 0.85")
        self.pos_cost.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        pos_input_row.addWidget(self.pos_cost)

        pos_input_row.addWidget(QLabel("定投基准/期:"))
        self.pos_base = QLineEdit()
        self.pos_base.setPlaceholderText("例: 1000")
        self.pos_base.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        pos_input_row.addWidget(self.pos_base)

        save_pos_btn = QPushButton("💾 保存持仓")
        save_pos_btn.clicked.connect(self._save_position)
        pos_input_row.addWidget(save_pos_btn)

        pos_layout.addLayout(pos_input_row)
        self.pos_status_label = QLabel("💡 输入持仓信息可获得更精准的个性化建议")
        self.pos_status_label.setStyleSheet("font-size: 11px; color: #95a5a6;")
        pos_layout.addWidget(self.pos_status_label)
        advice_layout.addWidget(pos_group)

        # 建议横幅
        self.advice_banner = QFrame()
        self.advice_banner.setMinimumHeight(100)
        self.advice_banner.setStyleSheet("border-radius: 10px; background-color: #bdc3c7;")
        banner_layout = QVBoxLayout(self.advice_banner)
        self.advice_level_label = QLabel("等待数据加载...")
        self.advice_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_level_label.setStyleSheet("font-size: 26px; font-weight: bold; color: white;")
        self.advice_desc_label = QLabel("请先选择基金并加载数据")
        self.advice_desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_desc_label.setStyleSheet("font-size: 14px; color: rgba(255,255,255,0.9);")
        banner_layout.addStretch()
        banner_layout.addWidget(self.advice_level_label)
        banner_layout.addWidget(self.advice_desc_label)
        banner_layout.addStretch()
        advice_layout.addWidget(self.advice_banner)

        # 操作建议数值
        ops_group = QGroupBox("📐 操作建议")
        ops_layout = QGridLayout(ops_group)
        ops_layout.setSpacing(12)
        self.ops_dca_label = QLabel("—")
        self.ops_dca_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #27ae60;")
        self.ops_grid_label = QLabel("—")
        self.ops_grid_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2980b9;")
        self.ops_position_label = QLabel("—")
        self.ops_position_label.setStyleSheet("font-size: 14px; color: #2c3e50;")
        ops_layout.addWidget(QLabel("📥 定投建议:"), 0, 0)
        ops_layout.addWidget(self.ops_dca_label, 0, 1)
        ops_layout.addWidget(QLabel("📐 网格信号:"), 1, 0)
        ops_layout.addWidget(self.ops_grid_label, 1, 1)
        ops_layout.addWidget(QLabel("💰 持仓状态:"), 2, 0)
        ops_layout.addWidget(self.ops_position_label, 2, 1)
        advice_layout.addWidget(ops_group)

        # 分析理由
        reasons_group = QGroupBox("📝 分析理由")
        reasons_layout = QVBoxLayout(reasons_group)
        self.reasons_label = QLabel("等待数据加载...")
        self.reasons_label.setStyleSheet("font-size: 13px; line-height: 1.8; color: #2c3e50; padding: 4px;")
        self.reasons_label.setWordWrap(True)
        reasons_layout.addWidget(self.reasons_label)
        advice_layout.addWidget(reasons_group)

        # 免责声明
        disclaimer = QLabel(
            "⚠️ 估算净值与实际净值存在偏差，请以基金公司公布为准。\n"
            "⚠️ 以上建议基于历史数据和公开信息量化估算，不构成确定性投资建议。投资有风险，入市需谨慎。"
        )
        disclaimer.setStyleSheet("font-size: 11px; color: #e67e22; padding: 8px; background: #fef9e7; border-radius: 6px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        advice_layout.addWidget(disclaimer)

        self.tabs.addTab(self.advice_scroll, "💡 投资建议")

        right_layout.addWidget(self.tabs)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 1060])

        fund_layout.addWidget(splitter)
        self.page_tabs.addTab(fund_page, "📈 自选基金")

        # 切换到账户汇总时自动刷新
        self.page_tabs.currentChanged.connect(self._on_page_changed)

        content_layout.addWidget(self.page_tabs)

        # 状态栏移入内容区
        self.statusbar_widget = QWidget()
        self.statusbar_widget.setFixedHeight(28)
        self.statusbar_widget.setStyleSheet("background: #1a1a2e; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px;")
        sb_layout = QHBoxLayout(self.statusbar_widget)
        sb_layout.setContentsMargins(14, 0, 14, 0)
        self.status_time = QLabel("就绪 — 请选择基金后点击「刷新数据」")
        self.status_time.setStyleSheet("color: #ccc; font-size: 11px; background: transparent;")
        sb_layout.addWidget(self.status_time)
        content_layout.addWidget(self.statusbar_widget)

        container_layout.addLayout(content_layout)
        outer_layout.addWidget(container)
        self.setStyleSheet(STYLE)

    # ─── 标题栏拖动 ─────────────────────────────────────
    def _title_bar_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def _title_bar_move(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ─── 绘制空图表（占位） ───────────────────────────────
    def _draw_empty_chart(self, canvas: MplCanvas, message: str):
        ax = canvas.ax
        ax.clear()
        ax.text(0.5, 0.5, message, transform=ax.transAxes,
                ha="center", va="center", fontsize=16, color="#bdc3c7")
        ax.set_xticks([])
        ax.set_yticks([])
        canvas.draw()

    # ─── 基金列表操作 ────────────────────────────────────
    BADGE_HELD_STYLE = (
        "QLabel { background: #e74c3c; color: white; border-radius: 3px; "
        "padding: 3px 8px; font-size: 13px; font-weight: bold; }"
    )

    # 选中指示器样式（用属性选择器避免影响子控件）
    SELECTED_STYLE = (
        "QWidget[selected=\"true\"] { "
        "background-color: #f0f4fa; border-radius: 6px; }"
    )
    UNSELECTED_STYLE = "QWidget[selected=\"true\"] { background: transparent; }"

    def _populate_list(self):
        self.fund_list.clear()
        self._fund_widgets = []
        for fund in self.funds:
            short_name = simplify_fund_name(fund["name"])
            pos = self.store.load_position(fund["code"])
            shares = pos.get("shares", 0)

            # 构建列表项 widget
            item_widget = QWidget()
            item_widget.setMinimumHeight(56)
            item_widget.setProperty("selected", False)
            item_widget.setStyleSheet(self.UNSELECTED_STYLE)
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 6, 6, 6)
            item_layout.setSpacing(2)

            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            code_label = QLabel(fund["code"])
            code_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; background: transparent;")
            top_row.addWidget(code_label)

            if shares > 0:
                badge = QLabel("持有")
                badge.setStyleSheet(self.BADGE_HELD_STYLE)
                top_row.addWidget(badge)

            top_row.addStretch()
            item_layout.addLayout(top_row)

            name_label = QLabel(short_name)
            name_label.setStyleSheet("font-size: 12px; color: #7f8c8d; background: transparent;")
            item_layout.addWidget(name_label)

            self._fund_widgets.append(item_widget)
            item = QListWidgetItem()
            item.setData(1, fund["code"])
            item.setSizeHint(QSize(0, 56))
            self.fund_list.addItem(item)
            self.fund_list.setItemWidget(item, item_widget)

        self._update_list_selection(self.fund_list.currentRow())

    def _update_list_selection(self, selected_row: int):
        """更新列表选中样式，不影响子控件"""
        for i, w in enumerate(self._fund_widgets):
            if i == selected_row:
                w.setProperty("selected", True)
                w.setStyleSheet(self.SELECTED_STYLE)
            else:
                w.setProperty("selected", False)
                w.setStyleSheet(self.UNSELECTED_STYLE)

    def _on_fund_selected(self, row: int):
        """选中基金时自动加载数据"""
        self._update_list_selection(row)
        if row < 0:
            return
        fund = self.funds[row]
        self.current_code = fund["code"]
        self._load_position_fields(fund["code"])
        self._load_fund(fund["code"], fund["name"])

    def _load_fund(self, code: str, name: str):
        """加载基金数据"""
        self.fund_title.setText(f"⏳ 正在加载 {simplify_fund_name(name)} ({code})...")
        self.progress.setVisible(True)
        self.status_time.setText("正在获取数据...")

        # 优先本地缓存
        if self.store.exists(code):
            try:
                df = self.store.load(code)
                if not df.empty:
                    self._update_display(df, name)
                    self.status_time.setText(f"数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    self.progress.setVisible(False)
                    return
            except Exception:
                pass  # 缓存读取失败，重新从网络获取

        # 后台线程获取
        self.fetch_thread = FetchThread(code)
        self.fetch_thread.finished.connect(lambda c, d: self._on_data_fetched(c, d, name))
        self.fetch_thread.error.connect(self._on_fetch_error)
        self.fetch_thread.start()

    def _on_data_fetched(self, code: str, df, name: str):
        self.progress.setVisible(False)
        if df is None or df.empty:
            self.fund_title.setText(f"❌ {simplify_fund_name(name)} ({code}) — 无数据返回")
            QMessageBox.warning(self, "数据获取失败",
                                f"无法获取基金 {code} 的数据。\n\n可能原因：\n• 网络连接异常\n• 基金代码不存在\n• 数据源暂时不可用")
            self.status_time.setText("数据获取失败")
            return
        try:
            self.store.save(code, df)
        except Exception:
            pass
        self._update_display(df, name)
        self.status_time.setText(f"数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _on_fetch_error(self, code: str, error: str):
        self.progress.setVisible(False)
        self.fund_title.setText(f"❌ 基金 {code} — 获取出错")
        QMessageBox.critical(self, "错误", f"获取基金 {code} 数据出错：\n{error}")
        self.status_time.setText(f"获取出错：{error[:50]}")

    def _update_display(self, df, name: str):
        """用数据更新所有界面组件"""
        self.current_df = df
        self.current_summary = self.analyzer.get_summary(df, name)
        self.fund_title.setText(f"{simplify_fund_name(name)} ({self.funds[self.fund_list.currentRow()]['code'] if self.fund_list.currentRow() >= 0 else '?'})")

        try:
            self._draw_nav_chart(df)
            self._draw_bar_chart(df)
        except Exception as e:
            pass  # 图表绘制出错，静默处理

        self._update_metrics(self.current_summary)
        self._update_position_display()
        self._update_advice(self.current_summary)

    # ─── 图表绘制 ────────────────────────────────────────
    def _draw_nav_chart(self, df):
        ax = self.nav_canvas.ax
        ax.clear()

        dates = df["净值日期"]
        nav = df["单位净值"]
        ma5 = self.analyzer.calc_ma(df, 5)
        ma20 = self.analyzer.calc_ma(df, 20)

        ax.plot(dates, nav, color="#3498db", linewidth=2, label="单位净值", zorder=3)
        ax.plot(dates, ma5, color="#e67e22", linewidth=1.2,
                linestyle="--", label="MA5", zorder=2)
        ax.plot(dates, ma20, color="#e74c3c", linewidth=1.2,
                linestyle="--", label="MA20", zorder=2)

        ax.fill_between(dates, ma5, ma20, where=(ma5 >= ma20),
                        color="#2ecc71", alpha=0.08)
        ax.fill_between(dates, ma5, ma20, where=(ma5 < ma20),
                        color="#e74c3c", alpha=0.08)

        latest_date = dates.iloc[-1]
        latest_nav = nav.iloc[-1]
        ax.annotate(f"{latest_nav:.4f}",
                    xy=(latest_date, latest_nav),
                    xytext=(15, 10), textcoords="offset points",
                    fontsize=10, fontweight="bold", color="#3498db",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                              edgecolor="#3498db", alpha=0.9))

        ax.set_title("基金净值走势图", fontsize=14, fontweight="bold", color="#2c3e50", pad=10)
        ax.set_ylabel("单位净值", fontsize=11, color="#7f8c8d")
        ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.set_facecolor("#fafbfc")
        self.nav_canvas.draw()

    def _draw_bar_chart(self, df):
        ax = self.bar_canvas.ax
        ax.clear()

        recent = df.tail(60)
        dates = recent["净值日期"]
        changes = recent["日增长率"].astype(float)
        colors = ["#27ae60" if v < 0 else "#e74c3c" for v in changes]

        ax.bar(dates, changes, color=colors, width=0.8, alpha=0.85)
        ax.axhline(y=0, color="#bdc3c7", linewidth=0.8)

        ax.set_title("每日涨跌幅（近60个交易日）", fontsize=14, fontweight="bold", color="#2c3e50", pad=10)
        ax.set_ylabel("涨跌幅 (%)", fontsize=11, color="#7f8c8d")
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=2, symbol="%"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.grid(True, axis="y", alpha=0.3, linestyle="--")
        ax.set_facecolor("#fafbfc")
        self.bar_canvas.draw()

    # ─── 指标卡片 ────────────────────────────────────────
    def _update_metrics(self, summary: dict):
        # 清空旧布局
        while self.metrics_grid.count():
            item = self.metrics_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        metrics = [
            ("最新净值", summary.get("最新净值"), "#3498db"),
            ("最新日涨跌幅(%)", f"{summary.get('最新日涨跌幅(%)', 0):+.2f}%",
             "#27ae60" if (summary.get('最新日涨跌幅(%)', 0) or 0) < 0 else "#e74c3c"),
            ("近1周收益(%)", f"{summary.get('近1周收益(%)', 0) or 0:+.2f}%",
             "#27ae60" if (summary.get('近1周收益(%)', 0) or 0) < 0 else "#e74c3c"),
            ("近1月收益(%)", f"{summary.get('近1月收益(%)', 0) or 0:+.2f}%",
             "#27ae60" if (summary.get('近1月收益(%)', 0) or 0) < 0 else "#e74c3c"),
            ("近3月收益(%)", f"{summary.get('近3月收益(%)', 0) or 0:+.2f}%",
             "#27ae60" if (summary.get('近3月收益(%)', 0) or 0) < 0 else "#e74c3c"),
            ("近1年收益(%)", f"{summary.get('近1年收益(%)', 0) or 0:+.2f}%",
             "#27ae60" if (summary.get('近1年收益(%)', 0) or 0) < 0 else "#e74c3c"),
            ("最大回撤(%)", f"{summary.get('最大回撤(%)', 0)}%", "#e74c3c"),
            ("夏普比率", summary.get("夏普比率", "-"), "#8e44ad"),
            ("RSI(14)", summary.get("RSI(14)", "-"), "#2c3e50"),
        ]

        for idx, (label, value, color) in enumerate(metrics):
            card = QFrame()
            card.setStyleSheet("QFrame { background: white; border: 1px solid #eee; border-radius: 8px; padding: 10px; }")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            clayout = QVBoxLayout(card)
            clayout.setSpacing(2)

            val_label = QLabel(str(value))
            val_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")
            val_label.setWordWrap(True)
            clayout.addWidget(val_label)

            desc_label = QLabel(label)
            desc_label.setStyleSheet("font-size: 11px; color: #7f8c8d;")
            desc_label.setWordWrap(True)
            clayout.addWidget(desc_label)

            row, col = divmod(idx, 3)
            self.metrics_grid.addWidget(card, row, col)

    # ─── 投资建议 ────────────────────────────────────────
    def _load_position_fields(self, code: str):
        """加载持仓数据到输入框"""
        pos = self.store.load_position(code)
        self.pos_shares.setText(str(pos.get("shares", "")))
        self.pos_cost.setText(str(pos.get("cost", "")))
        self.pos_base.setText(str(pos.get("base_amount", "")))

    def _save_position(self):
        """保存持仓信息（从持仓操作 Tab 或投资建议 Tab 读取）"""
        code = self.current_code
        if not code:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return

        # 优先读取持仓操作 Tab 的字段
        amount_text = self.edit_amount.text().strip()
        profit_text = self.edit_profit.text().strip()
        base_text = self.edit_base.text().strip()

        latest_nav = (self.current_summary or {}).get("最新净值", 1)

        if amount_text:
            try:
                amount = float(amount_text)
                profit = float(profit_text) if profit_text else 0
                base = float(base_text) if base_text else 1000
                shares = amount / latest_nav if latest_nav > 0 else 0
                cost = (amount - profit) / shares if shares > 0 else 0
            except (ValueError, ZeroDivisionError):
                QMessageBox.warning(self, "输入错误", "请输入有效的数字。")
                return
        else:
            # 兜底读取投资建议 Tab 的旧字段
            try:
                shares = float(self.pos_shares.text()) if self.pos_shares.text() else 0
                cost = float(self.pos_cost.text()) if self.pos_cost.text() else 0
                base = float(self.pos_base.text()) if self.pos_base.text() else 1000
            except ValueError:
                QMessageBox.warning(self, "输入错误", "请输入有效的数字。")
                return

        # 保留已有的定投频率配置
        old_pos = self.store.load_position(code) or {}
        dca_freq = old_pos.get("dca_freq", None)

        pos = {"shares": round(shares, 2), "cost": round(cost, 4), "base_amount": base}
        if dca_freq:
            pos["dca_freq"] = dca_freq
        self.store.save_position(code, pos)

        # 回填到持仓操作 Tab 显示
        self._update_position_display(pos)

        # 同步到投资建议 Tab
        self.pos_shares.setText(str(round(shares, 2)))
        self.pos_cost.setText(str(round(cost, 4)))
        self.pos_base.setText(str(base))
        self.pos_status_label.setText(f"✅ 已同步！持有 ¥{amount:,.0f}，收益 ¥{profit:+,.0f}")

        # 刷新左栏持仓标签
        self._populate_list()

        # 刷新建议
        if self.current_summary:
            self._update_advice(self.current_summary)

    def _update_position_display(self, pos: dict = None):
        """更新持仓操作 Tab 的当前持仓展示"""
        if pos is None and self.current_code:
            pos = self.store.load_position(self.current_code)
        if not pos:
            # 无持仓数据，清空显示
            self.cur_amount_label.setText("—")
            self.cur_profit_label.setText("—")
            self.cur_shares_label.setText("—")
            self.cur_cost_label.setText("—")
            self.edit_amount.clear()
            self.edit_profit.clear()
            self.edit_base.clear()
            return

        shares = pos.get("shares", 0)
        cost = pos.get("cost", 0)
        base = pos.get("base_amount", 1000)
        latest_nav = (self.current_summary or {}).get("最新净值", 0) or 0

        amount = shares * latest_nav
        profit = shares * (latest_nav - cost)

        self.cur_amount_label.setText(f"¥{amount:,.2f}")
        color = "#e74c3c" if profit >= 0 else "#27ae60"
        self.cur_profit_label.setText(f"¥{profit:+,.2f}")
        self.cur_profit_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        self.cur_shares_label.setText(f"{shares:,.2f} 份")
        self.cur_cost_label.setText(f"¥{cost:,.4f}")

        # 回填编辑框（每次切换基金都更新，确保数据隔离）
        self.edit_amount.setText(f"{amount:.2f}")
        self.edit_profit.setText(f"{profit:.2f}")
        self.edit_base.setText(f"{base:.0f}")

    def _sync_add(self):
        """同步加仓：直接增加持有金额"""
        if not self.current_code:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return

        current_amount = float(self.edit_amount.text() or 0)

        add_amount, ok = QInputDialog.getDouble(
            self, "同步加仓", "请输入加仓金额（元）：",
            1000, 0, 99999999, 2,
        )
        if not ok or add_amount <= 0:
            return

        current_profit = float(self.edit_profit.text() or 0)
        new_amount = current_amount + add_amount
        # 按比例调整收益（新增部分无收益）
        self.edit_amount.setText(f"{new_amount:.2f}")
        self._save_position()

        QMessageBox.information(self, "加仓完成",
                                f"持有金额 ¥{current_amount:,.0f} → ¥{new_amount:,.0f}\n"
                                f"本次加仓 ¥{add_amount:,.0f}")

    def _sync_reduce(self):
        """同步减仓：直接减少持有金额"""
        if not self.current_code:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return

        current_amount = float(self.edit_amount.text() or 0)
        if current_amount <= 0:
            QMessageBox.information(self, "提示", "当前无持仓金额，无法减仓。")
            return

        reduce_amount, ok = QInputDialog.getDouble(
            self, "同步减仓", "请输入减仓金额（元）：",
            min(1000, current_amount), 0, current_amount, 2,
        )
        if not ok or reduce_amount <= 0:
            return

        new_amount = current_amount - reduce_amount
        # 按比例调整收益
        if current_amount > 0:
            profit = float(self.edit_profit.text() or 0)
            profit = profit * (new_amount / current_amount) if new_amount > 0 else 0
            self.edit_profit.setText(f"{profit:.2f}")

        self.edit_amount.setText(f"{new_amount:.2f}")
        self._save_position()

        QMessageBox.information(self, "减仓完成",
                                f"持有金额 ¥{current_amount:,.0f} → ¥{new_amount:,.0f}\n"
                                f"本次减仓 ¥{reduce_amount:,.0f}")

    def _sync_dca(self):
        """同步定投：弹出定投设置对话框，直接增加持有金额"""
        if not self.current_code:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return

        pos_data = self.store.load_position(self.current_code) or {}
        base = pos_data.get("base_amount", 1000)

        dialog = DCADialog(current_base=base, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        dca_amount, freq = dialog.get_result()

        freq_label = {"daily": "每天", "weekly": "每周", "monthly": "每月"}.get(freq, freq)

        # 更新定投基准和频率到编辑框
        self.edit_base.setText(f"{dca_amount:.0f}")

        # 保存定投频率配置
        old_pos = self.store.load_position(self.current_code) or {}
        old_pos["dca_freq"] = freq
        self.store.save_position(self.current_code, old_pos)

        # 增加本期定投金额到持仓
        current_amount = float(self.edit_amount.text() or 0)
        new_amount = current_amount + dca_amount
        self.edit_amount.setText(f"{new_amount:.2f}")
        self._save_position()

        QMessageBox.information(self, "定投完成",
                                f"定投频率: {freq_label}\n"
                                f"持仓金额 ¥{current_amount:,.0f} → ¥{new_amount:,.0f}\n"
                                f"本期定投 ¥{dca_amount:,.0f}")

    def _on_page_changed(self, index: int):
        """切换到账户汇总时自动刷新"""
        if index == 0:  # 账户汇总页
            self._refresh_account_summary()

    def _refresh_account_summary(self):
        """刷新账户汇总表（后台线程，不卡 UI）"""
        if not self.funds:
            return  # 无自选基金，静默跳过

        if self._summary_loading:
            return  # 防止重复加载

        self._summary_loading = True
        self.status_time.setText("正在获取板块和重仓数据...")

        # 先填充基础数据（无需网络），让表格立即可见
        self._render_account_summary({}, {})

        # 后台线程加载板块和重仓数据
        self.summary_thread = SummaryFetchThread(self.funds)
        self.summary_thread.finished.connect(self._on_summary_data_ready)
        self.summary_thread.start()

    def _on_summary_data_ready(self, sector_map: dict, fund_holdings_map: dict, stock_changes: dict):
        """后台数据就绪，渲染完整表格"""
        self._summary_loading = False
        self._render_account_summary(sector_map, fund_holdings_map, stock_changes)
        self.status_time.setText(f"账户汇总已更新 — {datetime.now().strftime('%H:%M:%S')}")

    def _render_account_summary(self, sector_map: dict, fund_holdings_map: dict, stock_changes: dict = None):
        """渲染账户汇总表格（仅显示持有金额 > 0 的基金）"""
        if stock_changes is None:
            stock_changes = {}

        # 筛选有持仓的基金
        held = []
        for fund in self.funds:
            pos = self.store.load_position(fund["code"])
            shares = pos.get("shares", 0)
            if shares <= 0:
                continue
            nav = 0
            if self.store.exists(fund["code"]):
                try:
                    df = self.store.load(fund["code"])
                    if not df.empty:
                        nav = df.iloc[-1]["单位净值"]
                except Exception:
                    pass
            amount = shares * nav
            if amount <= 0:
                continue
            held.append((fund, pos, nav))

        table = self.summary_table
        table.setRowCount(len(held))

        total_amount = 0
        total_profit = 0
        total_daily = 0

        for row, (fund, pos, nav) in enumerate(held):
            code = fund["code"]
            name = simplify_fund_name(fund["name"])

            daily_pct = 0
            if nav > 0 and self.store.exists(code):
                try:
                    df = self.store.load(code)
                    if not df.empty:
                        daily_pct = float(df.iloc[-1]["日增长率"]) if "日增长率" in df.columns else 0
                except Exception:
                    pass

            shares = pos.get("shares", 0)
            cost = pos.get("cost", 0)
            amount = shares * nav if nav > 0 else 0
            profit_amt = shares * (nav - cost) if nav > 0 and shares > 0 else 0
            profit_pct = ((nav - cost) / cost * 100) if cost > 0 and nav > 0 else 0
            daily_amt = amount * daily_pct / 100 if amount > 0 else 0

            total_amount += amount
            total_profit += profit_amt
            total_daily += daily_amt

            sector = self.fetcher.guess_fund_sector(fund["name"])
            sector_change = sector_map.get(sector, 0) if sector else 0

            hld_avg = None
            holdings = fund_holdings_map.get(code, {})
            if holdings:
                hld_weighted = 0
                hld_total_weight = 0
                for s in holdings.get("stocks", []):
                    sc = stock_changes.get(s["code"], 0)
                    hld_weighted += sc * s["weight"]
                    hld_total_weight += s["weight"]
                hld_avg = round(hld_weighted / hld_total_weight, 2) if hld_total_weight > 0 else None

            # 是否还在加载中
            loading = not bool(sector_map or fund_holdings_map)

            def make_item(text, color="#2c3e50", bold=False):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color))
                if bold:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                return item

            table.setItem(row, 0, make_item(f"{name}\n{code}", "#2c3e50", True))
            table.setItem(row, 1, make_item(f"¥{amount:,.0f}" if amount > 0 else "—"))

            p_color = "#e74c3c" if profit_amt >= 0 else "#27ae60"
            table.setItem(row, 2, make_item(f"¥{profit_amt:+,.0f}" if shares > 0 else "—", p_color))
            table.setItem(row, 3, make_item(f"{profit_pct:+.2f}%" if cost > 0 else "—", p_color))

            d_color = "#e74c3c" if daily_pct >= 0 else "#27ae60"
            table.setItem(row, 4, make_item(f"¥{daily_amt:+,.0f}" if amount > 0 else "—", d_color))
            table.setItem(row, 5, make_item(f"{daily_pct:+.2f}%" if daily_pct != 0 else "—", d_color))

            if loading:
                table.setItem(row, 6, make_item("加载中...", "#95a5a6"))
                table.setItem(row, 7, make_item("...", "#95a5a6"))
                table.setItem(row, 8, make_item("...", "#95a5a6"))
            else:
                table.setItem(row, 6, make_item(sector or "—", "#7f8c8d" if not sector else "#2c3e50"))
                sc_color = "#e74c3c" if sector_change >= 0 else "#27ae60"
                table.setItem(row, 7, make_item(f"{sector_change:+.2f}%" if sector else "—", sc_color if sector else "#95a5a6"))

                if hld_avg is not None:
                    hld_color = "#e74c3c" if hld_avg >= 0 else "#27ae60"
                    table.setItem(row, 8, make_item(f"{hld_avg:+.2f}%", hld_color))
                else:
                    table.setItem(row, 8, make_item("—", "#95a5a6"))

            table.setRowHeight(row, 52)

        self.total_amount_label.setText(f"总持仓: ¥{total_amount:,.0f}")
        tp_color = "#e74c3c" if total_profit >= 0 else "#27ae60"
        self.total_profit_label.setText(f"总收益: ¥{total_profit:+,.0f}")
        self.total_profit_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {tp_color}; padding: 4px 8px;")
        td_color = "#e74c3c" if total_daily >= 0 else "#27ae60"
        self.total_daily_label.setText(f"今日收益: ¥{total_daily:+,.0f}")
        self.total_daily_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {td_color}; padding: 4px 8px;")

    def _update_advice(self, summary: dict):
        """用科学模型更新投资建议"""
        # 构建持仓
        pos = Position()
        if self.current_code:
            p = self.store.load_position(self.current_code)
            if p:
                pos = Position(
                    shares=float(p.get("shares", 0)),
                    cost=float(p.get("cost", 0)),
                    base_amount=float(p.get("base_amount", 1000)),
                )

        # PE分位（暂用技术面替代，后续可接入akshare指数PE数据）
        pe_pct = None
        # TODO: 通过 akshare 获取指数PE分位
        # pe_pct = cls._get_pe_percentile(self.current_code)

        fund_name = ""
        if self.fund_list.currentRow() >= 0:
            fund_name = self.funds[self.fund_list.currentRow()]["name"]

        result = self.advisor.evaluate(summary, pos, pe_pct, fund_name)

        # 横幅
        bg_color, _ = LEVEL_COLORS.get(
            result.level,
            LEVEL_COLORS.get("【持有】", ("#95a5a6", "#ecf0f1"))
        )
        self.advice_banner.setStyleSheet(
            f"background-color: {bg_color}; border-radius: 10px; padding: 14px;"
        )
        self.advice_level_label.setText(result.level)
        self.advice_desc_label.setText(result.description)

        # 操作建议数值
        if result.suggested_amount > 0:
            self.ops_dca_label.setText(
                f"¥{result.suggested_amount:,.0f}（{result.multiplier}x 基准）| PE分位: {result.pe_tier_label or '无数据'}"
            )
        elif result.multiplier == 0 and pos.shares > 0:
            self.ops_dca_label.setText("⏸️ 暂停买入 | 高估区域，资金转货币基金")
        else:
            self.ops_dca_label.setText("📊 输入持仓后可获得定投建议")

        if result.grid_action_amount > 0:
            self.ops_grid_label.setText(
                f"{result.grid_signal} ¥{result.grid_action_amount:,.0f} | 偏离成本触发"
            )
        else:
            self.ops_grid_label.setText(result.grid_signal if result.grid_signal else "未触发 | 输入成本后生效")

        if result.position_value > 0:
            color = "🔴" if result.profit_loss >= 0 else "🟢"
            self.ops_position_label.setText(
                f"市值 ¥{result.position_value:,.0f} | {color} ¥{result.profit_loss:+,.0f}（{result.profit_loss_pct:+.1f}%）"
            )
        else:
            self.ops_position_label.setText("输入持仓信息后显示")

        # 理由
        reason_text = ""
        for i, r in enumerate(result.reasons, 1):
            if any(w in r for w in ["机会", "良机", "加仓", "低估", "超卖", "向好", "优秀"]):
                icon = "✅"
            elif any(w in r for w in ["高估", "止盈", "止损", "清仓", "超买", "减持"]):
                icon = "⚠️"
            else:
                icon = "ℹ️"
            reason_text += f"{icon} {r}\n"
        self.reasons_label.setText(reason_text)

    # ─── 操作按钮 ────────────────────────────────────────
    def _refresh(self):
        """刷新当前选中基金的数据"""
        row = self.fund_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return
        fund = self.funds[row]
        self._load_fund(fund["code"], fund["name"])
        """刷新当前选中基金的数据"""
        row = self.fund_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return
        fund = self.funds[row]
        self._load_fund(fund["code"], fund["name"])

    def _add_fund(self):
        dialog = AddFundDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            code, name = dialog.get_fund()
            if not code:
                return

            # 如果没填名称，尝试自动获取
            if not name:
                try:
                    info = self.fetcher.get_fund_info(code)
                    # 基金简称已含 A/C（如 东方阿尔法科技智选混合发起C）
                    raw = info.get("基金简称", "")
                    if not raw:
                        for v in info.values():
                            if isinstance(v, str) and len(v) > 2:
                                raw = v
                                break
                    name = simplify_fund_name(raw) if raw else ""
                except Exception:
                    pass
                if not name:
                    name = f"基金{code}"  # 兜底名称
            else:
                name = simplify_fund_name(name)  # 手动输入的名称也简化

            # 去重检查
            for f in self.funds:
                if f["code"] == code:
                    QMessageBox.information(self, "提示", f"基金 {code} 已在自选列表中。")
                    return

            self.funds.append({"code": code, "name": name})
            self.store.save_watchlist(self.funds)
            self._populate_list()
            self.fund_list.setCurrentRow(len(self.funds) - 1)
            self.status_time.setText(f"已添加 {name} ({code})，选中后自动加载数据")

    def _delete_fund(self):
        """删除选中的自选基金"""
        row = self.fund_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return
        fund = self.funds[row]
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {simplify_fund_name(fund['name'])} ({fund['code']}) 吗？\n（基金数据缓存不会被删除）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        del self.funds[row]
        if row < len(self._fund_widgets):
            del self._fund_widgets[row]
        self.store.save_watchlist(self.funds)
        self.fund_list.takeItem(row)
        if self.funds and row >= len(self.funds):
            self.fund_list.setCurrentRow(len(self.funds) - 1)
        self.status_time.setText("已删除")

    def _on_context_menu(self, pos):
        """基金列表右键菜单"""
        item = self.fund_list.itemAt(pos)
        if not item:
            return
        self.fund_list.setCurrentItem(item)
        menu = QMenu(self)
        delete_action = menu.addAction("✕ 删除")
        delete_action.triggered.connect(self._delete_fund)
        menu.exec(self.fund_list.viewport().mapToGlobal(pos))

    def _export(self):
        if self.current_df is None:
            QMessageBox.information(self, "导出", "暂无数据可导出，请先加载基金数据。")
            return
        from pathlib import Path
        path = Path(f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        self.current_df.to_csv(path, index=False, encoding="utf-8-sig")
        QMessageBox.information(self, "导出成功", f"数据已导出至：\n{path.absolute()}")
        self.status_time.setText(f"已导出：{path.absolute()}")

    def _edit_thresholds(self):
        QMessageBox.information(self, "告警阈值",
                                f"当前配置：\n"
                                f"日涨跌幅告警：±{THRESHOLDS['daily_change_warn']}%\n"
                                f"最大回撤告警：{THRESHOLDS['max_drawdown_warn']}%\n"
                                f"连续下跌告警：{THRESHOLDS['consecutive_drop_days']}天\n\n"
                                f"请编辑 config/settings.py 修改阈值。")

    def _about(self):
        QMessageBox.about(self, "关于 XFund",
                          "<h2>XFund v1.0</h2>"
                          "<p>基金智能分析与建议系统</p>"
                          "<p>数据来源：天天基金 / 东方财富（akshare）</p>"
                          "<br>"
                          "<p style='color:#95a5a6;'>⚠️ 本系统仅供参考，不构成投资建议。</p>")


def main():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("XFund")

        # 设置应用图标
        from pathlib import Path
        icon_path = Path(__file__).parent.parent.parent / "assets" / "xfund.ico"
        if icon_path.exists():
            from PySide6.QtGui import QIcon
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
