from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
import requests
from .config import get_settings
from .utils import now_ms

import time

class BybitClient:
    """Минимальный REST-клиент для /v5/market/kline.
    Документация: https://bybit-exchange.github.io/docs/v5/market/kline
    Параметры: category (spot|linear|inverse), symbol (BTCUSDT), interval (1|3|..|D|W|M),
    start, end (мс), limit (1..1000; по умолчанию 200).
    """
    def __init__(self, session: Optional[requests.Session] = None):
        self.s = session or requests.Session()
        self.settings = get_settings()
        self._min_interval = 1.0 / max(0.1, self.settings.bybit_qps)
        self._last_request_ts = 0.0

    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.settings.bybit_base_url.rstrip('/')}/v5/market/kline"
        attempt = 0
        while True:
            # QPS limiter
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.s.get(url, params=params, timeout=self.settings.request_timeout_sec)
                self._last_request_ts = time.monotonic()
                r.raise_for_status()
                data = r.json()
                if data.get('retCode') != 0:
                    raise RuntimeError(f"Bybit error: {data.get('retCode')} {data.get('retMsg')}")
                return data['result']
            except Exception as e:
                attempt += 1
                if attempt > self.settings.bybit_max_retries:
                    raise
                time.sleep(self.settings.bybit_retry_backoff_sec * attempt)

    def fetch_klines_page(self, *, category: str, symbol: str, interval: str, limit: int = 200,
                          end: Optional[int] = None, start: Optional[int] = None) -> List[List[str]]:
        params = {
            'category': category,
            'symbol': symbol,
            'interval': interval,
            'limit': min(max(1, limit), self.settings.max_bars_per_request),
        }
        if end is not None:
            params['end'] = int(end)
        if start is not None:
            params['start'] = int(start)

        result = self._request(params)
        return result.get('list', [])

    def fetch_until(self, *, category: str, symbol: str, interval: str,
                    need_count: Optional[int] = None,
                    start_threshold_ms: Optional[int] = None) -> List[List[str]]:
        assert need_count is not None or start_threshold_ms is not None, "Specify need_count or start_threshold_ms"
        combined: List[List[str]] = []
        end_cursor: Optional[int] = None  # None => свежая страница
        max_per_page = self.settings.max_bars_per_request
        while True:
            lim = max_per_page
            if need_count is not None:
                lim = min(lim, max(1, need_count - len(combined)))
            page = self.fetch_klines_page(category=category, symbol=symbol, interval=interval, limit=lim, end=end_cursor)
            if not page:
                break
            combined.extend(page)
            oldest_start = int(page[-1][0])
            end_cursor = oldest_start - 1
            enough_by_count = need_count is not None and len(combined) >= need_count
            enough_by_time = start_threshold_ms is not None and oldest_start <= start_threshold_ms
            if enough_by_count or enough_by_time:
                break
        return combined

    def update_forward(self, *, category: str, symbol: str, interval: str, from_exclusive_ms: int) -> List[List[str]]:
        end = now_ms()
        page = self.fetch_klines_page(category=category, symbol=symbol, interval=interval,
                                      start=from_exclusive_ms + 1, end=end, limit=self.settings.max_bars_per_request)
        return page
