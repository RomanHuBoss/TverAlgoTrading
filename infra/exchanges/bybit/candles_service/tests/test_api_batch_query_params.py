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

def test_batch_endpoint_query_params(monkeypatch, tmp_path):
    import candles_service.config as cfg
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path/'cache'))
    cfg.get_settings()

    def fake_fetch_klines_page(self, *, category, symbol, interval, limit=200, end=None, start=None):
        step = 60*60*1000
        latest = 1_700_000_000_000
        if end is None:
            end = latest
        return make_page(end, step, min(limit, 6))

    monkeypatch.setattr(BybitClient, 'fetch_klines_page', fake_fetch_klines_page)

    resp = client.post('/candles/download/batch?symbols=BTCUSDT,ETHUSDT&timeframe=1h&hours_back=6')
    assert resp.status_code == 200, resp.text
    arr = resp.json()
    assert isinstance(arr, list) and len(arr) == 2
    for item in arr:
        assert item['ok'] is True
        x = item['result']
        assert x['timeframe'] == '1h'
        assert re.search(r"/(BTCUSDT|ETHUSDT)/1h/candles_\\d{8}-\\d{8}\\.csv$", x['saved_file'])
