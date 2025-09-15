from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Tuple

_MIN_TO_MS = 60_000
_HOUR_TO_MS = 60 * _MIN_TO_MS
_DAY_TO_MS = 24 * _HOUR_TO_MS
_WEEK_TO_MS = 7 * _DAY_TO_MS

_BYBIT_ALLOWED = {'1','3','5','15','30','60','120','240','360','720','D','W','M'}

def parse_timeframe(tf: str) -> Tuple[str, str, int]:
    s = (tf or '').strip()
    if not s:
        raise ValueError('timeframe is required')
    s_lower = s.lower()
    if s in _BYBIT_ALLOWED:
        if s in {'D','W','M'}:
            friendly = {'D':'1d','W':'1w','M':'1m'}.get(s, s)
            ms = _DAY_TO_MS if s=='D' else (_WEEK_TO_MS if s=='W' else 30*_DAY_TO_MS)
            return s, friendly, ms
        minutes = int(s)
        ms = minutes * _MIN_TO_MS
        friendly = f"{minutes}m" if minutes < 60 else (f"{minutes//60}h" if minutes % 60 == 0 else f"{minutes}m")
        return s, friendly, ms
    if s_lower.endswith('m') and s_lower != 'm':
        if s_lower.endswith('mo') or s_lower.endswith('mon'):
            try:
                n = int(s_lower[:-2])
            except ValueError:
                raise ValueError(f'Invalid timeframe: {tf}')
            if n != 1:
                raise ValueError('Bybit month interval supports only single months as unit. Use "M" or "1M"/"1mo".')
            return 'M', '1m', 30*_DAY_TO_MS
        try:
            n = int(s_lower[:-1])
        except ValueError:
            raise ValueError(f'Invalid timeframe: {tf}')
        if n not in {1,3,5,15,30}:
            raise ValueError('Allowed minute timeframes: 1m,3m,5m,15m,30m')
        return str(n), f"{n}m", n*_MIN_TO_MS
    if s_lower.endswith('h'):
        n = int(s_lower[:-1])
        mapping = {1: '60', 2: '120', 4: '240', 6: '360', 12: '720'}
        if n not in mapping:
            raise ValueError('Allowed hour timeframes: 1h,2h,4h,6h,12h')
        return mapping[n], f"{n}h", n*_HOUR_TO_MS
    if s_lower in {'d','1d'}:
        return 'D', '1d', _DAY_TO_MS
    if s_lower in {'w','1w'}:
        return 'W', '1w', _WEEK_TO_MS
    if s_lower in {'m','1m'}:
        return 'M', '1m', 30*_DAY_TO_MS
    raise ValueError(f'Unsupported timeframe: {tf}')

def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp()*1000)

def iso_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).isoformat()
