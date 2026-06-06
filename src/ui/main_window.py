"""
XFund 主窗口 — MainWindow 类
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

from PySide6.QtWidgets import (
    QMainWindow, QInputDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton,
    QMenu, QGroupBox, QGridLayout, QFrame,
    QSplitter, QMessageBox, QProgressBar, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QApplication,
    QLineEdit, QDialog,
)
from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QColor, QFont, QIcon

from config.settings import THRESHOLDS
from src.data.fetcher import FundFetcher
from src.analysis.calculator import FundAnalyzer
from src.strategy.advisor import FundAdvisor, Position
from src.storage.database import DataStore

from src.ui.styles import STYLE, LEVEL_COLORS
from src.ui.dialogs import DCADialog, AddFundDialog
from src.ui.threads import FetchThread, SummaryFetchThread
from src.ui.canvas import MplCanvas

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
        self.resize(1200, 900)
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
        central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(0)

        # ── 圆角容器（所有内容放这里）──
        container = QWidget()
        container.setObjectName("mainContainer")
        container.setStyleSheet(
            "#mainContainer {"
            "  background-color: white;"
            "  border-radius: 14px;"
            "  border: 1px solid #d0d3d8;"
            "}"
        )

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── 自定义标题栏 ──
        title_bar = QWidget()
        title_bar.setFixedHeight(42)
        title_bar.setStyleSheet(
            "background: white; border-top-left-radius: 14px; border-top-right-radius: 14px;"
            "border-bottom: 1px solid #e0e0e0;"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(14, 0, 8, 0)

        # 图标
        icon_path = Path(__file__).parent.parent.parent / "assets" / "xfund.ico"
        if icon_path.exists():
            icon_label = QLabel()
            icon_label.setPixmap(QIcon(str(icon_path)).pixmap(22, 22))
            icon_label.setStyleSheet("background: transparent;")
            tb_layout.addWidget(icon_label)

        logo = QLabel("XFund")
        logo.setStyleSheet("color: #1a1a2e; font-size: 14px; font-weight: bold; background: transparent;")
        tb_layout.addWidget(logo)

        # 标题栏菜单按钮（去除下拉箭头）
        menu_btn_style = (
            "QPushButton { background: transparent; color: #555; border: none; "
            "padding: 6px 14px; font-size: 15px; border-radius: 4px; }"
            "QPushButton:hover { background: #f0f0f0; color: #1a1a2e; }"
            "QPushButton::menu-indicator { image: none; }"
        )

        def make_menu(text, actions: list):
            btn = QPushButton(text)
            btn.setStyleSheet(menu_btn_style)
            menu = QMenu(btn)
            menu.setStyleSheet(
                "QMenu { background: white; color: #2c3e50; border: 1px solid #ddd; padding: 4px; border-radius: 6px; }"
                "QMenu::item { padding: 6px 24px; }"
                "QMenu::item:selected { background: #3498db; color: white; }"
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

        win_btn_base = (
            "QPushButton { background: transparent; color: #666; border: none; "
            "font-size: 10px; padding: 6px 12px; border-radius: 4px; "
            "font-family: 'Segoe MDL2 Assets', 'Segoe UI', Arial; }"
            "QPushButton:hover { background: #e8e8e8; color: #333; }"
        )
        btn_min = QPushButton("")
        btn_min.setStyleSheet(win_btn_base)
        btn_min.clicked.connect(self.showMinimized)
        tb_layout.addWidget(btn_min)

        btn_max = QPushButton("")
        btn_max.setStyleSheet(win_btn_base)
        btn_max.clicked.connect(self._toggle_maximize)
        tb_layout.addWidget(btn_max)

        btn_close = QPushButton("")
        btn_close.setStyleSheet(win_btn_base + "QPushButton:hover { background: #e74c3c; color: white; }")
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
        self.page_tabs.setObjectName("pageTabs")

        # ===== Page 0: 账户汇总 =====
        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        summary_layout.setSpacing(8)

        summary_toolbar = QHBoxLayout()
        summary_toolbar.addStretch()

        refresh_summary_btn = QPushButton("⭮ 刷新汇总")
        refresh_summary_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 8px 20px; border-radius: 5px; font-size: 13px; }"
            "QPushButton:hover { background: #2980b9; }"
        )
        refresh_summary_btn.clicked.connect(self._refresh_account_summary)
        summary_toolbar.addWidget(refresh_summary_btn)
        summary_layout.addLayout(summary_toolbar)

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(8)
        self.summary_table.setHorizontalHeaderLabels([
            "基金名称", "持有金额", "持有收益", "当日收益",
            "本周收益", "本月收益", "关联板块", "重仓均涨幅",
        ])
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 8):
            self.summary_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self.summary_table.setColumnWidth(1, 90)
        self.summary_table.setColumnWidth(2, 100)
        self.summary_table.setColumnWidth(3, 100)
        self.summary_table.setColumnWidth(4, 100)
        self.summary_table.setColumnWidth(5, 100)
        self.summary_table.setColumnWidth(6, 100)
        self.summary_table.setColumnWidth(7, 95)
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.setStyleSheet(
            "QTableWidget { background: white; border: 1px solid #ddd; border-radius: 6px; "
            "gridline-color: #eee; font-size: 16px; outline: none; }"
            "QTableWidget::item { padding: 8px 12px; outline: none; }"
            "QHeaderView::section { background: #f0f2f5; padding: 10px 8px; "
            "font-weight: bold; font-size: 15px; color: #2c3e50; border: none; border-bottom: 2px solid #ddd; }"
            "QTableWidget::item:alternate { background: #fafbfc; }"
        )
        self.summary_table.setWordWrap(True)
        self.summary_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.summary_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        summary_layout.addWidget(self.summary_table)

        total_bar = QHBoxLayout()
        self.total_amount_label = QLabel("总持仓: —")
        self.total_amount_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 4px 8px;")
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
        splitter.setHandleWidth(1)

        # ── 左侧面板：基金列表 ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 操作按钮（正方形，无文字）
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        sq_style = (
            "QPushButton { background: white; border: 1px solid #d5d8dc; border-radius: 5px; "
            "min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; "
            "font-size: 14px; padding: 0px; }"
        )
        refresh_btn = QPushButton("⭮")
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

        # 基金列表（自定义滚动区域，无内置缩进）
        self.fund_scroll = QScrollArea()
        self.fund_scroll.setWidgetResizable(True)
        self.fund_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fund_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fund_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fund_scroll.setStyleSheet("QScrollArea { background: white; border: none; }")
        self.fund_container = QWidget()
        self.fund_container.setStyleSheet("background: white;")
        self.fund_layout = QVBoxLayout(self.fund_container)
        self.fund_layout.setContentsMargins(0, 0, 0, 0)
        self.fund_layout.setSpacing(0)
        self.fund_layout.addStretch()
        self.fund_scroll.setWidget(self.fund_container)
        left_layout.addWidget(self.fund_scroll)

        self._fund_widgets = []
        self._selected_fund_index = -1
        self._populate_list()

        # ── 右侧面板 ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.fund_title = QLabel("")
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

        # --- Tab 3: 投资建议 ---
        self.advice_scroll = QScrollArea()
        self.advice_scroll.setWidgetResizable(True)
        self.advice_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.advice_tab = QWidget()
        self.advice_scroll.setWidget(self.advice_tab)
        advice_layout = QVBoxLayout(self.advice_tab)
        advice_layout.setSpacing(12)

        # 建议横幅
        self.advice_banner = QFrame()
        self.advice_banner = QFrame()
        self.advice_banner.setFixedHeight(150)
        self.advice_banner.setStyleSheet("border-radius: 10px; background-color: #bdc3c7;")
        banner_layout = QVBoxLayout(self.advice_banner)
        banner_layout.setContentsMargins(12, 12, 12, 12)
        banner_layout.setSpacing(8)
        self.advice_level_label = QLabel("等待数据加载...")
        self.advice_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_level_label.setStyleSheet("font-size: 22px; font-weight: bold; color: white;")
        self.advice_desc_label = QLabel("请先选择基金并加载数据")
        self.advice_desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_desc_label.setStyleSheet("font-size: 17px; color: rgba(255,255,255,0.95);")
        self.advice_action_label = QLabel("")
        self.advice_action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_action_label.setStyleSheet("font-size: 15px; font-weight: bold; color: rgba(255,255,255,0.95);")
        self.advice_action_label.setFixedHeight(24)  # 固定高度，有无内容都不变
        banner_layout.addStretch()
        banner_layout.addWidget(self.advice_level_label)
        banner_layout.addWidget(self.advice_desc_label)
        banner_layout.addWidget(self.advice_action_label)
        banner_layout.addStretch()
        advice_layout.addWidget(self.advice_banner)

        # 分析理由
        reasons_group = QGroupBox("分析理由")
        reasons_layout = QVBoxLayout(reasons_group)
        self.reasons_label = QLabel("等待数据加载...")
        self.reasons_label.setStyleSheet("font-size: 15px; line-height: 2.0; color: #2c3e50; padding: 4px;")
        self.reasons_label.setTextFormat(Qt.TextFormat.RichText)
        self.reasons_label.setWordWrap(True)
        reasons_layout.addWidget(self.reasons_label)
        advice_layout.addWidget(reasons_group)

        advice_layout.addStretch()

        self.tabs.addTab(self.advice_scroll, "💡 投资建议")

        right_layout.addWidget(self.tabs)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 1060])

        fund_layout.addWidget(splitter)
        self.page_tabs.addTab(fund_page, "📈 自选基金")

        # 切换到自选基金时自动选中第一只基金
        self.page_tabs.currentChanged.connect(self._on_page_changed)

        # 切换到账户汇总时自动刷新

        content_layout.addWidget(self.page_tabs)

        # 状态栏移入内容区
        self.statusbar_widget = QWidget()
        self.statusbar_widget.setFixedHeight(28)
        self.statusbar_widget.setStyleSheet(
            "background: white; border-bottom-left-radius: 14px; border-bottom-right-radius: 14px;"
            "border-top: 1px solid #e0e0e0;"
        )
        sb_layout = QHBoxLayout(self.statusbar_widget)
        sb_layout.setContentsMargins(14, 0, 14, 0)
        self.status_time = QLabel("就绪 — 请选择基金后点击「刷新数据」")
        self.status_time.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
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
        "QLabel { background: #e74c3c; color: white; border-radius: 2px; "
        "padding: 0px 2px; font-size: 10px; font-weight: bold; border-radius: 1px; max-height: 14px; min-height: 14px; }"
    )

    # 选中指示器样式（用属性选择器避免影响子控件）
    SELECTED_STYLE = (
        "QWidget[selected=\"true\"] { "
        "background-color: #f0f4fa; border-radius: 6px; }"
    )
    UNSELECTED_STYLE = "QWidget[selected=\"true\"] { background: transparent; }"

    def _make_fund_item(self, fund: dict, index: int):
        """创建单个基金列表项"""
        short_name = simplify_fund_name(fund["name"])
        pos = self.store.load_position(fund["code"])
        shares = pos.get("shares", 0)

        frame = QFrame()
        frame.setMinimumHeight(52)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        frame.mousePressEvent = lambda e, i=index: self._on_fund_clicked(i)
        frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        frame.customContextMenuRequested.connect(lambda pos, i=index: self._on_fund_right_click(i, pos))

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 4, 4, 4)
        layout.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        code_label = QLabel(fund["code"])
        code_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50; background: transparent;")
        top_row.addWidget(code_label)

        if shares > 0:
            badge = QLabel("持有")
            badge.setStyleSheet(self.BADGE_HELD_STYLE)
            top_row.addWidget(badge)

        top_row.addStretch()
        layout.addLayout(top_row)

        name_label = QLabel(short_name)
        name_label.setStyleSheet("font-size: 13px; color: #7f8c8d; background: transparent;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(name_label)

        return frame

    def _populate_list(self):
        """重建基金列表"""
        self._fund_widgets = []
        while self.fund_layout.count() > 1:
            item = self.fund_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, fund in enumerate(self.funds):
            w = self._make_fund_item(fund, i)
            self._fund_widgets.append(w)
            self.fund_layout.insertWidget(self.fund_layout.count() - 1, w)

        if self._selected_fund_index >= len(self.funds):
            self._selected_fund_index = -1
        self._update_list_selection(self._selected_fund_index)

    def _on_fund_clicked(self, index: int):
        if index < 0 or index >= len(self.funds):
            return
        self._selected_fund_index = index
        self._update_list_selection(index)
        fund = self.funds[index]
        self.current_code = fund["code"]
        self._load_position_fields(fund["code"])
        self._load_fund(fund["code"], fund["name"])

    def _on_fund_right_click(self, index: int, pos):
        self._on_fund_clicked(index)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; color: #2c3e50; border: 1px solid #ddd; padding: 4px; border-radius: 6px; }"
            "QMenu::item { padding: 6px 24px; }"
            "QMenu::item:selected { background: #3498db; color: white; }"
        )
        delete_action = menu.addAction("✕ 删除")
        delete_action.triggered.connect(lambda: self._delete_fund(index))
        menu.exec(self.fund_container.mapToGlobal(pos))

    def _update_list_selection(self, selected_row: int):
        for i, w in enumerate(self._fund_widgets):
            w.setStyleSheet(
                "QFrame { background-color: #eef2f7; border-radius: 6px; }" if i == selected_row
                else "QFrame { background: transparent; border: none; }"
            )

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
        self.fund_title.setText(f"{simplify_fund_name(name)} ({self.funds[self._selected_fund_index]['code'] if self._selected_fund_index >= 0 else '?'})")

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
        ax.plot(dates, ma5, color="#e67e22", linewidth=1.5,
                linestyle="--", label="MA5", zorder=2)
        ax.plot(dates, ma20, color="#8e44ad", linewidth=1.5,
                linestyle="--", label="MA20", zorder=2)

        ax.fill_between(dates, ma5, ma20, where=(ma5 >= ma20),
                        color="#2ecc71", alpha=0.08)
        ax.fill_between(dates, ma5, ma20, where=(ma5 < ma20),
                        color="#e74c3c", alpha=0.08)

        ax.set_title("基金净值走势图", fontsize=17, fontweight="bold", color="#2c3e50", pad=10)
        ax.set_ylabel("单位净值", fontsize=15, color="#7f8c8d")
        ax.legend(loc="upper left", framealpha=0.9, fontsize=15)
        ax.tick_params(labelsize=15)
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

        ax.set_title("每日涨跌幅（近60个交易日）", fontsize=17, fontweight="bold", color="#2c3e50", pad=10)
        ax.set_ylabel("涨跌幅 (%)", fontsize=15, color="#7f8c8d")
        ax.tick_params(labelsize=15)
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
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            clayout = QVBoxLayout(cell)
            clayout.setContentsMargins(4, 4, 4, 4)
            clayout.setSpacing(0)

            val_label = QLabel(str(value))
            val_label.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {color}; background: transparent;")
            val_label.setWordWrap(True)
            clayout.addWidget(val_label)

            name_label = QLabel(label)
            name_label.setStyleSheet("font-size: 15px; color: #7f8c8d; background: transparent;")
            name_label.setWordWrap(True)
            clayout.addWidget(name_label)

            row, col = divmod(idx, 3)
            self.metrics_grid.addWidget(cell, row, col)

    # ─── 投资建议 ────────────────────────────────────────
    def _load_position_fields(self, code: str):
        """加载持仓数据（占位，实际由持仓操作Tab处理）"""
        pass

    def _save_position(self):
        """保存持仓信息（从持仓操作 Tab 或投资建议 Tab 读取）"""
        code = self.current_code
        if not code:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return

        # 优先读取持仓操作 Tab 的字段
        amount_text = self.edit_amount.text().strip()
        profit_text = self.edit_profit.text().strip()
        base_text = "1000"

        latest_nav = (self.current_summary or {}).get("最新净值", 1)

        if not amount_text:
            QMessageBox.information(self, "提示", "请输入持有金额。")
            return
        try:
            amount = float(amount_text)
            profit = float(profit_text) if profit_text else 0
            base = float(base_text) if base_text else 1000
            shares = amount / latest_nav if latest_nav > 0 else 0
            cost = (amount - profit) / shares if shares > 0 else 0
        except (ValueError, ZeroDivisionError):
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
            return

        shares = pos.get("shares", 0)
        cost = pos.get("cost", 0)
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
        # 默认定投金额 = 持仓的 10%
        try:
            cur_amount = float(self.edit_amount.text() or 0)
            default_base = max(cur_amount * 0.1, 100) if cur_amount > 0 else 1000
        except ValueError:
            default_base = 1000
        base = pos_data.get("base_amount", default_base)

        dialog = DCADialog(current_base=base, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        dca_amount, freq = dialog.get_result()

        freq_label = {"daily": "每天", "weekly": "每周", "monthly": "每月"}.get(freq, freq)

        # 更新定投基准和频率到编辑框

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
        """切换到自选基金时，若未选中则自动选第一只"""
        if index == 1 and self._selected_fund_index < 0 and self.funds:
            self._on_fund_clicked(0)

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
        table.setRowCount(0)  # 清空旧的 cellWidget
        table.setRowCount(len(held))

        total_amount = 0
        total_profit = 0
        total_daily = 0

        for row, (fund, pos, nav) in enumerate(held):
            code = fund["code"]
            name = simplify_fund_name(fund["name"])

            daily_pct = 0
            week_profit = None   # (金额, 百分比)
            month_profit = None  # (金额, 百分比)
            if nav > 0 and self.store.exists(code):
                try:
                    df = self.store.load(code)
                    if not df.empty:
                        daily_pct = float(df.iloc[-1]["日增长率"]) if "日增长率" in df.columns else 0
                        today = datetime.now().date()
                        # 本周一
                        monday = today - timedelta(days=today.weekday())
                        # 本月1日
                        first_day = today.replace(day=1)

                        df_dates = pd.to_datetime(df["净值日期"]).dt.date
                        # 找离周一最近的交易日（≤ 周一，若无则取最早）
                        week_rows = df[df_dates <= monday]
                        if week_rows.empty:
                            week_rows = df.head(1)
                        w_nav = float(week_rows.iloc[-1]["单位净值"])
                        if w_nav > 0:
                            w_amt = shares * (nav - w_nav)
                            w_pct = (nav - w_nav) / w_nav * 100
                            week_profit = (w_amt, w_pct)

                        # 找离1日最近的交易日（≤ 1日，若无则取最早）
                        month_rows = df[df_dates <= first_day]
                        if month_rows.empty:
                            month_rows = df.head(1)
                        m_nav = float(month_rows.iloc[-1]["单位净值"])
                        if m_nav > 0:
                            m_amt = shares * (nav - m_nav)
                            m_pct = (nav - m_nav) / m_nav * 100
                            month_profit = (m_amt, m_pct)
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

            loading = not bool(sector_map or fund_holdings_map)

            def make_text_item(text, color="#2c3e50", bold=False):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color))
                if bold:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                return item

            def make_stacked_widget(top_text, bottom_text, color, top_bold=True):
                bold = "font-weight: bold;" if top_bold else ""
                html = (
                    f"<div style='text-align:center;font-size:16px;{bold}color:{color};margin:0'>"
                    f"{top_text}</div>"
                    f"<div style='text-align:center;font-size:15px;color:{color};margin:0'>"
                    f"{bottom_text}</div>"
                )
                label = QLabel(html)
                label.setStyleSheet("background: transparent;")
                label.setTextFormat(Qt.TextFormat.RichText)
                return label

            name_item = make_text_item(f"{code}\n{name}", "#2c3e50", True)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_item.setToolTip(f"{code}\n{fund['name']}")
            table.setItem(row, 0, name_item)

            table.setItem(row, 1, make_text_item(f"¥{amount:,.2f}" if amount > 0 else "—"))

            p_color = "#e74c3c" if profit_amt >= 0 else "#27ae60"
            p_amt = f"¥{profit_amt:+,.2f}" if shares > 0 else "—"
            p_pct = f"{profit_pct:+.2f}%" if cost > 0 else "—"
            table.setCellWidget(row, 2, make_stacked_widget(p_amt, p_pct, p_color))

            d_color = "#e74c3c" if daily_pct >= 0 else "#27ae60"
            d_amt = f"¥{daily_amt:+,.2f}" if amount > 0 else "—"
            d_pct = f"{daily_pct:+.2f}%" if daily_pct != 0 else "—"
            table.setCellWidget(row, 3, make_stacked_widget(d_amt, d_pct, d_color))

            # 本周收益
            if week_profit is not None:
                w_amt, w_pct = week_profit
                w_color = "#e74c3c" if w_amt >= 0 else "#27ae60"
                table.setCellWidget(row, 4, make_stacked_widget(
                    f"¥{w_amt:+,.2f}", f"{w_pct:+.2f}%", w_color))
            else:
                table.setItem(row, 4, make_text_item("—", "#95a5a6"))

            # 本月收益
            if month_profit is not None:
                m_amt, m_pct = month_profit
                m_color = "#e74c3c" if m_amt >= 0 else "#27ae60"
                table.setCellWidget(row, 5, make_stacked_widget(
                    f"¥{m_amt:+,.2f}", f"{m_pct:+.2f}%", m_color))
            else:
                table.setItem(row, 5, make_text_item("—", "#95a5a6"))

            # 关联板块 + 重仓均涨幅
            if loading:
                table.setItem(row, 6, make_text_item("...", "#95a5a6"))
                table.setItem(row, 7, make_text_item("...", "#95a5a6"))
            else:
                sc_color = "#e74c3c" if sector_change >= 0 else "#27ae60"
                if sector:
                    table.setCellWidget(row, 6, make_stacked_widget(
                        sector, f"{sector_change:+.2f}%", sc_color, top_bold=False))
                else:
                    table.setItem(row, 6, make_text_item("—", "#95a5a6"))

                if hld_avg is not None:
                    hld_color = "#e74c3c" if hld_avg >= 0 else "#27ae60"
                    table.setItem(row, 7, make_text_item(f"{hld_avg:+.2f}%", hld_color))
                else:
                    table.setItem(row, 7, make_text_item("—", "#95a5a6"))

            table.setRowHeight(row, 64)

        self.total_amount_label.setText(f"总持仓: ¥{total_amount:,.2f}")
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
        if self._selected_fund_index >= 0:
            fund_name = self.funds[self._selected_fund_index]["name"]

        result = self.advisor.evaluate(summary, pos, pe_pct, fund_name)

        # 纯百分比打分算法，记录各指标贡献
        score = 0
        details = []
        rsi = summary.get("RSI(14)")
        if isinstance(rsi, (int, float)):
            if rsi < 25:     score += 20; details.append(f"RSI={rsi:.1f}深度超卖 +20")
            elif rsi < 35:   score += 10; details.append(f"RSI={rsi:.1f}超卖 +10")
            elif rsi > 75:   score -= 20; details.append(f"RSI={rsi:.1f}深度超买 -20")
            elif rsi > 65:   score -= 10; details.append(f"RSI={rsi:.1f}超买 -10")

        ret_1m = summary.get("近1月收益(%)") or 0
        if isinstance(ret_1m, (int, float)):
            if ret_1m < -10:     score += 15; details.append(f"近1月{ret_1m:+.1f}%超跌 +15")
            elif ret_1m < -5:    score += 5;  details.append(f"近1月{ret_1m:+.1f}%下跌 +5")
            elif ret_1m > 15:    score -= 10; details.append(f"近1月{ret_1m:+.1f}%大涨 -10")
            elif ret_1m > 5:     score -= 5;  details.append(f"近1月{ret_1m:+.1f}%上涨 -5")

        ret_3m = summary.get("近3月收益(%)") or 0
        if isinstance(ret_3m, (int, float)):
            if ret_3m < -20:     score += 10; details.append(f"近3月{ret_3m:+.1f}%深跌 +10")
            elif ret_3m > 20:    score -= 5;  details.append(f"近3月{ret_3m:+.1f}%大涨 -5")

        dd = summary.get("最大回撤(%)")
        if isinstance(dd, (int, float)):
            if dd > 20:     score += 10; details.append(f"最大回撤{dd:.1f}%较深 +10")
            elif dd > 10:   score += 5;  details.append(f"最大回撤{dd:.1f}%偏高 +5")

        sharpe = summary.get("夏普比率")
        if isinstance(sharpe, (int, float)):
            if sharpe > 1:     score += 5;  details.append(f"夏普{sharpe:.1f}优秀 +5")
            elif sharpe < 0:   score -= 5;  details.append(f"夏普{sharpe:.1f}为负 -5")

        if score >= 20:     advise_pct, level, desc = 15, "【积极买入】", "多项指标强烈看多"
        elif score >= 10:   advise_pct, level, desc = 10, "【建议加仓】", "多项指标偏乐观"
        elif score >= 3:    advise_pct, level, desc = 5, "【建议加仓】", "部分指标向好"
        elif score >= -3:   advise_pct, level, desc = 0, "【持有观望】", "信号中性，等待明确信号"
        elif score >= -10:  advise_pct, level, desc = -5, "【适度减仓】", "指标偏弱"
        elif score >= -20:  advise_pct, level, desc = -10, "【建议减仓】", "多项指标走弱"
        else:               advise_pct, level, desc = -15, "【果断离场】", "指标全面恶化"

        # 横幅 — 加仓红底，减仓绿底，持有灰底
        if advise_pct > 0:
            bg_color = "#e74c3c"
        elif advise_pct < 0:
            bg_color = "#27ae60"
        else:
            bg_color = "#95a5a6"
        self.advice_banner.setStyleSheet(f"background-color: {bg_color}; border-radius: 10px;")
        self.advice_level_label.setText(level)
        self.advice_desc_label.setText(desc)

        # 操作建议 — 加仓红，减仓绿，持有灰
        if advise_pct > 0:
            act_color = "#e74c3c"
        elif advise_pct < 0:
            act_color = "#27ae60"
        else:
            act_color = "#ccc"
        self.advice_action_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {act_color};")

        nav_val = float(summary.get("最新净值", 0)) if summary.get("最新净值") else 0
        if advise_pct != 0 and pos.shares > 0 and nav_val > 0:
            amt = pos.shares * nav_val * abs(advise_pct) / 100
            self.advice_action_label.setText(f"建议 {advise_pct:+d}%（约¥{amt:,.0f}）")
        elif advise_pct != 0:
            self.advice_action_label.setText(f"建议 {advise_pct:+d}%")
        else:
            self.advice_action_label.setText("持有观望")


        # 分析理由 — 过滤无用信息，数值标色
        skip_keywords = ["正常", "交易日", "盘中", "估算净值", "偏差", "仅", "金字塔"]
        reason_html = ""
        for r in result.reasons:
            if any(kw in r for kw in skip_keywords):
                continue
            # 方向判断：劣势→绿，优势→红。优秀/向好可抵消"风险"一词
            has_bad = any(w in r for w in ["回撤", "亏损", "下跌", "止损", "偏弱"])
            has_good = any(w in r for w in ["优秀", "向好", "偏乐观", "低估", "超卖", "反弹", "机会"])
            has_risk_only = "风险" in r and not has_good
            is_bad = has_bad or has_risk_only
            is_good = has_good
            def colorize(text):
                def _color(m):
                    num_str = m.group()
                    try:
                        val = float(num_str.replace("%", "").replace(",", "").replace("+", ""))
                    except ValueError:
                        return num_str
                    if is_bad:
                        return f'<span style="color:#27ae60;font-weight:bold">{num_str}</span>'
                    if is_good or val > 0:
                        return f'<span style="color:#e74c3c;font-weight:bold">{num_str}</span>'
                    if val < 0:
                        return f'<span style="color:#27ae60;font-weight:bold">{num_str}</span>'
                    return num_str
                # 只标小数(含.)、带符号的数、%结尾的数，不标孤立整数
                return re.sub(r'[+-]\d+\.?\d*%?|\d+\.\d+%?|\d+\.?\d+%', _color, text)
            r_escaped = r.replace("<", "&lt;").replace(">", "&gt;")
            reason_html += f"· {colorize(r_escaped)}<br>"
        self.reasons_label.setText(reason_html)

    # ─── 操作按钮 ────────────────────────────────────────
    def _refresh(self):
        """刷新当前选中基金的数据"""
        row = self._selected_fund_index
        if row < 0:
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return
        fund = self.funds[row]
        self._load_fund(fund["code"], fund["name"])
        """刷新当前选中基金的数据"""
        row = self._selected_fund_index
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
            self._on_fund_clicked(len(self.funds) - 1)
            self.status_time.setText(f"已添加 {name} ({code})，选中后自动加载数据")

    def _delete_fund(self, row: int = -1):
        """删除选中的自选基金"""
        if row < 0:
            row = self._selected_fund_index
        if row < 0 or row >= len(self.funds):
            QMessageBox.information(self, "提示", "请先在左侧选择一只基金。")
            return
        fund = self.funds[row]
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {simplify_fund_name(fund['name'])} ({fund['code']}) 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        del self.funds[row]
        self.store.save_watchlist(self.funds)
        self._selected_fund_index = -1
        self._populate_list()
        self.status_time.setText("已删除")

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
                                f"连续下跌告警：{THRESHOLDS['consecutive_drop_days']}天\n\n")

    def _about(self):
        QMessageBox.about(self, "关于 XFund",
                          "<h2>XFund v1.0</h2>"
                          "<p>基金智能分析与建议系统</p>"
                          "<p>数据来源：天天基金 / 东方财富（akshare）</p>"
                          "<br>"
                          "<p style='color:#95a5a6;'>⚠️ 本系统仅供参考，不构成投资建议。</p>")


