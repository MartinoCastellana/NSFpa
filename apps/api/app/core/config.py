from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    public_api_base_url: str = "http://localhost:8000/api/v1"
    frontend_origin: str = "http://localhost:5173"
    database_url: str = "sqlite+aiosqlite:///./privacy_ocr_dev.db"
    redis_url: str = "redis://redis:6379/0"
    storage_root: Path = Path("private_documents")
    max_upload_mb: int = 25
    max_pages: int = 150
    max_raster_pixels: int = 40_000_000
    ocr_engine: str = "tesseract"
    ocr_languages: str = "ita+eng"
    ocr_dpi: int = 200
    ner_min_confidence: float = 0.80
    ocr_min_confidence: float = 0.70
    require_manual_approval: bool = True
    fail_closed: bool = True
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60
    openai_max_output_tokens: int = 2500
    openai_mode: str = "mock"
    data_encryption_key: str = "dev-only-change-me"
    jwt_issuer: str = "nsfpa-dev"
    jwt_audience: str = "nsfpa"
    oidc_jwks_url: str = ""
    retention_days: int = 30
    log_level: str = "INFO"
    minicpm_ocr_enabled: bool = False
    minicpm_ocr_command: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_origin.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    return settings
