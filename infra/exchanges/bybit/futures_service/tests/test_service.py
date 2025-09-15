import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import service

class DummyResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")
    def json(self):
        return self._payload

def make_payload(list_items, cursor=""):
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"category":"linear","list":list_items,"nextPageCursor":cursor},
        "time": 0,
    }

def test_cache_and_fetch(monkeypatch, tmp_path):
    service.settings.CSV_PATH = tmp_path / "cache.csv"
    calls = {"n":0}
    def fake_get(url, params=None, timeout=0):
        calls["n"]+=1
        items=[{
            "symbol":"BTCUSDT","contractType":"LinearFutures","status":"Trading",
            "baseCoin":"BTC","quoteCoin":"USDT","launchTime":"0","deliveryTime":"0",
            "priceScale":"2","priceFilter":{"tickSize":"0.1"},
            "lotSizeFilter":{"minOrderQty":"0.001","maxOrderQty":"10","qtyStep":"0.001","minNotionalValue":"5"},
            "fundingInterval":0,
        }]
        return DummyResp(200, make_payload(items))
    monkeypatch.setattr(service.requests.Session, "get", fake_get)
    service.cache.ensure_cache()
    assert service.settings.CSV_PATH.exists()
    assert calls["n"]==1
    service.cache.ensure_cache()
    assert calls["n"]==1

def test_endpoint(monkeypatch, tmp_path):
    service.settings.CSV_PATH = tmp_path / "cache.csv"
    def fake_get(url, params=None, timeout=0):
        items=[{
            "symbol":"ETHUSDT","contractType":"LinearFutures","status":"Trading",
            "baseCoin":"ETH","quoteCoin":"USDT","launchTime":"0","deliveryTime":"0",
            "priceScale":"2","priceFilter":{"tickSize":"0.01"},
            "lotSizeFilter":{"minOrderQty":"0.01","maxOrderQty":"10","qtyStep":"0.01","minNotionalValue":"5"},
            "fundingInterval":0,
        },{
            "symbol":"BTCUSDT","contractType":"LinearFutures","status":"Trading",
            "baseCoin":"BTC","quoteCoin":"USDT","launchTime":"0","deliveryTime":"0",
            "priceScale":"2","priceFilter":{"tickSize":"0.1"},
            "lotSizeFilter":{"minOrderQty":"0.001","maxOrderQty":"10","qtyStep":"0.001","minNotionalValue":"5"},
            "fundingInterval":0,
        }]
        return DummyResp(200, make_payload(items))
    monkeypatch.setattr(service.requests.Session, "get", fake_get)
    client = TestClient(service.app)
    resp = client.get("/futures", params={"page":1,"page_size":1,"order":"asc"})
    assert resp.status_code==200
    data=resp.json()
    assert "items" in data
    assert data["total"]==2
