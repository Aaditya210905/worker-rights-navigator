"""Verify that the .env file is loaded and API keys are present."""

from dotenv import load_dotenv
import os

load_dotenv()

sarvam_key = os.getenv("SARVAM_API_KEY")
hf_token = os.getenv("HF_TOKEN")

print("Sarvam API key loaded:", bool(sarvam_key and sarvam_key != "your_key_here"))
print("HuggingFace token loaded:", bool(hf_token and hf_token != "hf_YOUR_TOKEN_HERE"))
