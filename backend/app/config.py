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


    # --- Sarvam AI (voice: STT + TTS) ---
    sarvam_api_key: str = ""

    # --- LLM for agent reasoning (OpenAI-compatible endpoint) ---
    # Default: Groq — fastest free-tier option for Indian language tasks
    # Override in .env to use OpenAI, Ollama, or any other provider
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.1-8b-instant"

    # --- HuggingFace (for Qwen3 embeddings only) ---
    huggingface_api_token: str = ""

    # --- Application ---
    app_env: str = "development"
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # --- Embedding settings (OpenAI-compatible / OpenRouter) ---
    embedding_backend: str = "openai"
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str = ""
    embedding_model: str = "nvidia/nemotron-3-embed-1b:free"

    # --- Paths (defaults set for local dev) ---
    knowledge_dir: str = "knowledge"


# Singleton instance — import this wherever config is needed.
settings = Settings()
