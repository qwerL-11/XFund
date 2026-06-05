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
    QStatusBar, QMenuBar, QMenu, QGroupBox, QGridLayout, QFrame,
    QSplitter, QMessageBox, QProgressBar, QSizePolicy,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QAction

from config.settings import THRESHOLDS
from src.data.fetcher import FundFetcher
from src.analysis.calculator import FundAnalyzer
from src.strategy.advisor import FundAdvisor
from src.storage.database import DataStore

# ─── 全局样式表 ───────────────────────────────────────────
STYLE = """
QMainWindow { background-color: #f0f2f5; }
QMenuBar { background-color: #1a1a2e; color: white; padding: 4px; font-size: 13px; }
QMenuBar::item:selected { background-color: #16213e; }
QMenu { background-color: #1a1a2e; color: white; border: 1px solid #0f3460; }
QMenu::item:selected { background-color: #0f3460; }
QListWidget { background-color: white; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; padding: 4px; }
QListWidget::item { padding: 10px 8px; border-bottom: 1px solid #eee; }
QListWidget::item:selected { background-color: #3498db; color: white; border-radius: 4px; }
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
QStatusBar { background-color: #1a1a2e; color: #ccc; font-size: 12px; }
QProgressBar { border: none; border-radius: 4px; background-color: #e0e0e0; height: 4px; }
QProgressBar::chunk { background-color: #3498db; border-radius: 4px; }
"""

# ─── 级别颜色映射 ─────────────────────────────────────────
LEVEL_COLORS = {
    "【买入】": ("#27ae60", "#d5f5e3"),
    "【加仓】": ("#2ecc71", "#d5f5e3"),
    "【持有】": ("#f39c12", "#fef9e7"),
    "【减仓】": ("#e74c3c", "#fadbd8"),
    "【卖出】": ("#c0392b", "#f5b7b1"),
}

# ─── 中文 matplotlib 配置 ─────────────────────────────────
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
matplotlib.rcParams["axes.unicode_minus"] = False


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


class MplCanvas(FigureCanvas):
    """Matplotlib 画布，嵌入 Qt"""
    def __init__(self):
        self.fig = Figure(figsize=(10, 4.5), dpi=100, facecolor="white")
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


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


class MainWindow(QMainWindow):
    """XFund 主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XFund")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(STYLE)

        self.fetcher = FundFetcher()
        self.analyzer = FundAnalyzer()
        self.advisor = FundAdvisor()
        self.store = DataStore()

        self.funds = self.store.load_watchlist()
        self.current_df = None
        self.current_summary = None
        self.fetch_thread = None

        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()

    # ─── 菜单栏 ──────────────────────────────────────────
    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")
        add_action = QAction("添加基金...", self)
        add_action.triggered.connect(self._add_fund)
        refresh_action = QAction("刷新数据", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh)
        export_action = QAction("导出数据...", self)
        export_action.triggered.connect(self._export)
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(add_action)
        file_menu.addAction(refresh_action)
        file_menu.addSeparator()
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("设置(&S)")
        threshold_action = QAction("告警阈值...", self)
        threshold_action.triggered.connect(self._edit_thresholds)
        settings_menu.addAction(threshold_action)

        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于 XFund", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    # ─── 主界面布局 ──────────────────────────────────────
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        hlayout = QHBoxLayout(central)
        hlayout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 左侧面板：基金列表 ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("📈 自选基金")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a1a2e; padding: 8px;")
        left_layout.addWidget(title_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索基金...")
        self.search_input.setStyleSheet("padding: 8px; border: 1px solid #ddd; border-radius: 6px; margin: 4px 8px;")
        self.search_input.textChanged.connect(self._filter_list)
        left_layout.addWidget(self.search_input)

        self.fund_list = QListWidget()
        self._populate_list()
        self.fund_list.currentRowChanged.connect(self._on_fund_selected)
        left_layout.addWidget(self.fund_list)

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        refresh_btn = QPushButton("🔄 刷新数据")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.clicked.connect(self._refresh)
        btn_layout.addWidget(refresh_btn)

        add_btn = QPushButton("＋ 添加基金")
        add_btn.clicked.connect(self._add_fund)
        btn_layout.addWidget(add_btn)

        left_layout.addLayout(btn_layout)

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

        # --- Tab 1: 净值走势 ---
        self.chart_tab = QWidget()
        chart_layout = QVBoxLayout(self.chart_tab)
        chart_layout.setContentsMargins(0, 0, 0, 0)

        self.nav_canvas = MplCanvas()
        self._draw_empty_chart(self.nav_canvas, "选择基金并刷新后显示净值走势")
        chart_layout.addWidget(self.nav_canvas)

        self.bar_canvas = MplCanvas()
        self._draw_empty_chart(self.bar_canvas, "选择基金并刷新后显示日涨跌幅")
        chart_layout.addWidget(self.bar_canvas)

        self.tabs.addTab(self.chart_tab, "📊 净值走势")

        # --- Tab 2: 综合分析 ---
        self.analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(self.analysis_tab)

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(16)
        analysis_layout.addLayout(self.metrics_grid)
        analysis_layout.addStretch()

        self.tabs.addTab(self.analysis_tab, "📋 综合分析")

        # --- Tab 3: 投资建议 ---
        self.advice_tab = QWidget()
        advice_layout = QVBoxLayout(self.advice_tab)

        self.advice_banner = QFrame()
        self.advice_banner.setMinimumHeight(120)
        self.advice_banner.setStyleSheet("border-radius: 10px; background-color: #bdc3c7;")
        banner_layout = QVBoxLayout(self.advice_banner)
        self.advice_level_label = QLabel("等待数据")
        self.advice_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_level_label.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        self.advice_desc_label = QLabel("请先选择基金并刷新")
        self.advice_desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_desc_label.setStyleSheet("font-size: 16px; color: white;")
        self.advice_score_label = QLabel("")
        self.advice_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.advice_score_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.7);")

        banner_layout.addStretch()
        banner_layout.addWidget(self.advice_level_label)
        banner_layout.addWidget(self.advice_desc_label)
        banner_layout.addWidget(self.advice_score_label)
        banner_layout.addStretch()

        advice_layout.addWidget(self.advice_banner)

        reasons_group = QGroupBox("📝 分析理由")
        reasons_layout = QVBoxLayout(reasons_group)
        self.reasons_label = QLabel("等待数据加载...")
        self.reasons_label.setStyleSheet("font-size: 13px; line-height: 1.8; color: #2c3e50;")
        self.reasons_label.setWordWrap(True)
        reasons_layout.addWidget(self.reasons_label)
        advice_layout.addWidget(reasons_group)

        disclaimer = QLabel("⚠️ 以上建议仅供参考，不构成投资建议。投资有风险，入市需谨慎。")
        disclaimer.setStyleSheet("font-size: 12px; color: #95a5a6; padding: 8px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        advice_layout.addWidget(disclaimer)

        self.tabs.addTab(self.advice_tab, "💡 投资建议")

        right_layout.addWidget(self.tabs)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 950])

        hlayout.addWidget(splitter)

    # ─── 绘制空图表（占位） ───────────────────────────────
    def _draw_empty_chart(self, canvas: MplCanvas, message: str):
        ax = canvas.ax
        ax.clear()
        ax.text(0.5, 0.5, message, transform=ax.transAxes,
                ha="center", va="center", fontsize=16, color="#bdc3c7")
        ax.set_xticks([])
        ax.set_yticks([])
        canvas.draw()

    # ─── 状态栏 ──────────────────────────────────────────
    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_time = QLabel("就绪 — 请选择基金后点击「刷新数据」")
        self.statusbar.addPermanentWidget(self.status_time)

    # ─── 基金列表操作 ────────────────────────────────────
    def _populate_list(self, filter_text: str = ""):
        self.fund_list.clear()
        for fund in self.funds:
            text = f"{fund['code']}\n{fund['name']}"
            if filter_text and filter_text.lower() not in text.lower():
                continue
            item = QListWidgetItem(text)
            item.setData(1, fund["code"])
            hint = item.sizeHint()
            hint.setHeight(hint.height() + 12)
            item.setSizeHint(hint)
            self.fund_list.addItem(item)

    def _filter_list(self, text: str):
        self._populate_list(text)

    def _on_fund_selected(self, row: int):
        """选中基金时自动加载数据"""
        if row < 0:
            return
        fund = self.funds[row]
        self._load_fund(fund["code"], fund["name"])

    def _load_fund(self, code: str, name: str):
        """加载基金数据"""
        self.fund_title.setText(f"⏳ 正在加载 {name} ({code})...")
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
            self.fund_title.setText(f"❌ {name} ({code}) — 无数据返回")
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
        self.fund_title.setText(f"{name} ({self.funds[self.fund_list.currentRow()]['code'] if self.fund_list.currentRow() >= 0 else '?'})")

        try:
            self._draw_nav_chart(df)
            self._draw_bar_chart(df)
        except Exception as e:
            pass  # 图表绘制出错，静默处理

        self._update_metrics(self.current_summary)
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
        self.nav_canvas.fig.tight_layout()
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
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=1, symbol="%"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.grid(True, axis="y", alpha=0.3, linestyle="--")
        ax.set_facecolor("#fafbfc")
        self.bar_canvas.fig.tight_layout()
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
            card.setStyleSheet("QFrame { background: white; border: 1px solid #eee; border-radius: 8px; padding: 12px; }")
            clayout = QVBoxLayout(card)
            clayout.setSpacing(4)

            val_label = QLabel(str(value))
            val_label.setObjectName("metricValue")
            val_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")
            clayout.addWidget(val_label)

            desc_label = QLabel(label)
            desc_label.setObjectName("metricLabel")
            clayout.addWidget(desc_label)

            row, col = divmod(idx, 3)
            self.metrics_grid.addWidget(card, row, col)

    # ─── 投资建议 ────────────────────────────────────────
    def _update_advice(self, summary: dict):
        level, desc, reasons = self.advisor.evaluate(summary)

        bg_color, _ = LEVEL_COLORS.get(level, ("#95a5a6", "#ecf0f1"))
        self.advice_banner.setStyleSheet(
            f"background-color: {bg_color}; border-radius: 10px; padding: 16px;"
        )
        self.advice_level_label.setText(level)
        self.advice_desc_label.setText(desc)
        self.advice_score_label.setText(f"数据日期：{summary.get('净值日期', '-')}")

        reason_text = ""
        for i, r in enumerate(reasons, 1):
            if "向好" in r or "超卖" in r or "较好" in r:
                icon = "✅"
            elif "正常" in r:
                icon = "ℹ️"
            else:
                icon = "⚠️"
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
                    name = info.get("基金全称", "") or info.get("基金简称", "")
                except Exception:
                    pass
                if not name:
                    name = f"基金{code}"  # 兜底名称

            # 去重检查
            for f in self.funds:
                if f["code"] == code:
                    QMessageBox.information(self, "提示", f"基金 {code} 已在自选列表中。")
                    return

            self.funds.append({"code": code, "name": name})
            self.store.save_watchlist(self.funds)  # 持久化到 JSON
            self.search_input.clear()
            self._populate_list()
            self.fund_list.setCurrentRow(len(self.funds) - 1)
            self.status_time.setText(f"已添加 {name} ({code})，选中后自动加载数据")

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
