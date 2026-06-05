"""
数据存储模块
将基金净值数据持久化到本地 CSV 文件，自选列表持久化到 JSON
"""

import json
from pathlib import Path

import pandas as pd

from config.settings import DATA_DIR


class DataStore:
    """本地数据存储（CSV + JSON）"""

    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        return self.data_dir / f"{symbol}.csv"

    def save(self, symbol: str, df: pd.DataFrame) -> None:
        """保存基金净值数据到 CSV"""
        path = self._path(symbol)
        df.to_csv(path, index=False, encoding="utf-8")

    def load(self, symbol: str) -> pd.DataFrame:
        """从 CSV 加载基金净值数据"""
        path = self._path(symbol)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, parse_dates=["净值日期"])

    def exists(self, symbol: str) -> bool:
        """检查是否有本地缓存"""
        return self._path(symbol).exists()

    def save_watchlist(self, funds: list) -> None:
        """持久化自选基金列表"""
        path = self.data_dir / "watchlist.json"
        path.write_text(json.dumps(funds, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_watchlist(self) -> list:
        """加载自选基金列表"""
        path = self.data_dir / "watchlist.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def save_position(self, code: str, pos: dict) -> None:
        """保存持仓数据"""
        path = self.data_dir / "positions.json"
        all_pos = self.load_all_positions()
        all_pos[code] = pos
        path.write_text(json.dumps(all_pos, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_position(self, code: str) -> dict:
        """加载单只基金持仓"""
        return self.load_all_positions().get(code, {})

    def load_all_positions(self) -> dict:
        """加载全部持仓"""
        path = self.data_dir / "positions.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
