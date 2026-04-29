from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://mse:mse@localhost:5432/mse_viewer"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "dev"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()
