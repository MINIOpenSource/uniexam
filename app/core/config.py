from pydantic_settings import BaseSettings
from pydantic import Field
import os
from pathlib import Path

class Settings(BaseSettings):
    APP_NAME: str = "Online Exam System"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "insecure-secret-key-replace-in-production"))

    # Database
    DATA_DIR: Path = Path(__file__).resolve().parent.parent.parent / "data"
    SQLITE_DB_PATH: str = Field(default_factory=lambda: os.getenv("SQLITE_DB_PATH", "sqlite+aiosqlite:///./data/exam.db"))

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    ADMIN_USER_DEFAULT_PASSWORD: str = "admin"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = {
        "env_file": ".env",
        "case_sensitive": True
    }

    def get_database_url(self) -> str:
        # Ensure data directory exists
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return self.SQLITE_DB_PATH

settings = Settings()
