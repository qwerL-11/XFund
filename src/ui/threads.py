"""后台线程"""

from PySide6.QtCore import QThread, Signal
from src.data.fetcher import FundFetcher


class FetchThread(QThread):
    """后台线程：异步获取基金数据，避免界面卡顿"""
    finished = Signal(str, object)
    error = Signal(str, str)

    def __init__(self, fund_code: str):
        super().__init__()
        self.fund_code = fund_code

    def run(self):
        try:
            fetcher = FundFetcher()
            df = fetcher.get_fund_nav(self.fund_code)
            self.finished.emit(self.fund_code, df)
        except Exception as e:
            self.error.emit(self.fund_code, str(e))


class SummaryFetchThread(QThread):
    """后台线程：异步加载账户汇总所需的板块、重仓股数据"""
    finished = Signal(dict, dict, dict)  # (sector_map, fund_holdings_map, stock_changes)

    def __init__(self, funds: list):
        super().__init__()
        self.funds = funds

    def run(self):
        fetcher = FundFetcher()
        try:
            sector_map = fetcher.get_sector_performance()
        except Exception:
            sector_map = {}
        try:
            all_stock_codes = set()
            fund_holdings_map = {}
            for fund in self.funds:
                try:
                    holdings = fetcher.get_fund_holdings(fund["code"])
                    fund_holdings_map[fund["code"]] = holdings
                    for s in holdings.get("stocks", []):
                        all_stock_codes.add(s["code"])
                except Exception:
                    fund_holdings_map[fund["code"]] = {"stocks": [], "total_weight": 0}
            stock_changes = fetcher.get_stock_daily_change(list(all_stock_codes)) if all_stock_codes else {}
        except Exception:
            fund_holdings_map = {}
            stock_changes = {}
        self.finished.emit(sector_map, fund_holdings_map, stock_changes)
