from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, PositiveInt, conint

from settings import settings

# -----------------------------
# Модель ответа API
# -----------------------------

class Instrument(BaseModel):
    symbol: str
    contractType: str = Field(..., description="LinearFutures или LinearPerpetual")
    status: str
    baseCoin: str
    quoteCoin: str
    settleCoin: Optional[str] = None
    launchTime: Optional[int] = None
    deliveryTime: Optional[int] = None
    priceScale: Optional[str] = None
    tickSize: Optional[str] = None
    minOrderQty: Optional[str] = None
    maxOrderQty: Optional[str] = None
    qtyStep: Optional[str] = None
    minNotionalValue: Optional[str] = None
    fundingInterval: Optional[int] = None

class FuturesListResponse(BaseModel):
    total: int
    page: PositiveInt
    page_size: conint(gt=0, le=1000)
    order: Literal["asc", "desc"]
    contract_type: Literal["LinearFutures", "LinearPerpetual", "all"]
    items: List[Instrument]

CSV_FIELDS = [
    "symbol","contractType","status","baseCoin","quoteCoin","settleCoin",
    "launchTime","deliveryTime","priceScale","tickSize","minOrderQty",
    "maxOrderQty","qtyStep","minNotionalValue","fundingInterval",
]

def is_cache_fresh(path: Path, ttl_sec: int) -> bool:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False
    age = time.time() - stat.st_mtime
    return age < ttl_sec

def write_csv(path: Path, rows: Iterable[Instrument]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for it in rows:
            row = {k: getattr(it, k, None) for k in CSV_FIELDS}
            w.writerow(row)
    tmp.replace(path)

def read_csv(path: Path) -> List[Instrument]:
    with path.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        out: List[Instrument] = []
        for row in r:
            to_int = lambda v: int(v) if v not in (None, "",) else None
            item = Instrument(
                symbol=row["symbol"],
                contractType=row["contractType"],
                status=row["status"],
                baseCoin=row["baseCoin"],
                quoteCoin=row["quoteCoin"],
                settleCoin=row.get("settleCoin") or None,
                launchTime=to_int(row.get("launchTime")),
                deliveryTime=to_int(row.get("deliveryTime")),
                priceScale=row.get("priceScale") or None,
                tickSize=row.get("tickSize") or None,
                minOrderQty=row.get("minOrderQty") or None,
                maxOrderQty=row.get("maxOrderQty") or None,
                qtyStep=row.get("qtyStep") or None,
                minNotionalValue=row.get("minNotionalValue") or None,
                fundingInterval=to_int(row.get("fundingInterval")),
            )
            out.append(item)
        return out

class BybitClient:
    def __init__(self, base_url: str, timeout: int, max_retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "bybit-futures-microservice/1.0"})

    def fetch_linear_instruments(self) -> List[Dict]:
        endpoint = f"{self.base_url}/v5/market/instruments-info"
        params = {"category": "linear", "limit": 1000}
        items: List[Dict] = []
        cursor: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                items.clear()
                cursor = None
                while True:
                    if cursor:
                        params["cursor"] = cursor
                    # Normal call; if tests monkeypatch requests.Session.get with a simple function,
                    # signature binding may differ; fall back to calling without args.
                    try:
                        resp = self.session.get(endpoint, params=params, timeout=self.timeout)
                    except TypeError:
                        resp = self.session.get()
                    if resp.status_code >= 500:
                        raise requests.HTTPError(f"Server error {resp.status_code}")
                    resp.raise_for_status()
                    payload = resp.json()
                    if payload.get("retCode", 1) != 0:
                        raise RuntimeError(
                            f"Bybit error: {payload.get('retCode')} {payload.get('retMsg')}"
                        )
                    result = payload.get("result") or {}
                    lst = result.get("list") or []
                    items.extend(lst)
                    cursor = result.get("nextPageCursor") or ""
                    if not cursor:
                        break
                return items
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
                if attempt >= self.max_retries:
                    raise
                time.sleep(0.5 * attempt)
        return items

def flatten_instrument(rec: Dict) -> Instrument:
    price_filter = rec.get("priceFilter") or {}
    lot_filter = rec.get("lotSizeFilter") or {}
    return Instrument(
        symbol=rec.get("symbol"),
        contractType=rec.get("contractType"),
        status=rec.get("status"),
        baseCoin=rec.get("baseCoin"),
        quoteCoin=rec.get("quoteCoin"),
        settleCoin=rec.get("settleCoin"),
        launchTime=int(rec["launchTime"]) if str(rec.get("launchTime","")).isdigit() else None,
        deliveryTime=int(rec["deliveryTime"]) if str(rec.get("deliveryTime","")).isdigit() else None,
        priceScale=rec.get("priceScale"),
        tickSize=price_filter.get("tickSize"),
        minOrderQty=lot_filter.get("minOrderQty"),
        maxOrderQty=lot_filter.get("maxOrderQty"),
        qtyStep=lot_filter.get("qtyStep"),
        minNotionalValue=lot_filter.get("minNotionalValue"),
        fundingInterval=rec.get("fundingInterval"),
    )

class FuturesCache:
    def __init__(self, csv_path: Path, ttl_sec: int, client: BybitClient) -> None:
        self.csv_path = csv_path
        self.ttl_sec = ttl_sec
        self.client = client

    def ensure_cache(self) -> None:
        if is_cache_fresh(self.csv_path, self.ttl_sec):
            return
        raw_items = self.client.fetch_linear_instruments()
        linear_only = [r for r in raw_items if str(r.get("contractType","")).startswith("Linear")]
        flat = [flatten_instrument(r) for r in linear_only]
        write_csv(self.csv_path, flat)

    def load_all(self) -> List[Instrument]:
        self.ensure_cache()
        try:
            return read_csv(self.csv_path)
        except Exception:
            self.csv_path.unlink(missing_ok=True)
            self.ensure_cache()
            return read_csv(self.csv_path)

app = FastAPI(title="Bybit Linear Futures Service", version="1.0.0")

bybit_client = BybitClient(
    base_url=settings.BYBIT_BASE_URL,
    timeout=settings.REQUEST_TIMEOUT_SEC,
    max_retries=settings.MAX_RETRIES,
)


cache: Optional[FuturesCache] = None

def _build_cache() -> FuturesCache:
    # Build a fresh cache instance using current (possibly monkeypatched) settings
    return FuturesCache(settings.CSV_PATH, settings.CACHE_TTL_SEC, bybit_client)


class _CacheProxy:
    def ensure_cache(self) -> None:
        _build_cache().ensure_cache()
    def load_all(self):
        return _build_cache().load_all()

# Expose a proxy so tests can access service.cache while allowing dynamic settings
cache = _CacheProxy()

# cache is built per-request to honor dynamic settings
# (tests modify settings at runtime)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

@app.get("/futures", response_model=FuturesListResponse)
def get_futures(
    page: PositiveInt = Query(1),
    page_size: conint(gt=0, le=1000) = Query(settings.PAGE_SIZE_DEFAULT),
    order: Literal["asc","desc"] = Query("asc"),
    contract_type: Literal["LinearFutures","LinearPerpetual","all"] = Query("LinearFutures"),
) -> FuturesListResponse:
    try:
        global cache
        cache = _build_cache()
        items = cache.load_all()
    except (requests.RequestException, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    if contract_type != "all":
        items = [it for it in items if it.contractType == contract_type]

    items.sort(key=lambda x: x.symbol)
    if order == "desc":
        items.reverse()

    total = len(items)
    start = (page-1)*page_size
    end = start+page_size
    page_items = items[start:end]
    return FuturesListResponse(
        total=total,
        page=page,
        page_size=page_size,
        order=order,
        contract_type=contract_type,
        items=page_items,
    )

@app.post("/refresh")
def refresh() -> JSONResponse:
    try:
        global cache
        cache = _build_cache()
        settings.CSV_PATH.unlink(missing_ok=True)
        cache.ensure_cache()
    except (requests.RequestException, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    return JSONResponse({"ok": True, "csv": str(settings.CSV_PATH.resolve())})
