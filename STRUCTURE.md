# XFund 项目结构说明

```
XFund/                                  # 项目根目录
├── src/                                # 源代码主目录
│   ├── __init__.py                     # 包初始化
│   ├── main.py                         # CLI 入口，支持三种运行模式
│   │
│   ├── data/                           # ===== 数据获取层 =====
│   │   ├── __init__.py                 # 导出 FundFetcher
│   │   └── fetcher.py                  # 基金数据获取器
│   │       · FundFetcher.get_fund_nav()      → 获取基金历史净值（日级别）
│   │       · FundFetcher.get_fund_info()     → 获取基金基本信息
│   │       · FundFetcher.get_fund_ranking()  → 获取全市场基金排行
│   │       · FundFetcher.get_all_funds()     → 获取全部基金列表
│   │       数据源：天天基金 / 东方财富（通过 akshare）
│   │
│   ├── analysis/                       # ===== 数据分析层 =====
│   │   ├── __init__.py                 # 导出 FundAnalyzer
│   │   └── calculator.py              # 基金指标计算器
│   │       · calc_returns()            → 计算各周期收益率（1周/1月/3月/6月/1年）
│   │       · calc_max_drawdown()       → 计算最大回撤及起止日期
│   │       · calc_ma(window)           → 计算移动均线（MA5/MA20）
│   │       · calc_rsi(period=14)       → 计算 RSI 指标
│   │       · calc_volatility(window=21)→ 计算滚动年化波动率
│   │       · calc_sharpe_ratio()       → 计算年化夏普比率
│   │       · get_summary()             → 生成综合分析摘要字典
│   │
│   ├── strategy/                       # ===== 策略建议层 =====
│   │   ├── __init__.py                 # 导出 FundAdvisor
│   │   └── advisor.py                 # 投资建议引擎
│   │       · evaluate(summary)         → 综合评估并给出建议
│   │       评分维度：RSI、均线交叉、近期收益、最大回撤、夏普比率
│   │       建议等级：
│   │         【买入】 score ≥ 4  → 多项指标向好
│   │         【加仓】 score ≥ 2  → 趋势偏乐观
│   │         【持有】 score ≥ -1 → 信号中性
│   │         【减仓】 score ≥ -3 → 多项指标偏弱
│   │         【卖出】 score < -3 → 趋势恶化
│   │
│   ├── storage/                        # ===== 数据存储层 =====
│   │   ├── __init__.py                 # 导出 DataStore
│   │   └── database.py                # 本地数据持久化
│   │       · DataStore.save(symbol, df)→ 保存净值数据到 CSV
│   │       · DataStore.load(symbol)    → 从 CSV 加载数据
│   │       · DataStore.exists(symbol)  → 检查本地缓存是否存在
│   │       存储格式：data/{基金代码}.csv
│   │
│   ├── scheduler/                      # ===== 定时调度层 =====
│   │   ├── __init__.py                 # 导出 JobScheduler
│   │   └── jobs.py                    # 定时任务
│   │       · update_all_funds()        → 更新所有自选基金 + 告警检查
│   │       · run_daily(hour, minute)   → 每日定时执行（默认 15:30 收盘后）
│   │       告警：日涨跌幅超阈值、最大回撤超阈值
│   │
│   └── ui/                            # ===== 前端展示层 =====
│       ├── __init__.py
│       └── app.py                     # Streamlit Web 界面
│           Tab 1 📊 净值走势  → Plotly 交互折线图 + 涨跌柱状图
│           Tab 2 📋 基金分析  → 关键指标卡片展示
│           Tab 3 💡 投资建议  → 操作建议 + 分析理由
│
├── config/                            # 配置文件目录
│   ├── __init__.py
│   └── settings.py                    # 全局配置
│       · WATCHLIST          → 自选基金列表 [{code, name}, ...]
│       · DATA_DIR           → 本地数据存储路径
│       · THRESHOLDS         → 告警阈值（涨跌幅、回撤、连跌天数）
│       · STRATEGY           → 策略参数（MA周期、RSI超买超卖线）
│
├── data/                              # 本地数据缓存目录
│   └── .gitkeep                       # 占位文件，实际数据 .gitignore 忽略
│       数据文件示例：161725.csv、005827.csv
│
├── tests/                             # 单元测试目录
│   └── __init__.py
│
├── notebooks/                         # Jupyter Notebook 探索目录
│   └── .gitkeep
│
├── logs/                              # 日志文件目录
│   └── .gitkeep
│
├── XFund_venv/                        # Python 虚拟环境（Git 忽略）
│   ├── Scripts/activate.ps1           # PowerShell 激活
│   ├── Scripts/activate.bat           # CMD 激活
│   └── ...
│
├── requirements.txt                   # Python 依赖清单
├── .gitignore                         # Git 忽略规则
└── STRUCTURE.md                       # ← 本文件：项目结构说明
```

---

## 架构分层

```
┌─────────────────────────────────────────────────────┐
│                    展示层 (ui/)                       │
│              Streamlit Web + Plotly 图表              │
├─────────────────────────────────────────────────────┤
│   策略层 (strategy/)    │    调度层 (scheduler/)      │
│   投资建议引擎           │    定时任务 + 告警          │
├─────────────────────────────────────────────────────┤
│                    分析层 (analysis/)                 │
│    收益率 · 回撤 · RSI · 均线 · 夏普比率 · 波动率     │
├─────────────────────────────────────────────────────┤
│      数据层 (data/)     │      存储层 (storage/)      │
│      akshare 数据获取    │      CSV 本地缓存           │
├─────────────────────────────────────────────────────┤
│                    外部数据源                         │
│       天天基金 · 东方财富 · 新浪财经                    │
└─────────────────────────────────────────────────────┘
```

## 数据流

```
自选基金代码 (config/settings.py)
    │
    ▼
FundFetcher.get_fund_nav()      ← 从天天基金获取净值
    │
    ▼
DataStore.save()                ← 缓存到本地 CSV
    │
    ▼
FundAnalyzer.get_summary()      ← 计算各项指标
    │
    ▼
FundAdvisor.evaluate()          ← 综合评分 → 操作建议
    │
    ▼
展示：CLI 打印 / Web 界面 / 日志告警
```

## 运行方式

| 命令 | 说明 |
|------|------|
| `python -m src.main` | CLI 模式：查看所有自选基金分析 |
| `python -m src.main serve` | Web 模式：启动 Streamlit 界面 |
| `python -m src.main scheduler` | 调度模式：每日定时更新+告警 |

## 核心依赖

| 库 | 用途 |
|----|------|
| `akshare` | 基金数据获取（天天基金/东方财富） |
| `pandas` | 数据处理与计算 |
| `numpy` | 数值计算 |
| `plotly` | 交互式图表 |
| `streamlit` | Web 界面框架 |
| `schedule` | 定时任务调度 |
| `loguru` | 日志管理 |
| `sqlalchemy` | 数据库 ORM（可选） |
