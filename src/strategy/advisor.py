"""
投资建议生成模块
基于技术指标与阈值规则，生成投资建议
"""

from typing import List, Tuple

from config.settings import STRATEGY, THRESHOLDS


class FundAdvisor:
    """基金投资建议引擎"""

    LEVEL_BUY = "【买入】"
    LEVEL_ADD = "【加仓】"
    LEVEL_HOLD = "【持有】"
    LEVEL_REDUCE = "【减仓】"
    LEVEL_SELL = "【卖出】"

    @classmethod
    def evaluate(cls, summary: dict) -> Tuple[str, str, List[str]]:
        """
        综合评估基金，给出操作建议

        Args:
            summary: FundAnalyzer.get_summary 的输出

        Returns:
            (建议等级, 建议描述, 分析理由列表)
        """
        score = 0
        reasons = []

        # 1. RSI 评估
        rsi = summary.get("RSI(14)")
        if rsi is not None:
            if rsi < STRATEGY["rsi_oversold"]:
                score += 2
                reasons.append(f"RSI={rsi:.1f}，处于超卖区间，短期反弹概率较大")
            elif rsi > STRATEGY["rsi_overbought"]:
                score -= 2
                reasons.append(f"RSI={rsi:.1f}，处于超买区间，注意短期回调风险")
            else:
                reasons.append(f"RSI={rsi:.1f}，处于正常区间")

        # 2. 均线评估
        ma5 = summary.get("MA5")
        ma20 = summary.get("MA20")
        if ma5 is not None and ma20 is not None:
            if ma5 > ma20:
                score += 1
                reasons.append("MA5 在 MA20 上方，短期趋势向好")
            else:
                score -= 1
                reasons.append("MA5 在 MA20 下方，短期趋势偏弱")

        # 3. 近期收益评估
        ret_1m = summary.get("近1月收益(%)")
        ret_3m = summary.get("近3月收益(%)")
        if ret_1m is not None:
            if ret_1m > 5:
                score += 1
                reasons.append(f"近1月收益 {ret_1m}%，表现强劲")
            elif ret_1m < -5:
                score -= 1
                reasons.append(f"近1月收益 {ret_1m}%，短期跌幅较大")
        if ret_3m is not None:
            if ret_3m > 10:
                score += 1
            elif ret_3m < -10:
                score -= 1

        # 4. 最大回撤评估
        max_dd = summary.get("最大回撤(%)")
        if max_dd is not None and max_dd > THRESHOLDS["max_drawdown_warn"]:
            score -= 1
            reasons.append(f"最大回撤 {max_dd}%，超过阈值 {THRESHOLDS['max_drawdown_warn']}%")

        # 5. 日涨跌幅异常检测
        daily_change = summary.get("最新日涨跌幅(%)")
        if daily_change is not None:
            if abs(daily_change) > THRESHOLDS["daily_change_warn"]:
                reasons.append(f"当日涨跌幅 {daily_change}%，异常波动")

        # 6. 夏普比率评估
        sharpe = summary.get("夏普比率")
        if sharpe is not None:
            if sharpe > 1:
                score += 1
                reasons.append(f"夏普比率 {sharpe}，风险调整收益较好")
            elif sharpe < 0:
                score -= 1
                reasons.append(f"夏普比率 {sharpe}，风险调整收益为负")

        # 综合评分 → 操作建议
        if score >= 4:
            level, desc = cls.LEVEL_BUY, "多项指标向好，建议买入或加仓"
        elif score >= 2:
            level, desc = cls.LEVEL_ADD, "趋势偏乐观，可适度加仓"
        elif score >= -1:
            level, desc = cls.LEVEL_HOLD, "信号中性，建议持有观望"
        elif score >= -3:
            level, desc = cls.LEVEL_REDUCE, "多项指标偏弱，建议适度减仓"
        else:
            level, desc = cls.LEVEL_SELL, "趋势恶化，建议卖出或大幅减仓"

        return level, desc, reasons
