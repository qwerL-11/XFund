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

    _fund_list_cache = None  # 全量基金列表缓存

    @classmethod
    def _get_fund_list(cls) -> pd.DataFrame:
        """获取全量基金列表（带缓存）"""
        if cls._fund_list_cache is None:
            cls._fund_list_cache = ak.fund_name_em()
        return cls._fund_list_cache

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

    @classmethod
    def get_fund_info(cls, symbol: str) -> dict:
        """获取基金简称（含 A/C）"""
        try:
            df = cls._get_fund_list()
            cols = list(df.columns)
            match = df[df[cols[0]].astype(str) == symbol]
            if match.empty:
                return {}
            row = match.iloc[0]
            return {
                "基金代码": str(row[cols[0]]),
                "基金简称": str(row[cols[2]]) if len(cols) > 2 else str(row[cols[0]]),
                "基金类型": str(row[cols[3]]) if len(cols) > 3 else "",
            }
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

    @staticmethod
    def get_fund_holdings(symbol: str, year: str = "2025") -> dict:
        """
        获取基金前十大重仓股及占比

        Returns:
            {"stocks": [{"code": "600519", "name": "贵州茅台", "weight": 9.5}, ...],
             "total_weight": 65.2}
        """
        try:
            df = ak.fund_portfolio_hold_em(symbol=symbol, date=year)
            if df.empty:
                return {"stocks": [], "total_weight": 0}

            # 列名可能是中文，取前10行
            cols = list(df.columns)
            code_col = next((c for c in cols if "代码" in str(c)), cols[0])
            name_col = next((c for c in cols if "名称" in str(c)), cols[1]) if len(cols) > 1 else cols[1]
            weight_col = next((c for c in cols if "占净" in str(c) or "比例" in str(c)), cols[-1])

            stocks = []
            total = 0
            for _, row in df.head(10).iterrows():
                try:
                    code = str(row[code_col]).strip().zfill(6)
                    name = str(row[name_col]).strip()
                    weight = float(row[weight_col])
                    stocks.append({"code": code, "name": name, "weight": weight})
                    total += weight
                except (ValueError, KeyError):
                    continue

            return {"stocks": stocks, "total_weight": round(total, 1)}
        except Exception:
            return {"stocks": [], "total_weight": 0}

    @staticmethod
    def get_stock_daily_change(stock_codes: list) -> dict:
        """
        批量获取股票当日涨跌幅

        Returns:
            {"600519": 2.35, "000858": -1.20, ...}
        """
        result = {}
        if not stock_codes:
            return result
        try:
            df = ak.stock_zh_a_spot_em()
            if df.empty:
                return result
            code_col = df.columns[1]  # 代码列
            change_col = df.columns[df.columns.get_loc("涨跌幅")] if "涨跌幅" in df.columns else None
            if change_col is None:
                for c in df.columns:
                    if "涨跌" in str(c):
                        change_col = c
                        break
            if change_col is None:
                return result

            df[code_col] = df[code_col].astype(str).str.strip()
            for code in stock_codes:
                match = df[df[code_col] == code]
                if not match.empty:
                    try:
                        result[code] = float(match.iloc[0][change_col])
                    except (ValueError, TypeError):
                        result[code] = 0
        except Exception:
            pass
        return result

    @staticmethod
    def get_sector_performance() -> dict:
        """
        获取各行业板块当日涨跌幅

        Returns:
            {"白酒": 1.35, "半导体": -0.80, ...}
        """
        result = {}
        try:
            df = ak.stock_board_industry_name_em()
            if df.empty:
                return result
            name_col = df.columns[0] if "名称" in str(df.columns[0]) else df.columns[1]
            change_col = None
            for c in df.columns:
                if "涨跌幅" in str(c):
                    change_col = c
                    break
            if change_col is None:
                for c in df.columns:
                    if "涨跌" in str(c):
                        change_col = c
                        break
            if change_col is None:
                return result

            for _, row in df.iterrows():
                try:
                    name = str(row[name_col]).strip()
                    change = float(row[change_col])
                    result[name] = change
                except (ValueError, KeyError):
                    continue
        except Exception:
            pass
        return result

    @staticmethod
    def guess_fund_sector(fund_name: str) -> str:
        """根据基金名称推测关联板块"""
        keywords = {
            "白酒": "白酒", "酒": "酿酒行业",
            "医疗": "医疗器械", "医药": "医药制造", "健康": "医疗行业",
            "科技": "半导体", "半导体": "半导体", "芯片": "半导体",
            "新能源": "新能源", "光伏": "光伏设备", "锂电": "电池",
            "消费": "商业百货", "食品": "食品饮料", "饮料": "食品饮料",
            "军工": "航天航空", "国防": "航天航空",
            "证券": "证券", "券商": "证券",
            "银行": "银行",
            "保险": "保险",
            "地产": "房地产", "房地产": "房地产",
            "汽车": "汽车整车", "新能源车": "汽车整车",
            "互联网": "互联网服务", "计算机": "互联网服务",
            "传媒": "文化传媒", "影视": "文化传媒",
            "农业": "农牧饲渔", "养殖": "农牧饲渔",
            "黄金": "贵金属", "有色": "有色金属", "钢铁": "钢铁行业",
            "煤炭": "煤炭行业", "石油": "石油行业",
            "电力": "电力行业", "基建": "工程建设",
            "环保": "环保行业", "碳中和": "环保行业",
            "物流": "物流行业", "旅游": "旅游酒店",
            "通信": "通信设备", "5G": "通信设备",
            "人工智能": "互联网服务", "AI": "互联网服务",
            "机器人": "专用设备",
        }
        for kw, sector in keywords.items():
            if kw in fund_name:
                return sector
        return ""
