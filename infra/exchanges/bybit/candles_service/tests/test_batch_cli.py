import re
from pathlib import Path
from candles_service.cli import batch_download
from candles_service.bybit_client import BybitClient

def make_page(start_ms: int, step_ms: int, n: int):
    bars = []
    t = start_ms
    for i in range(n):
        bars.append([str(t), '1','2','0.5','1.5','10','15'])
        t -= step_ms
    return bars

def test_batch_download(monkeypatch, tmp_path):
    import candles_service.config as cfg
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path/'cache'))
    cfg.get_settings()

    def fake_fetch_klines_page(self, *, category, symbol, interval, limit=200, end=None, start=None):
        step = 60*60*1000  # 1h
        latest = 1_700_000_000_000
        if end is None:
            end = latest
        return make_page(end, step, min(limit, 24))

    monkeypatch.setattr(BybitClient, 'fetch_klines_page', fake_fetch_klines_page)

    res = batch_download(['BTCUSDT','ETHUSDT'], timeframe='1h', hours_back=6)
    assert len(res) == 2
    for r in res:
        assert r['timeframe'] == '1h'
        assert re.search(r"/data/(BTCUSDT|ETHUSDT)/1h/candles_\\d{8}-\\d{8}\\.csv$", r['saved_file'])
