"""
定时任务调度模块
用于定时更新基金数据并检查告警
"""

import time

import schedule
from loguru import logger

from config.settings import WATCHLIST, THRESHOLDS
from src.analysis.calculator import FundAnalyzer
from src.data.fetcher import FundFetcher
from src.storage.database import DataStore
from src.strategy.advisor import FundAdvisor


class JobScheduler:
    """定时任务调度器"""

    def __init__(self):
        self.fetcher = FundFetcher()
        self.store = DataStore()
        self.analyzer = FundAnalyzer()
        self.advisor = FundAdvisor()

    def update_all_funds(self) -> None:
        """更新所有自选基金数据"""
        logger.info("=" * 40)
        logger.info("开始更新自选基金数据...")

        for fund in WATCHLIST:
            try:
                df = self.fetcher.get_fund_nav(fund["code"])
                if not df.empty:
                    self.store.save(fund["code"], df)

                    # 生成分析摘要
                    summary = self.analyzer.get_summary(df, fund["name"])
                    level, desc, reasons = self.advisor.evaluate(summary)

                    logger.info(f"{fund['name']}({fund['code']}) — {level} {desc}")

                    # 日涨跌幅告警
                    daily = summary.get("最新日涨跌幅(%)", 0)
                    if abs(daily) >= THRESHOLDS["daily_change_warn"]:
                        logger.warning(
                            f"⚠ {fund['name']} 日涨跌幅 {daily}%，触发告警"
                        )

            except Exception as e:
                logger.error(f"更新 {fund['name']}({fund['code']}) 失败: {e}")

        logger.info("更新完毕！")

    def run_daily(self, hour: int = 15, minute: int = 30) -> None:
        """
        每天定时运行

        Args:
            hour: 小时 (24h制)
            minute: 分钟
        """
        logger.info(f"定时任务已设置：每天 {hour:02d}:{minute:02d}")

        schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(
            self.update_all_funds
        )

        while True:
            schedule.run_pending()
            time.sleep(60)
