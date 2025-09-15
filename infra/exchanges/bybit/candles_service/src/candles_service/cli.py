from __future__ import annotations
import argparse
import sys
from typing import List, Optional, Dict, Any
from pathlib import Path

from .service import DownloadRequest, download_candles, batch_download
from .utils import parse_timeframe

def batch_download(symbols: List[str], *, timeframe: str, category: str = 'linear',
                   candles_back: Optional[int] = None, hours_back: Optional[int] = None,
                   days_back: Optional[int] = None, months_back: Optional[int] = None,
                   years_back: Optional[int] = None, out_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Скачать для нескольких символов. Возвращает список результатов download_candles."""
    if not symbols:
        raise ValueError('Empty symbols list')
    # Валидация таймфрейма заранее (бросит ValueError при ошибке)
    parse_timeframe(timeframe)
    results = []
    for sym in symbols:
        req = DownloadRequest(
            symbol=sym, timeframe=timeframe, category=category,
            candles_back=candles_back, hours_back=hours_back, days_back=days_back,
            months_back=months_back, years_back=years_back, out_dir=out_dir
        )
        res = download_candles(req)
        results.append(res)
    return results

def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='candles-batch', description='Batch download candles from Bybit')
    p.add_argument('--symbols', '-s', nargs='+', help='Список символов через пробел, например: BTCUSDT ETHUSDT', default=[])
    p.add_argument('--symbols-file', help='Путь к файлу со списком символов (по одному в строке)')
    p.add_argument('--timeframe', '-t', required=True, help='Например 30m, 1h, 4h, D, W, M')
    p.add_argument('--category', default='linear', choices=['spot','linear','inverse'])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--candles-back', type=int)
    g.add_argument('--hours-back', type=int)
    g.add_argument('--days-back', type=int)
    g.add_argument('--months-back', type=int)
    g.add_argument('--years-back', type=int)
    p.add_argument('--out-dir', help='Корневая директория вывода (по умолчанию ./data)')
    return p.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> int:
    ns = _parse_args(argv or sys.argv[1:])
    symbols: List[str] = list(ns.symbols or [])
    if ns.symbols_file:
        path = Path(ns.symbols_file)
        if not path.exists():
            print(f'File not found: {path}', file=sys.stderr)
            return 2
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    symbols.append(line)
    try:
        res = batch_download(
            symbols, timeframe=ns.timeframe, category=ns.category,
            candles_back=ns.candles_back, hours_back=ns.hours_back, days_back=ns.days_back,
            months_back=ns.months_back, years_back=ns.years_back, out_dir=ns.out_dir
        )
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    # Красивый вывод
    if res:
        print('Downloaded:')
        for r in res:
        if r.get('ok'):
            x = r['result']
            print(f" - {x['symbol']:>10s}  {x['timeframe']:>4s}  {x['rows']:>6d} rows  -> {x['saved_file']}")
        else:
            print(f" - {r.get('symbol','?'):>10s}  ERROR  {r.get('error','')}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
