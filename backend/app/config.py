from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str
    test_database_url: str | None = None
    jwt_secret: str
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    cookie_secure: bool = False
    max_upload_mb: int = 10
    storage_dir: Path = Path("./storage")
    cors_origins: str = ""
    log_level: str = "INFO"
    seed_submitter_password: str
    seed_reviewer_password: str


settings = Settings()
