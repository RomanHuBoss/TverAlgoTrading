from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict
import pandas as pd

from .config import get_settings
from .utils import iso_from_ms

@dataclass
class CacheKey:
    symbol: str
    interval: str  # Bybit API token

class CandleCache:
    """Файловый кэш (CSV) по ключу (symbol, interval).
    Структура CSV: timestamp_ms,start_time_iso,open,high,low,close,volume,turnover
    Время хранится в мс (UTC). Файл отсортирован по времени по возрастанию. Дубликаты удаляются по ключу timestamp_ms.
    """
    def __init__(self):
        self.settings = get_settings()

    def _path(self, key: CacheKey) -> Path:
        # Храним по дереву: cache/<SYMBOL>/<interval>/candles.csv
        d = (self.settings.cache_dir / key.symbol.upper() / key.interval)
        d.mkdir(parents=True, exist_ok=True)
        return (d / 'candles.csv').resolve()

    def load(self, key: CacheKey) -> Optional[pd.DataFrame]:
        p = self._path(key)
        if not p.exists():
            return None
        df = pd.read_csv(p)
        if 'timestamp_ms' not in df.columns:
            return None
        df = df.drop_duplicates(subset=['timestamp_ms']).sort_values('timestamp_ms', ascending=True).reset_index(drop=True)
        return df

    def save(self, key: CacheKey, df: pd.DataFrame) -> Path:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
        return p

    def merge_and_save(self, key: CacheKey, bars: List[List[str]]) -> pd.DataFrame:
        if not bars:
            existing = self.load(key)
            return existing if existing is not None else pd.DataFrame(columns=['timestamp_ms','start_time_iso','open','high','low','close','volume','turnover'])
        df_new = self._bars_to_df(bars)
        df_existing = self.load(key)
        if df_existing is None or df_existing.empty:
            merged = df_new
        else:
            merged = pd.concat([df_existing, df_new], ignore_index=True)
            merged = merged.drop_duplicates(subset=['timestamp_ms']).sort_values('timestamp_ms', ascending=True).reset_index(drop=True)
        self.save(key, merged)
        return merged

    @staticmethod
    def _bars_to_df(bars: List[List[str]]) -> pd.DataFrame:
        rows = []
        for item in bars:
            ts = int(item[0])
            rows.append({
                'timestamp_ms': ts,
                'start_time_iso': iso_from_ms(ts),
                'open': float(item[1]),
                'high': float(item[2]),
                'low': float(item[3]),
                'close': float(item[4]),
                'volume': float(item[5]),
                'turnover': float(item[6]),
            })
        df = pd.DataFrame(rows).sort_values('timestamp_ms', ascending=True).reset_index(drop=True)
        return df
