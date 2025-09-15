import json
import types
import pandas as pd
from fastapi.testclient import TestClient

from candles_service.api import app
from candles_service.bybit_client import BybitClient

client = TestClient(app)

def make_page(start_ms: int, step_ms: int, n: int):
    bars = []
    t = start_ms
    for i in range(n):
        bars.append([str(t), '1','2','0.5','1.5','10','15'])
        t -= step_ms
    return bars

def test_download_candles_hours_back(monkeypatch, tmp_path):
    import candles_service.config as cfg
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path/'cache'))
    cfg.get_settings()
    def fake_fetch_klines_page(self, *, category, symbol, interval, limit=200, end=None, start=None):
        step = 30*60*1000
        latest = 1_700_000_000_000
        if end is None:
            end = latest
        return make_page(end, step, limit)
    monkeypatch.setattr(BybitClient, 'fetch_klines_page', fake_fetch_klines_page)
    resp = client.post('/candles/download', params={
        'symbol':'BTCUSDT',
        'timeframe':'30m',
        'hours_back': 3,
        'category': 'linear',
        'out_dir': str(tmp_path/'out')
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data['symbol'] == 'BTCUSDT'
    assert data['timeframe'] == '30m'
    assert data['mode'] == 'hours_back'
    assert data['value'] == 3
    import re
    assert re.search(r"BTCUSDT/30m/candles_\d{8}-\d{8}\.csv$", data['saved_file'])
