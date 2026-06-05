"""
基金数据获取模块
基于 akshare 封装常用基金数据接口
"""

from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd


class FundFetcher:
    """基金数据获取器"""

    @staticmethod
    def get_fund_nav(symbol: str, start_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取基金历史净值数据

        Args:
            symbol: 基金代码，如 "161725"
            start_date: 起始日期 "YYYY-MM-DD"，默认近一年

        Returns:
            DataFrame 包含: 净值日期, 单位净值, 日增长率
        """
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")

        if df.empty:
            return df

        # akshare 返回 3 列：净值日期、单位净值、日增长率
        col_count = len(df.columns)
        if col_count == 4:
            df.columns = ["净值日期", "单位净值", "累计净值", "日增长率"]
        else:
            df.columns = ["净值日期", "单位净值", "日增长率"]

        df["净值日期"] = pd.to_datetime(df["净值日期"])
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        df["日增长率"] = pd.to_numeric(df["日增长率"], errors="coerce")

        # 过滤日期范围
        df = df[df["净值日期"] >= start_date]
        df = df.sort_values("净值日期").reset_index(drop=True)

        return df

    @staticmethod
    def get_fund_info(symbol: str) -> dict:
        """
        获取基金基本信息

        Args:
            symbol: 基金代码

        Returns:
            dict: 基金名称、类型、规模、基金经理等
        """
        try:
            df = ak.fund_individual_basic_info_xq(symbol=symbol)
            if df.empty:
                return {}
            info = dict(zip(df["item"], df["value"]))
            return info
        except Exception:
            return {}

    @staticmethod
    def get_fund_ranking() -> pd.DataFrame:
        """获取全市场基金排行"""
        return ak.fund_open_fund_rank_em(symbol="全部")

    @staticmethod
    def get_all_funds() -> pd.DataFrame:
        """获取全市场基金列表"""
        return ak.fund_name_em()
