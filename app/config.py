import os
from typing import Optional
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Support both relative and absolute path resolution to .env
env_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", env_file_path) if os.path.exists(env_file_path) else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required string variables without defaults (fails fast on startup if missing)
    DATABASE_URL: str
    SECRET_KEY: str = Field(validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET_KEY"))
    EMAIL_ALEGRA: str
    APIKEY_ALEGRA: str
    URL_API_ALEGRA: str
    GOOGLE_CLOUD_PROJECT: str

    # Fields with safe defaults or optional coercion
    ENVIRONMENT: str = "development"
    SECURE_COOKIES: bool = True
    ALGORITHM: str = Field("HS256", validation_alias=AliasChoices("ALGORITHM", "JWT_ALGORITHM"))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    READONLY_DATABASE_URL: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: str = "us-central1"

    @model_validator(mode="after")
    def resolve_cookie_security(self) -> "Settings":
        # In local development environments without an explicit SECURE_COOKIES override,
        # set to False to permit auth cookies over local HTTP.
        if "SECURE_COOKIES" not in self.model_fields_set:
            if self.ENVIRONMENT.lower() in ("development", "local", "dev", "test"):
                self.SECURE_COOKIES = False
        return self

    @property
    def effective_readonly_db_url(self) -> str:
        """Returns READONLY_DATABASE_URL if configured, otherwise falls back to DATABASE_URL."""
        return self.READONLY_DATABASE_URL or self.DATABASE_URL


settings = Settings()
