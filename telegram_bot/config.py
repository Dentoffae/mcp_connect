"""
Configuration — reads all secrets from the .env file in the project root.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from telegram_bot/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"[config] '{key}' is not set. "
            f"Add it to {_env_path} and restart the bot."
        )
    return value


TELEGRAM_TOKEN:  str = _require("TELEGRAM_TOKEN")
OPENAI_API_KEY:  str = _require("OPENAI_API_KEY")

MCP_SERVER_URL:  str = os.getenv("MCP_SERVER_URL",  "http://localhost:8000")
OPENAI_MODEL:    str = os.getenv("OPENAI_MODEL",    "gpt-4o-mini")
