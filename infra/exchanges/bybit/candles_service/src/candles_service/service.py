from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import pandas as pd
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta

from .config import get_settings
from .utils import parse_timeframe, now_ms
import concurrent.futures
from .bybit_client import BybitClient
from .cache import CandleCache, CacheKey

@dataclass
class DownloadRequest:
    symbol: str
    timeframe: str
    category: str = 'linear'
    candles_back: Optional[int] = None
    hours_back: Optional[int] = None
    days_back: Optional[int] = None
    months_back: Optional[int] = None
    years_back: Optional[int] = None
    out_dir: Optional[str] = None

def _validate_and_mode(req: DownloadRequest) -> Tuple[str, int]:
    provided = {k: v for k, v in {
        'candles_back': req.candles_back,
        'hours_back': req.hours_back,
        'days_back': req.days_back,
        'months_back': req.months_back,
        'years_back': req.years_back,
    }.items() if v is not None}
    if len(provided) != 1:
        raise ValueError('Ровно один из параметров обязателен: candles_back | hours_back | days_back | months_back | years_back')
    mode, value = next(iter(provided.items()))
    if value <= 0:
        raise ValueError(f'{mode} должен быть положительным')
    return mode, int(value)

def _friendly_suffix(mode: str, value: int) -> str:
    mapping = {
        'candles_back': 'candles_back',
        'hours_back': 'hours_back',
        'days_back': 'days_back',
        'months_back': 'months_back',
        'years_back': 'years_back',
    }
    return f"{value}{mapping[mode]}"

def _symbol_tf_dir(base: Path, symbol: str, friendly_tf: str) -> Path:
    d = base / symbol.upper() / friendly_tf
    d.mkdir(parents=True, exist_ok=True)
    return d

def _output_path(base: Path, symbol: str, friendly_tf: str, start_ms: int, end_ms: int) -> Path:
    # Имя файла формата candles_YYYYMMDD-YYYYMMDD.csv
    start_date = datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).strftime('%Y%m%d')
    end_date = datetime.fromtimestamp(end_ms/1000, tz=timezone.utc).strftime('%Y%m%d')
    fname = f"candles_{start_date}-{end_date}.csv"
    return _symbol_tf_dir(base, symbol, friendly_tf) / fname

def _ensure_cache_for_range(cache: CandleCache, client: BybitClient, symbol: str, api_interval: str,
                            *, category: str, target_start_ms: Optional[int], need_count: Optional[int]) -> pd.DataFrame:
    """Гарантируем, что кэш покрывает требуемый диапазон по времени или количеству.

    1) Если кэш пуст — качаем последовательно страницы от «свежих» в прошлое до выполнения условий.
    2) Иначе: дотягиваем вперёд новые бары, затем при необходимости «доливаем» назад, двигая end-курсор.
    """
    key = CacheKey(symbol=symbol.upper(), interval=api_interval)
    df = cache.load(key)
    if df is None:
        df = pd.DataFrame(columns=['timestamp_ms','start_time_iso','open','high','low','close','volume','turnover'])

    now = now_ms()

    if df.empty:
        # Начальная загрузка
        bars = client.fetch_until(category=category, symbol=symbol, interval=api_interval,
                                  need_count=need_count, start_threshold_ms=target_start_ms)
        df = cache.merge_and_save(key, bars)
    else:
        # Дотянуть новые бары «вперёд»
        last_ts = int(df['timestamp_ms'].iloc[-1])
        forward = client.update_forward(category=category, symbol=symbol, interval=api_interval, from_exclusive_ms=last_ts)
        if forward:
            df = cache.merge_and_save(key, forward)

        # Проверка необходимости «назад»
        def coverage_ok() -> bool:
            ok = True
            if need_count is not None and len(df) < need_count:
                ok = False
            if target_start_ms is not None and (df.empty or int(df['timestamp_ms'].iloc[0]) > target_start_ms):
                ok = False
            return ok

        # Доливаем назад страницами
        while not coverage_ok():
            earliest = int(df['timestamp_ms'].iloc[0]) if not df.empty else now
            page = client.fetch_klines_page(category=category, symbol=symbol, interval=api_interval,
                                            end=earliest - 1, limit=get_settings().max_bars_per_request)
            if not page:
                break
            df = cache.merge_and_save(key, page)
            # цикл продолжится пока не покроем условия или не иссякнут данные

    return df

def _compute_target_start_ms(mode: str, value: int) -> int:
    now_dt = datetime.now(timezone.utc)
    if mode == 'hours_back':
        start_dt = now_dt - timedelta(hours=value)
    elif mode == 'days_back':
        start_dt = now_dt - timedelta(days=value)
    elif mode == 'months_back':
        start_dt = now_dt - relativedelta(months=value)
    elif mode == 'years_back':
        start_dt = now_dt - relativedelta(years=value)
    else:
        raise ValueError('Unsupported mode for date arithmetic')
    return int(start_dt.timestamp()*1000)



def batch_download(symbols: List[str], *, timeframe: str, category: str = 'linear',
                   candles_back: Optional[int] = None, hours_back: Optional[int] = None,
                   days_back: Optional[int] = None, months_back: Optional[int] = None,
                   years_back: Optional[int] = None, out_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Скачать для нескольких символов (параллельно), вернуть список результатов/ошибок.
    Поля ответа:
      - ok: bool
      - result: объект ответа download_candles (если ok)
      - error: текст ошибки (если не ok)
    """
    if not symbols:
        raise ValueError('Empty symbols list')
    parse_timeframe(timeframe)
    settings = get_settings()
    max_workers = min(8, max(1, len(symbols)))
    out: List[Dict[str, Any]] = []

    def _work(sym: str) -> Dict[str, Any]:
        try:
            req = DownloadRequest(
                symbol=sym, timeframe=timeframe, category=category,
                candles_back=candles_back, hours_back=hours_back, days_back=days_back,
                months_back=months_back, years_back=years_back, out_dir=out_dir
            )
            res = download_candles(req)
            return {'ok': True, 'result': res}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'symbol': sym}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futmap = {ex.submit(_work, s): s for s in symbols}
        for fut in as_completed(futmap):
            out.append(fut.result())
    return out

def download_candles(req: DownloadRequest) -> Dict[str, Any]:
    settings = get_settings()
    mode, value = _validate_and_mode(req)
    api_interval, friendly_tf, interval_ms = parse_timeframe(req.timeframe)

    need_count: Optional[int] = None
    target_start_ms: Optional[int] = None
    if mode == 'candles_back':
        need_count = value
    else:
        factor = {
            'hours_back': 60*60*1000,
            'days_back': 24*60*60*1000,
            'months_back': 30*24*60*60*1000,
            'years_back': 365*24*60*60*1000,
        }[mode]
        target_start_ms = now_ms() - value * factor

    cache = CandleCache()
    client = BybitClient()

    df = _ensure_cache_for_range(cache, client, req.symbol, api_interval,
                                 category=req.category, target_start_ms=target_start_ms, need_count=need_count)

    if need_count is not None:
        df_out = df.tail(need_count).copy()
    else:
        df_out = df[df['timestamp_ms'] >= target_start_ms].copy()

    df_out = df_out.sort_values('timestamp_ms', ascending=True).reset_index(drop=True)

    out_dir = Path(req.out_dir).resolve() if req.out_dir else settings.data_dir
    start_ms = int(df_out['timestamp_ms'].iloc[0]) if not df_out.empty else now_ms()
    end_ms = int(df_out['timestamp_ms'].iloc[-1]) if not df_out.empty else now_ms()
    out_path = _output_path(out_dir, req.symbol, friendly_tf, start_ms, end_ms)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(out_path, index=False)

    return {
        'saved_file': str(out_path),
        'rows': int(len(df_out)),
        'symbol': req.symbol.upper(),
        'timeframe': friendly_tf,
        'category': req.category,
        'mode': mode,
        'value': value,
    }
