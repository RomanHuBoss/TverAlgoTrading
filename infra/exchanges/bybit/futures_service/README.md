# Bybit Linear Futures Service

Микросервис для проекта **TverAlgoTrading**, который:
- получает список **линейных контрактов** Bybit (LinearFutures и LinearPerpetual) через публичный REST V5;
- кэширует данные в **CSV** на диске с заданным временем жизни (TTL);
- отдаёт клиенту список инструментов с **сортировкой по символу** и **пагинацией**.

> Фокус сервиса — **линейные фьючерсы**. По умолчанию API отдаёт `LinearFutures`, но по параметру можно запросить и `LinearPerpetual`, или сразу `all`.

---

## Назначение и место в репозитории

Расположение: `TverAlgoTrading/infra/exchanges/bybit/futures_service/`

Сервис относится к инфраструктурному слою и обеспечивает **централизованный, дешёвый по сетевым вызовам источник метаданных контрактов** для других компонентов (стратегии, оркестраторы, симуляторы).

---

## Архитектура (в двух словах)

- **Источник данных**: Bybit REST V5 `GET /v5/market/instruments-info?category=linear`  
  Пагинация — по `nextPageCursor`, лимит — `limit=1000` (для уменьшения количества запросов).  
  Отбираем только записи с `contractType` начинающимся на `Linear*` и приводим в унифицированную модель `Instrument`.

- **Кэш**: CSV‑файл на диске. При обращении к API сервиса:
  1. Если файла **нет** или **просрочен** (старше `CACHE_TTL_SEC`) — сервис запрашивает Bybit и перезаписывает кэш **атомарно** (`.tmp` → `rename`).
  2. Если файл **свежий** — **в сеть не ходим**, читаем локально.

- **API сервиса**: FastAPI, три эндпоинта:
  - `GET /health` — проверка живости;
  - `GET /futures` — выдача списка инструментов с сортировкой/фильтрацией/пагинацией;
  - `POST /refresh` — принудительное обновление кэша.

- **Ключевые классы**:
  - `BybitClient` — инкапсулирует REST вызовы и ретраи;
  - `FuturesCache` — управляет актуальностью CSV;
  - `Instrument` — pydantic‑модель ответа;
  - Вспомогательные функции: `is_cache_fresh`, `write_csv`, `read_csv`, `flatten_instrument`.

---

## Конфигурация

Конфиг реализован через **pydantic‑settings** с поддержкой **трёх источников**:

1. **Переменные окружения** (включая `.env` в рабочей директории) — **наивысший приоритет**.  
2. **`config.yaml`** — дефолтные настройки в файле рядом с сервисом.  
3. Значения **по умолчанию** в коде.

Приоритет: **env → config.yaml → defaults**.

### Доступные параметры

| Ключ | Тип | По умолчанию | Описание |
|---|---:|---|---|
| `CSV_PATH` | `Path` | `bybit_linear_futures.csv` | Путь к файлу кэша CSV |
| `CACHE_TTL_SEC` | `int` | `3600` | TTL кэша в секундах |
| `BYBIT_BASE_URL` | `str` | `https://api.bybit.com` | База REST‑API Bybit |
| `REQUEST_TIMEOUT_SEC` | `int` | `15` | Таймаут HTTP запроса |
| `MAX_RETRIES` | `int` | `3` | Кол-во ретраев на сетевые/5xx ошибки |
| `PAGE_SIZE_DEFAULT` | `int` | `50` | Размер страницы по умолчанию в выдаче сервиса |

### Примеры конфигурации

**config.yaml**:
```yaml
CSV_PATH: ./bybit_linear_futures.csv
CACHE_TTL_SEC: 1800
BYBIT_BASE_URL: https://api.bybit.com
REQUEST_TIMEOUT_SEC: 10
MAX_RETRIES: 5
PAGE_SIZE_DEFAULT: 100
```

**.env**:
```dotenv
CSV_PATH=/abs/path/cache/bybit_linear_futures.csv
CACHE_TTL_SEC=900
```

> Любой ключ из `config.yaml` может быть переопределён переменной окружения.

---

## Формат CSV‑кэша

Файл содержит заголовок и строки с полями (все значения — строки, кроме меток времени, которые при чтении приводятся к `int`):
```
symbol,contractType,status,baseCoin,quoteCoin,settleCoin,
launchTime,deliveryTime,priceScale,tickSize,minOrderQty,
maxOrderQty,qtyStep,minNotionalValue,fundingInterval
```

- `contractType` ∈ `{LinearFutures, LinearPerpetual}`  
- `launchTime`, `deliveryTime` — unix‑time в миллисекундах (если предоставлено API)  
- Запись выполняется **атомарно** через временный файл: исключает «рваные» данные при гонках записи.

---

## Установка и запуск (без Docker)

1) Python окружение:
```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
```

2) Зависимости:
```bash
pip install -r requirements.txt
```

3) (Опционально) подготовьте `config.yaml` или `.env` в директории сервиса.

4) Запуск API:
```bash
uvicorn service:app --host 0.0.0.0 --port 8000 --reload
```

5) Откройте Swagger:
```
http://127.0.0.1:8000/docs
```

---

## Эндпоинты

### `GET /health`
Простая проверка:
```json
{"status":"ok"}
```

### `GET /futures` — список линейных контрактов Bybit

**Query‑параметры:**
- `page` — номер страницы, **1‑based**, по умолчанию `1`;
- `page_size` — размер страницы, по умолчанию `PAGE_SIZE_DEFAULT` из конфигурации, максимум `1000`;
- `order` — сортировка по символу: `asc` (по умолчанию) или `desc`;
- `contract_type` — фильтрация по типу: `LinearFutures` (по умолчанию), `LinearPerpetual` или `all`.

**Примеры:**
```bash
# Первая страница по 25 инструментов, сортировка по возрастанию, только фьючерсы
curl "http://127.0.0.1:8000/futures?page=1&page_size=25&order=asc&contract_type=LinearFutures"

# Все линейные контракты (фьючерсы + перпетуалы), обратная сортировка
curl "http://127.0.0.1:8000/futures?contract_type=all&order=desc"
```

**Ответ (схема):**
```json
{
  "total": 2,
  "page": 1,
  "page_size": 2,
  "order": "asc",
  "contract_type": "LinearFutures",
  "items": [
    {
      "symbol": "BTCUSDT",
      "contractType": "LinearFutures",
      "status": "Trading",
      "baseCoin": "BTC",
      "quoteCoin": "USDT",
      "settleCoin": "USDT",
      "launchTime": 0,
      "deliveryTime": 9999999999999,
      "priceScale": "2",
      "tickSize": "0.1",
      "minOrderQty": "0.001",
      "maxOrderQty": "10",
      "qtyStep": "0.001",
      "minNotionalValue": "5",
      "fundingInterval": 0
    }
  ]
}
```

**Поведение при выходе за пределы**: если `page` указывает за конец списка — вернётся пустой массив `items`, без ошибки.

**Коды ошибок:**
- `422` — неверные параметры запроса (валидация query‑параметров);
- `502` — ошибка похода в Bybit (таймаут, 5xx, `retCode != 0`);
- `500` — непредвиденная внутренняя ошибка.

### `POST /refresh` — принудительный апдейт кэша

Удаляет текущий CSV (если есть) и заново загружает список из Bybit.
```bash
curl -X POST "http://127.0.0.1:8000/refresh"
```
Ответ:
```json
{"ok": true, "csv": "/abs/path/bybit_linear_futures.csv"}
```

---

## Внутреннее устройство (детали реализации)

- **`settings.py`** — конфигурация на базе pydantic‑settings. Источники: `.env`, `config.yaml`, окружение.  
- **`service.py`** — основной код FastAPI и логика кэширования:
  - `BybitClient.fetch_linear_instruments()` — забирает **все страницы** `category=linear`, ретраит сетевые/5xx;
  - `flatten_instrument()` — маппинг ответа Bybit в `Instrument` (извлекает вложенные `priceFilter`, `lotSizeFilter`);
  - `FuturesCache.ensure_cache()` — если кэш отсутствует или устарел, перезаписывает его атомарно;
  - `GET /futures` — читает CSV, фильтрует по `contract_type`, сортирует по `symbol`, пагинирует 1‑based.
- **`tests/test_service.py`** — юнит‑тесты без внешних вызовов: HTTP к Bybit мокается, проверяются кэш, сортировка, пагинация, фильтрация.

### Потокобезопасность и одновременные запросы
- Запись CSV идёт в **временный файл** и затем `rename` — это атомарно на уровне файловой системы, читатели видят либо старый, либо новый файл.
- Возможна конкурентная загрузка при первом обращении несколькими процессами: данные корректны, но можно оптимизировать mutex‑локом при необходимости (пока не требуется).

### Производительность
- Благодаря TTL существенно снижено количество походов в Bybit.
- Обработка (сортировка/пагинация) выполняется в памяти; этого достаточно, т.к. речь о сотнях–пара тысячах инструментов.
- Ограничение `page_size ≤ 1000` защищает от чрезмерной нагрузки и ошибок клиента.

---

## Зависимости

Перечень в `requirements.txt`:
```
fastapi
uvicorn[standard]
requests
pytest
pydantic-settings
PyYAML
```

---

## Запуск тестов

Из директории сервиса:
```bash
pytest -q
```

Тесты не ходят в интернет — сетевые вызовы замещаются моками.

---

## Интеграция с другими компонентами

Другие сервисы/модули могут ходить к этому API внутри общей сети/процесса:
- Запросить первую страницу: `GET /futures?page=1&page_size=100`;
- Дальнейшую пагинацию — пока `items` не опустеет;
- Если нужно **только фьючерсы** — использовать дефолт `contract_type=LinearFutures`; для перпетуалов — `LinearPerpetual`; для полной витрины — `all`.

Пример простого клиента на Python:
```python
import requests

url = "http://127.0.0.1:8000/futures"
params = {"page": 1, "page_size": 100, "contract_type": "LinearFutures"}
r = requests.get(url, params=params, timeout=10)
r.raise_for_status()
data = r.json()
print([x["symbol"] for x in data["items"]])
```

---

## Известные ограничения и планы улучшений

- Нет встроенных метрик/трассировки — при необходимости можно добавить Prometheus + middleware.
- Нет файловой блокировки при заполнении кэша — можно добавить `filelock`/`fasteners`.
- Логирование минимальное — можно внедрить structured logging и уровни.

---

## Контакты и поддержка

Если потребуется расширить выборку (фильтры, поиск по базовой/квотируемой монете) или вывести дополнительные поля из Bybit, это делается в `flatten_instrument()` и в схеме `Instrument`.


---

## Изменения (актуализация)
- Предел `page_size` строго до 1000. Если запрошено больше — автокэп до 1000.
- Фолбэк при сетевой ошибке: если локальный CSV существует, используется он; иначе 502.
- Новый параметр `minage_years` (опционально). Возвращаются только активы, чей возраст по `launchTime` не меньше указанного числа лет.
