"""
全局配置文件
"""

# ===== 自选基金列表 =====
WATCHLIST = []  # 自选基金列表，通过 GUI 添加

# ===== 数据存储路径 =====
DATA_DIR = "data"

# ===== 告警阈值 =====
THRESHOLDS = {
    "daily_change_warn": 3.0,       # 日涨跌幅超过 ±3% 告警
    "max_drawdown_warn": 15.0,      # 最大回撤超过 15% 警告
    "consecutive_drop_days": 3,     # 连续下跌天数告警
}

# ===== 建议策略参数 =====
STRATEGY = {
    "ma_short": 5,                  # 短期均线天数
    "ma_long": 20,                  # 长期均线天数
    "rsi_oversold": 30,             # RSI 超卖阈值
    "rsi_overbought": 70,           # RSI 超买阈值
}
