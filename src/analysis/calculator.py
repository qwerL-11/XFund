"""
基金分析计算模块
计算各类技术指标：涨跌幅、最大回撤、均线、RSI 等
"""

from typing import Tuple

import numpy as np
import pandas as pd


class FundAnalyzer:
    """基金分析计算器"""

    @staticmethod
    def calc_returns(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算各周期收益率

        Args:
            df: 包含 净值日期、单位净值、日增长率 的 DataFrame

        Returns:
            添加了各周期收益率列的 DataFrame
        """
        df = df.copy()
        df = df.sort_values("净值日期")

        latest_nav = df["单位净值"].iloc[-1]

        # 各周期收益率
        for period_name, days in [
            ("近1周", 5),
            ("近1月", 21),
            ("近3月", 63),
            ("近6月", 126),
            ("近1年", 252),
        ]:
            if len(df) >= days:
                past_nav = df["单位净值"].iloc[-(days + 1)]
                df.attrs[f"return_{period_name}"] = round((latest_nav - past_nav) / past_nav * 100, 2)
            else:
                df.attrs[f"return_{period_name}"] = None

        return df

    @staticmethod
    def calc_max_drawdown(df: pd.DataFrame) -> Tuple[float, str, str]:
        """
        计算最大回撤

        Args:
            df: 包含 单位净值、净值日期 的 DataFrame

        Returns:
            (最大回撤百分比, 回撤起始日期, 回撤最低日期)
        """
        df = df.sort_values("净值日期")
        nav = df["单位净值"].values
        dates = df["净值日期"].values

        peak = nav[0]
        max_dd = 0.0
        peak_idx = 0
        trough_idx = 0
        start_idx = 0

        for i, value in enumerate(nav):
            if value > peak:
                peak = value
                peak_idx = i
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd
                start_idx = peak_idx
                trough_idx = i

        return (
            round(max_dd, 2),
            str(dates[start_idx])[:10],
            str(dates[trough_idx])[:10],
        )

    @staticmethod
    def calc_ma(df: pd.DataFrame, window: int) -> pd.Series:
        """计算移动均线"""
        return df["单位净值"].rolling(window=window).mean()

    @staticmethod
    def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算 RSI 指标

        Args:
            df: 包含 日增长率 的 DataFrame
            period: RSI 周期，默认 14 天

        Returns:
            RSI 值序列
        """
        delta = df["日增长率"].astype(float)
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        # 使用 Wilder's smoothing
        for i in range(period, len(avg_gain)):
            avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calc_volatility(df: pd.DataFrame, window: int = 21) -> pd.Series:
        """计算滚动波动率（年化）"""
        daily_returns = df["日增长率"] / 100
        rolling_std = daily_returns.rolling(window=window).std()
        annualized_vol = rolling_std * np.sqrt(252) * 100
        return annualized_vol

    @staticmethod
    def calc_sharpe_ratio(df: pd.DataFrame, risk_free: float = 2.5) -> float:
        """
        计算夏普比率（年化）

        Args:
            df: 包含 日增长率 的 DataFrame
            risk_free: 无风险利率（%）

        Returns:
            年化夏普比率
        """
        daily_returns = df["日增长率"] / 100
        excess = daily_returns.mean() * 252 - risk_free / 100
        volatility = daily_returns.std() * np.sqrt(252)
        if volatility == 0:
            return 0
        return round(excess / volatility, 2)

    @staticmethod
    def get_summary(df: pd.DataFrame, fund_name: str = "") -> dict:
        """
        生成基金综合分析摘要

        Args:
            df: 净值数据 DataFrame
            fund_name: 基金名称

        Returns:
            分析摘要字典
        """
        if df.empty:
            return {}

        df = FundAnalyzer.calc_returns(df)
        max_dd, dd_start, dd_trough = FundAnalyzer.calc_max_drawdown(df)
        sharpe = FundAnalyzer.calc_sharpe_ratio(df)
        rsi = FundAnalyzer.calc_rsi(df)
        ma5 = FundAnalyzer.calc_ma(df, 5)
        ma20 = FundAnalyzer.calc_ma(df, 20)

        latest_nav = df["单位净值"].iloc[-1]
        latest_date = df["净值日期"].iloc[-1]

        return {
            "基金名称": fund_name,
            "基金代码": fund_name,
            "最新净值": round(latest_nav, 4),
            "净值日期": str(latest_date)[:10],
            "最新日涨跌幅(%)": round(df["日增长率"].iloc[-1], 2),
            "近1周收益(%)": df.attrs.get("return_近1周"),
            "近1月收益(%)": df.attrs.get("return_近1月"),
            "近3月收益(%)": df.attrs.get("return_近3月"),
            "近6月收益(%)": df.attrs.get("return_近6月"),
            "近1年收益(%)": df.attrs.get("return_近1年"),
            "最大回撤(%)": max_dd,
            "回撤起始日": dd_start,
            "回撤最低日": dd_trough,
            "夏普比率": sharpe,
            "RSI(14)": round(rsi.iloc[-1], 2) if not rsi.empty else None,
            "MA5": round(ma5.iloc[-1], 4) if not ma5.empty else None,
            "MA20": round(ma20.iloc[-1], 4) if not ma20.empty else None,
        }
