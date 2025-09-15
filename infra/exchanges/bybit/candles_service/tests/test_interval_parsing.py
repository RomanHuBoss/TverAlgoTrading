import pytest
from candles_service.utils import parse_timeframe

@pytest.mark.parametrize('inp, api, friendly, ms', [
    ('30m', '30', '30m', 30*60*1000),
    ('1h', '60', '1h', 60*60*1000),
    ('4h', '240', '4h', 4*60*60*1000),
    ('D', 'D', '1d', 24*60*60*1000),
    ('W', 'W', '1w', 7*24*60*60*1000),
    ('M', 'M', '1m', 30*24*60*60*1000),
])
def test_parse_timeframe(inp, api, friendly, ms):
    a, f, m = parse_timeframe(inp)
    assert a == api
    assert f == friendly
    assert m == ms
