"""Verify that the .env file is loaded and the API key is present."""

from dotenv import load_dotenv
import os

load_dotenv()

key = os.getenv("ASSEMBLYAI_API_KEY")

print("API key loaded:", bool(key and key != "your_key_here"))
