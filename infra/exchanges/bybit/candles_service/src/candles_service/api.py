from __future__ import annotations
from fastapi import FastAPI, Query, Body, HTTPException
from typing import Optional, Dict, Any
from .service import download_candles, DownloadRequest

app = FastAPI(title="Bybit Candles Downloader", version="1.0.0")

@app.get('/health')
def health() -> Dict[str, str]:
    return {'status': 'ok'}

@app.post('/candles/download')
def candles_download(
    symbol: str = Query(..., description='Например BTCUSDT'),
    timeframe: str = Query(..., description='Например 30m, 1h, 4h, D, W, M'),
    category: str = Query('linear', description='spot | linear | inverse'),
    candles_back: Optional[int] = Query(None),
    hours_back: Optional[int] = Query(None),
    days_back: Optional[int] = Query(None),
    months_back: Optional[int] = Query(None),
    years_back: Optional[int] = Query(None),
    out_dir: Optional[str] = Query(None),
    body: Optional[dict] = Body(None)
) -> Dict[str, Any]:
    try:
        req = DownloadRequest(
            symbol=symbol, timeframe=timeframe, category=category,
            candles_back=candles_back, hours_back=hours_back, days_back=days_back,
            months_back=months_back, years_back=years_back, out_dir=out_dir
        )
        return download_candles(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel, Field
from typing import List

class BatchDownloadBody(BaseModel):
    symbols: List[str] = Field(..., description='Список символов, например ["BTCUSDT","ETHUSDT"]')
    timeframe: str
    category: str = 'linear'
    candles_back: Optional[int] = None
    hours_back: Optional[int] = None
    days_back: Optional[int] = None
    months_back: Optional[int] = None
    years_back: Optional[int] = None
    out_dir: Optional[str] = None

def _validate_one_mode(body: BatchDownloadBody) -> None:
    provided = [v for v in [body.candles_back, body.hours_back, body.days_back, body.months_back, body.years_back] if v is not None]
    if len(provided) != 1:
        raise HTTPException(status_code=422, detail='Укажите ровно один параметр из: candles_back | hours_back | days_back | months_back | years_back')

@app.post('/candles/download/batch')
def candles_download_batch(body: BatchDownloadBody, symbols: Optional[str] = Query(None, description='Список символов через запятую, например BTCUSDT,ETHUSDT')):
    _validate_one_mode(body)
    try:
        from .service import batch_download
        symbols_list = list(body.symbols)
        if symbols:
            symbols_list.extend([s.strip() for s in symbols.split(',') if s.strip()])
        res = batch_download(symbols_list,
            body.symbols, timeframe=body.timeframe, category=body.category,
            candles_back=body.candles_back, hours_back=body.hours_back, days_back=body.days_back,
            months_back=body.months_back, years_back=body.years_back, out_dir=body.out_dir
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
