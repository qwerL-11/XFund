"""对话框组件"""

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QHBoxLayout, QLabel, QRadioButton, QButtonGroup, QMessageBox,
)


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
        self.radio_daily.setChecked(True)
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

        hint = QLabel("只需填写代码即可添加，名称会自动获取")
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
