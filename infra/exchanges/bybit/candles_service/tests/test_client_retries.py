from fastapi.testclient import TestClient
from candles_service.api import app
from candles_service.bybit_client import BybitClient

client = TestClient(app)

def test_retries(monkeypatch, tmp_path):
    import candles_service.config as cfg
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('CACHE_DIR', str(tmp_path/'cache'))
    monkeypatch.setenv('BYBIT_MAX_RETRIES', '2')
    cfg.get_settings()

    calls = {'n': 0}
    def fake_request(self, params):
        calls['n'] += 1
        # Первые 2 вызова - ошибка, затем успех
        if calls['n'] <= 2:
            raise RuntimeError('Bybit error: 10001 rate limit')
        # успех: вернем форму, ожидаемую fetch_klines_page
        step = 60*60*1000
        latest = 1_700_000_000_000
        n = min(params.get('limit', 6), 6)
        bars = []
        t = latest
        for i in range(n):
            bars.append([str(t), '1','2','0.5','1.5','10','15'])
            t -= step
        return {'list': bars}

    monkeypatch.setattr(BybitClient, '_request', fake_request)

    resp = client.post('/candles/download', params={
        'symbol':'BTCUSDT', 'timeframe':'1h', 'hours_back': 3
    })
    assert resp.status_code == 200, resp.text
    # Убедимся, что было минимум 3 попытки (2 ошибки + успех)
    assert calls['n'] >= 3
