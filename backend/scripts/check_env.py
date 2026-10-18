"""Verify that the .env file is loaded and API keys are present."""

from dotenv import load_dotenv
import os

load_dotenv()

sarvam_key = os.getenv("SARVAM_API_KEY")
llm_key = os.getenv("LLM_API_KEY")
embed_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY")

print("Sarvam API key loaded    :", bool(sarvam_key and sarvam_key != "your_key_here"))
print("LLM API key loaded       :", bool(llm_key and not llm_key.startswith("<")))
print("Embedding API key loaded :", bool(embed_key and not embed_key.startswith("<")))
