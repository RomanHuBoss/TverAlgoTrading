import re
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

def test_batch_endpoint(monkeypatch, tmp_path):
    import candles_service.config as cfg
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path/'cache'))
    cfg.get_settings()

    def fake_fetch_klines_page(self, *, category, symbol, interval, limit=200, end=None, start=None):
        # 1h bars, return up to 12
        step = 60*60*1000
        latest = 1_700_000_000_000
        if end is None:
            end = latest
        return make_page(end, step, min(limit, 12))

    monkeypatch.setattr(BybitClient, 'fetch_klines_page', fake_fetch_klines_page)

    body = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "timeframe": "1h",
        "hours_back": 6
    }
    resp = client.post('/candles/download/batch', json=body)
    assert resp.status_code == 200, resp.text
    arr = resp.json()
    assert isinstance(arr, list) and len(arr) == 2
    for item in arr:
        assert item['timeframe'] == '1h'
        assert re.search(r"/(BTCUSDT|ETHUSDT)/1h/candles_\\d{8}-\\d{8}\\.csv$", item['saved_file'])


def test_batch_endpoint_query(monkeypatch, tmp_path):
    import candles_service.config as cfg
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path/'cache'))
    cfg.get_settings()

    from candles_service.bybit_client import BybitClient

    def fake_fetch_klines_page(self, *, category, symbol, interval, limit=200, end=None, start=None):
        step = 60*60*1000
        latest = 1_700_000_000_000
        if end is None:
            end = latest
        bars = []
        t = end
        for i in range(min(limit, 6)):
            bars.append([str(t), '1','2','0.5','1.5','10','15'])
            t -= step
        return bars

    monkeypatch.setattr(BybitClient, 'fetch_klines_page', fake_fetch_klines_page)

    body = {
        "symbols": ["BTCUSDT"],
        "timeframe": "1h",
        "hours_back": 6
    }
    resp = client.post('/candles/download/batch?symbols=ETHUSDT,LTCUSDT', json=body)
    assert resp.status_code == 200
    arr = resp.json()
    syms = [a['symbol'] for a in arr]
    assert set(syms) == {"BTCUSDT","ETHUSDT","LTCUSDT"}
