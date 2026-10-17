"""
Application configuration.

All settings are loaded from environment variables (via .env file).
Never hardcode API keys or secrets in Python code.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
ENV_FILES = [str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env"), ".env"]

for ef in ENV_FILES:
    if Path(ef).is_file():
        load_dotenv(dotenv_path=ef)


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


    # --- Indian Language & LLM Models (Sarvam / HuggingFace / Local) ---
    sarvam_api_key: str = ""
    huggingface_api_token: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:latest"

    # --- Legacy / Optional ---
    assemblyai_api_key: str = ""

    # --- Application ---
    app_env: str = "development"
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # --- Paths (defaults set for local dev) ---
    knowledge_dir: str = "knowledge"


# Singleton instance — import this wherever config is needed.
settings = Settings()
