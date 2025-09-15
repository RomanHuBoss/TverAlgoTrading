import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    bybit_base_url: str = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
    request_timeout_sec: int = int(os.getenv("REQUEST_TIMEOUT_SEC", "10"))
    max_bars_per_request: int = int(os.getenv("MAX_BARS_PER_REQUEST", "1000"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data")).resolve()
    cache_dir: Path = Path(os.getenv("CACHE_DIR", "./cache")).resolve()
    enable_cache: bool = os.getenv("ENABLE_CACHE", "true").lower() != "false"
    bybit_qps: float = float(os.getenv("BYBIT_QPS", "5"))
    bybit_max_retries: int = int(os.getenv("BYBIT_MAX_RETRIES", "3"))
    bybit_retry_backoff_sec: float = float(os.getenv("BYBIT_RETRY_BACKOFF_SEC", "0.5"))

def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    return s
