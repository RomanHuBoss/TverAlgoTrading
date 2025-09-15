"""
Настройки сервиса (pydantic-settings v2).
Источники (приоритет): env/.env  >  config.yaml  >  defaults.
"""

from pathlib import Path
from typing import Any, Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- параметры сервиса ---
    CSV_PATH: Path = Path("bybit_linear_futures.csv")
    CACHE_TTL_SEC: int = 3600
    BYBIT_BASE_URL: str = "https://api.bybit.com"
    REQUEST_TIMEOUT_SEC: int = 15
    MAX_RETRIES: int = 3
    PAGE_SIZE_DEFAULT: int = 50

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """
        Порядок источников:
          1) init_settings      (значения, переданные в конструктор)
          2) env_settings       (переменные окружения)
          3) dotenv_settings    (.env)
          4) YAML-файл config.yaml (наш кастомный источник)
          5) file_secret_settings
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            cls.yaml_config_settings,   # <— нулевого арности callable
            file_secret_settings,
        )

    @staticmethod
    def yaml_config_settings() -> Dict[str, Any]:
        """
        Кастомный источник настроек из config.yaml.
        ДОЛЖЕН быть вызываемым без аргументов и возвращать dict.
        """
        import yaml

        path = Path("config.yaml")
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data


# Глобальный объект настроек
settings = Settings()
