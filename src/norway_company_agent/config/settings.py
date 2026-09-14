from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    openrouter_api_key: str
    easyproxy_api_key: str | None = None
    easyproxy_endpoint: str | None = None
    signalpost_db_path: str = "./db/signalpost.db"
    signalpost_output_dir: str = "./out/"
    signalpost_log_level: str = "INFO"
    signalpost_run_id: str | None = None

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
