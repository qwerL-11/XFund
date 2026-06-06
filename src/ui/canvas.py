"""Matplotlib 画布组件"""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtCore import QTimer


class MplCanvas(FigureCanvas):
    """Matplotlib 画布，嵌入 Qt（高性能优化）"""
    def __init__(self, figsize=(10, 4.5)):
        self.fig = Figure(figsize=figsize, dpi=72, facecolor="white")
        self.fig.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.15)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(200)
        self.setStyleSheet("background: white;")

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
