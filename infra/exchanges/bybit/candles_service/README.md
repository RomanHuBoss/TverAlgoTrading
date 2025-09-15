# Bybit Candles Downloader (microservice)

Сервис скачивает **последние свечи (OHLCV)** с Bybit для заданного символа и таймфрейма и сохраняет результат в CSV.
Поддерживаются разные способы задать «сколько последних свечей» — количеством или «за N часов/дней/месяцев/лет».

Документация Bybit (REST V5): /v5/market/kline. Список допустимых интервалов: `1,3,5,15,30,60,120,240,360,720,D,W,M` (минуты, дни, недели, месяцы).

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Запуск сервиса
uvicorn candles_service.api:app --reload --port 8081
```

Проверка живости:
```
GET http://127.0.0.1:8081/health
```

## Эндпоинт

```
POST /candles/download
```

### Параметры (query или JSON- тело)

- `symbol` (строка, **обязательно**): например, `BTCUSDT` (верхним регистром)
- `timeframe` (строка, **обязательно**): например, `30m`, `1h`, `4h`, `D`, `W`, `M`
- `category` (строка, опционально): `spot` | `linear` | `inverse` (по умолчанию `linear`)
- Один из вариантов диапазона (указать **ровно один**):
  - `candles_back` (int) – количество последних свечей
  - `hours_back` (int) – часов к текущему моменту
  - `days_back` (int) – дней к текущему моменту
  - `months_back` (int) – месяцев к текущему моменту
  - `years_back` (int) – лет к текущему моменту
- `out_dir` (строка, опционально): корневая папка выгрузки (по умолчанию `./data`)

### Ответ
```json
{
  "saved_file": "data/BTCUSDT/30m/candles_20240101-20240131.csv",
  "rows": 60,
  "symbol": "BTCUSDT",
  "timeframe": "30m",
  "category": "linear",
  "mode": "hours_back",
  "value": 30
}
```

### Схема CSV
Колонки: `timestamp_ms,start_time_iso,open,high,low,close,volume,turnover` (восходящая сортировка по времени).

## Кэширование

Сервис поддерживает файловый кэш по ключу **(symbol, timeframe)** в папке `./cache/<SYMBOL>/<timeframe>/candles.csv`. 
- При каждом запросе сервис:
  1. Подгружает кэш и, если нужно, **дотягивает свежие свечи** (до текущего момента) минимальным числом запросов в Bybit.
  2. Если диапазон выходит в прошлое дальше имеющегося кэша — дозагружает **недостающий «хвост»** назад постранично (Bybit возвращает до 1000 свечей за запрос).
  3. Обновляет кэш (директива «dedupe on timestamp»).
- Папки выгрузки — `./data/<SYMBOL>/<timeframe>/...` (для разных валют и таймфреймов — отдельные директории).

Отключение/настройка кэша через переменные окружения (см. ниже).

## Конфигурация

Через переменные окружения:
- `BYBIT_BASE_URL` (по умолчанию `https://api.bybit.com`)
- `DATA_DIR` (по умолчанию `./data`)
- `CACHE_DIR` (по умолчанию `./cache`)
- `REQUEST_TIMEOUT_SEC` (по умолчанию `10`)
- `MAX_BARS_PER_REQUEST` (по умолчанию `1000`)
- `ENABLE_CACHE` (по умолчанию `true`)

## Примеры

```bash
# 30 минутки за последние 30 часов
curl -X POST "http://127.0.0.1:8081/candles/download?symbol=BTCUSDT&timeframe=30m&hours_back=30"

# 4 часа, 1000 свечей
curl -X POST "http://127.0.0.1:8081/candles/download?symbol=ETHUSDT&timeframe=4h&candles_back=1000"

# Дневки за последние 2 года в отдельную папку
curl -X POST "http://127.0.0.1:8081/candles/download?symbol=SOLUSDT&timeframe=D&years_back=2&out_dir=/tmp/out"
```

## Тесты

```bash
pytest -q
```

## Docker

```Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
ENV PYTHONPATH=/app/src
EXPOSE 8081
CMD ["uvicorn", "candles_service.api:app", "--host", "0.0.0.0", "--port", "8081"]
```
Сохраните как `Dockerfile` и соберите:
```bash
docker build -t bybit-candles .
docker run --rm -p 8081:8081 -v $PWD/data:/app/data -v $PWD/cache:/app/cache bybit-candles
```


## CLI: пакетная выгрузка

Можно запускать без API, одной командой:

```bash
# через модуль
python -m candles_service.cli --symbols BTCUSDT ETHUSDT --timeframe 30m --hours-back 12

# из файла со списком (по одному символу в строке)
python -m candles_service.cli --symbols-file symbols.txt --timeframe D --years-back 1
```

Ключи диапазона взаимно исключающие — укажите ровно один из:
`--candles-back`, `--hours-back`, `--days-back`, `--months-back`, `--years-back`.


## REST: пакетная выгрузка

```
POST /candles/download/batch
Content-Type: application/json

{
  "symbols": ["BTCUSDT","ETHUSDT","SOLUSDT"],
  "timeframe": "1h",
  "hours_back": 12,
  "category": "linear",
  "out_dir": "./data"
}
```

Ответ — список результатов `download_candles` по каждому символу.
