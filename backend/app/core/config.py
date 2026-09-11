from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "Education OS"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str
    OWNER_DATABASE_URL: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
