from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/radar.db"
    app_timezone: str = "Asia/Kolkata"
    admin_secret: str = "change-me"
    github_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "VoiceERADeveloperRadar/0.1"
    forem_api_key: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    daily_schedule: str = "09:00"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def ensure_data_dir(self) -> None:
        if self.database_url.startswith("sqlite:///./"):
            Path(self.database_url.removeprefix("sqlite:///./")).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

