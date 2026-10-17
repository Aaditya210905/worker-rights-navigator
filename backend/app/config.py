"""
Application configuration.

All settings are loaded from environment variables (via .env file).
Never hardcode API keys or secrets in Python code.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- AssemblyAI ---
    assemblyai_api_key: str = ""

    # --- Application ---
    app_env: str = "development"
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # --- Paths (defaults set for local dev) ---
    knowledge_dir: str = "knowledge"


# Singleton instance — import this wherever config is needed.
settings = Settings()
