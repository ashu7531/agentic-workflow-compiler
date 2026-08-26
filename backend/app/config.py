"""App configuration. GEMINI_API_KEY is optional — without it the app runs in a
deterministic MOCK compiler mode so you can develop/demo before adding a key.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    # CORS origins for the frontend (comma-separated). "*" for local dev.
    CORS_ORIGINS: str = "*"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def has_llm(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # allow env var to win even if a stale .env exists
    s = Settings()
    if not s.GEMINI_API_KEY:
        s.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    return s
