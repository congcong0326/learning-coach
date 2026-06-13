from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "learning-coach-backend"
    environment: str = "local"
    api_prefix: str = "/api"
    database_url: str = (
        "postgresql+asyncpg://learning_coach:learning_coach"
        "@localhost:5432/learning_coach"
    )
    session_cookie_name: str = "learning_coach_session"
    session_ttl_hours: int = 24 * 14
    session_cookie_secure: bool = False
    problem_seed_path: Path = Path("data/seed")
    seed_problems_on_startup: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
