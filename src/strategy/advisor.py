"""
科学投资建议引擎

决策模型（四步法）：
  第1步 — 获取关键数据：净值、RSI、均线、回撤、夏普
  第2步 — 计算估值偏离度：估算净值、PE分位、持仓盈亏
  第3步 — 市场形势判定：金字塔加仓 + 网格交易 + 技术指标
  第4步 — 结合持仓：输出个性化建议 + 具体金额

所有建议仅供参考，不构成投资建议。
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from config.settings import PYRAMID_TIERS, GRID_CONFIG, STOP_CONFIG, STRATEGY, THRESHOLDS


@dataclass
class Position:
    """用户持仓"""
    shares: float = 0.0         # 持有份额
    cost: float = 0.0           # 持仓成本（每份净值）
    base_amount: float = 1000.0 # 定投基准金额（元）


@dataclass
class AdviceResult:
    """建议结果"""
    level: str = ""             # 建议等级
    description: str = ""       # 建议描述
    reasons: List[str] = field(default_factory=list)

    # 金字塔
    pe_percentile: Optional[float] = None  # PE 分位
    pe_tier_label: str = ""                # 估值区间标签
    multiplier: float = 1.0                # 定投倍数
    suggested_amount: float = 0.0          # 建议投入金额

    # 网格
    grid_signal: str = ""                  # 网格信号
    grid_action_amount: float = 0.0        # 网格操作金额

    # 持仓
    position_value: float = 0.0            # 持仓市值
    profit_loss: float = 0.0               # 盈亏金额
    profit_loss_pct: float = 0.0           # 盈亏比例

    # 技术
    technical_score: int = 0               # 技术评分
    ma_signal: str = ""                    # 均线信号
    rsi_signal: str = ""                   # RSI 信号

    # 综合
    total_score: int = 0                   # 综合评分
    action: str = ""                       # 最终动作
    suggestion_text: str = ""              # 完整建议文案


class FundAdvisor:
    """科学投资建议引擎"""

    # ─── 主入口 ─────────────────────────────────────────
    @classmethod
    def evaluate(
        cls,
        summary: dict,
        position: Optional[Position] = None,
        pe_percentile: Optional[float] = None,
        fund_name: str = "",
    ) -> AdviceResult:
        """
        综合评估基金，给出科学投资建议

        Args:
            summary: FundAnalyzer.get_summary 输出
            position: 用户持仓（可选）
            pe_percentile: PE 估值分位 0-100（可选）
            fund_name: 基金名称
        """
        if position is None:
            position = Position()

        result = AdviceResult()

        # ── 第1步：技术指标评估 ──
        tech_score, tech_reasons = cls._evaluate_technical(summary)
        result.technical_score = tech_score

        # ── 第2步：估值偏离度 ──
        val_score, val_reasons = cls._evaluate_valuation(
            summary, position, pe_percentile, result
        )
        result.pe_percentile = pe_percentile

        # ── 第3步：金字塔 & 网格 ──
        grid_score, grid_reasons = cls._evaluate_grid_and_pyramid(
            summary, position, pe_percentile, result
        )

        # ── 第4步：综合决策矩阵 ──
        decision_score, decision_reasons = cls._decision_matrix(
            summary, position, pe_percentile, result
        )

        # ── 汇总 ──
        all_reasons = tech_reasons + val_reasons + grid_reasons + decision_reasons
        result.reasons = all_reasons

        total = tech_score + val_score + grid_score + decision_score
        result.total_score = total

        result.level, result.description = cls._score_to_level(total)
        result.suggestion_text = cls._generate_suggestion(result, fund_name, summary)

        return result

    # ─── 技术指标评估 ───────────────────────────────────
    @classmethod
    def _evaluate_technical(cls, s: dict) -> Tuple[int, List[str]]:
        score = 0
        reasons = []

        # RSI
        rsi = s.get("RSI(14)")
        if rsi is not None:
            if rsi < STRATEGY["rsi_oversold"]:
                score += 2
                r = f"RSI={rsi:.1f}，处于超卖区间（<{STRATEGY['rsi_oversold']}），短期反弹概率较大"
                reasons.append(r)
                rsi_flag = "超卖"
            elif rsi > STRATEGY["rsi_overbought"]:
                score -= 2
                r = f"RSI={rsi:.1f}，处于超买区间（>{STRATEGY['rsi_overbought']}），注意短期回调风险"
                reasons.append(r)
                rsi_flag = "超买"
            else:
                r = f"RSI={rsi:.1f}，处于正常区间"
                reasons.append(r)
                rsi_flag = "正常"

        # 均线交叉
        ma5 = s.get("MA5")
        ma20 = s.get("MA20")
        if ma5 is not None and ma20 is not None:
            if ma5 > ma20:
                score += 1
                r = f"MA5({ma5:.4f}) > MA20({ma20:.4f})，短期趋势向好"
                reasons.append(r)
            else:
                score -= 1
                r = f"MA5({ma5:.4f}) < MA20({ma20:.4f})，短期趋势偏弱"
                reasons.append(r)

        # 夏普比率
        sharpe = s.get("夏普比率")
        if sharpe is not None:
            if sharpe > 1.5:
                score += 1
                reasons.append(f"夏普比率 {sharpe}，风险调整收益优秀")
            elif sharpe > 0.5:
                score += 0
                reasons.append(f"夏普比率 {sharpe}，风险调整收益尚可")
            elif sharpe < 0:
                score -= 1
                reasons.append(f"夏普比率 {sharpe}，风险调整收益为负，性价比低")

        # 最大回撤
        dd = s.get("最大回撤(%)")
        if dd is not None:
            if dd > THRESHOLDS["max_drawdown_warn"]:
                reasons.append(f"最大回撤 {dd}%，已超阈值，注意风险控制")
            else:
                reasons.append(f"最大回撤 {dd}%，在可控范围")

        # 近1月收益
        ret_1m = s.get("近1月收益(%)")
        if ret_1m is not None:
            if ret_1m > 5:
                score += 1
                reasons.append(f"近1月涨幅 {ret_1m}%，短期动能强")
            elif ret_1m < -5:
                score -= 1
                reasons.append(f"近1月跌幅 {ret_1m}%，短期超跌中")

        return score, reasons

    # ─── 估值偏离度评估 ─────────────────────────────────
    @classmethod
    def _evaluate_valuation(
        cls, s: dict, pos: Position, pe_pct: Optional[float], result: AdviceResult
    ) -> Tuple[int, List[str]]:
        score = 0
        reasons = []

        # PE 分位判断
        if pe_pct is not None:
            result.pe_percentile = pe_pct
            for threshold, mult, label, desc in PYRAMID_TIERS:
                if pe_pct <= threshold:
                    result.pe_tier_label = label
                    result.multiplier = mult
                    reasons.append(f"PE分位 {pe_pct:.0f}%，处于{label}（{desc}）")
                    if mult > 1:
                        score += 3
                    elif mult == 1:
                        score += 1
                    elif mult < 0.5:
                        score -= 2
                    else:
                        score -= 1
                    break

        # 持仓盈亏
        latest_nav = s.get("最新净值", 0)
        if latest_nav > 0 and pos.cost > 0 and pos.shares > 0:
            pnl_pct = (latest_nav - pos.cost) / pos.cost
            pnl_amt = (latest_nav - pos.cost) * pos.shares
            result.position_value = latest_nav * pos.shares
            result.profit_loss = pnl_amt
            result.profit_loss_pct = pnl_pct * 100

            if pnl_pct < -0.10:
                reasons.append(f"持仓浮亏 {pnl_pct*100:.1f}%（¥{pnl_amt:+.0f}），浮亏较大")
                if pe_pct is not None and pe_pct < 30:
                    score += 2  # 低估+浮亏 → 加倍买入机会
                    reasons.append("低估区域叠加浮亏，是加仓良机")
            elif pnl_pct > 0.20:
                reasons.append(f"持仓浮盈 {pnl_pct*100:.1f}%（¥{pnl_amt:+.0f}），盈利丰厚")
                if pe_pct is not None and pe_pct > 70:
                    score -= 2  # 高估+浮盈 → 止盈信号
                    reasons.append("高估区域叠加大幅浮盈，建议考虑止盈")
            else:
                reasons.append(f"持仓{'浮盈' if pnl_pct >= 0 else '浮亏'} {pnl_pct*100:.1f}%（¥{pnl_amt:+.0f}）")

        # 无估值数据时用技术面替代
        if pe_pct is None:
            dd = s.get("最大回撤(%)", 0) or 0
            if dd > 15:
                reasons.append("虽无PE分位数据，但历史回撤较深，可能处于相对低位")
                score += 1
            monthly = s.get("近1月收益(%)", 0) or 0
            if monthly < -5:
                reasons.append("近期跌幅较大，短期可能有反弹机会")
                score += 1

        return score, reasons

    # ─── 金字塔 & 网格 ──────────────────────────────────
    @classmethod
    def _evaluate_grid_and_pyramid(
        cls, s: dict, pos: Position, pe_pct: Optional[float], result: AdviceResult
    ) -> Tuple[int, List[str]]:
        score = 0
        reasons = []

        latest_nav = s.get("最新净值", 0) or 0

        # 金字塔金额计算
        if pos.shares > 0 and pos.base_amount > 0:
            amount = pos.base_amount * result.multiplier
            result.suggested_amount = round(amount, 2)
            if result.multiplier > 1:
                reasons.append(
                    f"金字塔策略：定投倍率 {result.multiplier}x → 建议投入 ¥{amount:.0f}"
                    f"（基准 ¥{pos.base_amount:.0f} × {result.multiplier}）"
                )
            elif result.multiplier == 0:
                reasons.append(
                    f"金字塔策略：处于高估区域，暂停买入。可将原定投金额 ¥{pos.base_amount:.0f}"
                    f" 转入货币基金等待机会"
                )
            else:
                reasons.append(
                    f"金字塔策略：定投倍率 {result.multiplier}x → 建议投入 ¥{amount:.0f}"
                )

        # 网格交易
        if pos.cost > 0 and pos.shares > 0 and latest_nav > 0:
            deviation = (latest_nav - pos.cost) / pos.cost
            grid_step = GRID_CONFIG["grid_step"]
            grids = int(abs(deviation) / grid_step)

            if grids >= 1:
                if deviation < 0:
                    # 跌破成本 → 买入网格
                    buy_pct = min(grids * GRID_CONFIG["buy_amount"], 1.0)
                    grid_amt = pos.base_amount * buy_pct if pos.base_amount else result.position_value * buy_pct
                    result.grid_signal = "买入"
                    result.grid_action_amount = round(grid_amt, 2)
                    reasons.append(
                        f"网格策略：净值低于成本 {abs(deviation)*100:.1f}%"
                        f"（触发 {grids} 格）→ 建议买入 ¥{grid_amt:.0f}"
                    )
                    score += min(grids, 2)
                else:
                    # 涨超成本 → 卖出网格
                    sell_pct = min(grids * GRID_CONFIG["sell_amount"], 1.0)
                    grid_amt = result.position_value * sell_pct
                    result.grid_signal = "卖出"
                    result.grid_action_amount = round(grid_amt, 2)
                    reasons.append(
                        f"网格策略：净值高于成本 {deviation*100:.1f}%"
                        f"（触发 {grids} 格）→ 建议卖出 ¥{grid_amt:.0f}"
                    )
                    score -= min(grids, 2)
            else:
                result.grid_signal = "持有"
                reasons.append(f"网格策略：偏离成本 {deviation*100:.2f}%，未触发网格（步长{grid_step*100:.0f}%）")

        # 止盈止损
        if pos.cost > 0 and latest_nav > 0:
            pnl = (latest_nav - pos.cost) / pos.cost
            if pnl > STOP_CONFIG["take_profit"]:
                reasons.append(
                    f"止盈提醒：浮盈 {pnl*100:.1f}% 已超过止盈线 {STOP_CONFIG['take_profit']*100:.0f}%"
                    f"，强烈建议分批止盈"
                )
                score -= 3
            elif pnl < STOP_CONFIG["stop_loss"]:
                reasons.append(
                    f"止损提醒：浮亏 {pnl*100:.1f}% 已触及止损线 {STOP_CONFIG['stop_loss']*100:.0f}%"
                    f"，请审视是否继续持有"
                )
                score -= 2

        return score, reasons

    # ─── 决策矩阵 ───────────────────────────────────────
    @classmethod
    def _decision_matrix(
        cls, s: dict, pos: Position, pe_pct: Optional[float], result: AdviceResult
    ) -> Tuple[int, List[str]]:
        score = 0
        reasons = []

        # 日涨跌幅异常
        daily = s.get("最新日涨跌幅(%)", 0) or 0
        if abs(daily) > THRESHOLDS["daily_change_warn"]:
            direction = "大涨" if daily > 0 else "大跌"
            reasons.append(f"今日{direction} {daily:+.2f}%，超过阈值 {THRESHOLDS['daily_change_warn']}%")
            if daily < -3 and pe_pct is not None and pe_pct < 30:
                reasons.append("低估区单日大跌 → 可能是难得的加仓窗口")
                score += 1
            elif daily > 3 and pe_pct is not None and pe_pct > 70:
                reasons.append("高估区单日大涨 → 可考虑趁机减仓")
                score -= 1

        # 3点前提醒
        reasons.append("💡 交易日15:00前操作按当日净值成交，请在此前完成决策")
        reasons.append("⚠️ 盘中估算净值与实际净值存在偏差，请以基金公司公布为准")

        return score, reasons

    # ─── 评分转等级 ─────────────────────────────────────
    @classmethod
    def _score_to_level(cls, score: int) -> Tuple[str, str]:
        if score >= 5:
            return "【积极买入】", "市场低估 + 技术向好 + 估值合理，是难得的重仓机会"
        elif score >= 2:
            return "【建议加仓】", "多项指标偏乐观，可按金字塔倍率适度加仓"
        elif score >= -1:
            return "【持有观望】", "信号中性，保持当前仓位，等待更明确信号"
        elif score >= -4:
            return "【适度减仓】", "指标偏弱，建议按网格策略减仓或暂停买入"
        else:
            return "【果断离场】", "高估 + 趋势恶化，建议大幅减仓或清仓"

    # ─── 生成建议文案 ───────────────────────────────────
    @classmethod
    def _generate_suggestion(
        cls, result: AdviceResult, fund_name: str, summary: dict
    ) -> str:
        latest_nav = summary.get("最新净值", "-")
        latest_date = summary.get("净值日期", "-")

        lines = []
        lines.append(f"【{fund_name}】投资分析报告")
        lines.append(f"数据日期：{latest_date}  |  最新净值：{latest_nav}")
        lines.append("")

        # 估值
        if result.pe_percentile is not None:
            lines.append(f"📊 估值水平：PE分位 {result.pe_percentile:.0f}% → {result.pe_tier_label}")
        else:
            lines.append(f"📊 估值水平：暂无PE分位数据")

        # 持仓
        if result.position_value > 0:
            color = "🔴" if result.profit_loss < 0 else "🟢"
            lines.append(f"💰 持仓市值：¥{result.position_value:,.0f}  |  {color} 盈亏：¥{result.profit_loss:+,.0f}（{result.profit_loss_pct:+.1f}%）")

        # 建议动作
        lines.append(f"")
        lines.append(f"🎯 综合建议：{result.level}")
        lines.append(f"   {result.description}")

        # 具体操作
        if result.suggested_amount > 0 and result.multiplier > 0:
            lines.append(f"")
            lines.append(f"📥 定投建议：本期投入 ¥{result.suggested_amount:,.0f}（{result.multiplier}x 基准）")
        elif result.multiplier == 0:
            lines.append(f"")
            lines.append(f"⏸️ 定投建议：暂停买入，资金转货币基金等待机会")

        if result.grid_action_amount > 0:
            action_word = "买入" if result.grid_signal == "买入" else "卖出"
            lines.append(f"📐 网格{action_word}：¥{result.grid_action_amount:,.0f}（偏离成本触发）")

        # 理由
        lines.append(f"")
        lines.append(f"📝 分析依据：")
        for i, r in enumerate(result.reasons, 1):
            lines.append(f"   {i}. {r}")

        lines.append(f"")
        lines.append(f"⚠️ 免责声明：以上分析基于历史数据和公开信息估算，盘中估算净值与实际净值存在偏差，不构成确定性投资建议。投资有风险，入市需谨慎。")

        return "\n".join(lines)
