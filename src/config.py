# config.py

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4.1")
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))


settings = Settings()
