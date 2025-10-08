# config.py
"""
Configuration settings for LLM providers in the PDFtoPodcast extraction pipeline.

Supports multiple LLM providers (OpenAI and Anthropic Claude) with configuration
via environment variables. Load settings from a .env file or set environment
variables directly.

Environment Variables:
    # Provider Selection
    LLM_PROVIDER: Default provider (openai or claude)

    # OpenAI Configuration
    OPENAI_API_KEY: OpenAI API key
    OPENAI_MODEL: Model name (default: gpt-4o, supports structured outputs)
    OPENAI_MAX_TOKENS: Maximum output tokens (default: 4096)

    # Anthropic Configuration
    ANTHROPIC_API_KEY: Anthropic API key
    ANTHROPIC_MODEL: Model name (default: claude-3-5-sonnet-20241022)
    ANTHROPIC_MAX_TOKENS: Maximum output tokens (default: 4096)

    # General Settings
    LLM_TEMPERATURE: Temperature for generation (default: 0.0 for deterministic)
    LLM_TIMEOUT: Request timeout in seconds (default: 120)

    # PDF Processing Limits (API Constraints)
    MAX_PDF_PAGES: Maximum pages to process from PDF (default: 100, API limit)
    MAX_PDF_SIZE_MB: Maximum PDF file size in MB (default: 32, API limit)

Example .env file:
    OPENAI_API_KEY=sk-...
    OPENAI_MODEL=gpt-4o
    ANTHROPIC_API_KEY=sk-ant-...
    LLM_TEMPERATURE=0.0
    LLM_TIMEOUT=120

Usage:
    >>> from src.config import llm_settings
    >>> llm_settings.openai_model
    'gpt-4o'
"""

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class LLMProvider(Enum):
    """
    Supported LLM providers for data extraction.

    Providers:
        OPENAI: OpenAI GPT models (supports native structured outputs)
        CLAUDE: Anthropic Claude models (uses prompt-based structured outputs)
    """

    OPENAI = "openai"
    CLAUDE = "claude"


@dataclass(frozen=True)
class LLMSettings:
    """
    Configuration for LLM providers.

    All settings can be overridden via environment variables.
    Default provider is OpenAI. Both providers support JSON extraction,
    but OpenAI has native structured outputs for guaranteed schema compliance.

    Attributes:
        default_provider: Which LLM provider to use by default
        openai_api_key: OpenAI API key from OPENAI_API_KEY env var
        openai_model: Model name (default: gpt-4o, supports structured outputs)
        openai_max_tokens: Max output tokens for OpenAI (default: 4096)
        anthropic_api_key: Anthropic API key from ANTHROPIC_API_KEY env var
        anthropic_model: Claude model name (default: claude-3-5-sonnet-20241022)
        anthropic_max_tokens: Max output tokens for Claude (default: 4096)
        temperature: Sampling temperature, 0.0 = deterministic (default: 0.0)
        timeout: Request timeout in seconds (default: 120 for long extractions)
        max_pdf_pages: Maximum pages to process from PDF (default: 100, API limit)
        max_pdf_size_mb: Maximum PDF file size in MB (default: 32, API limit)
    """

    # Default provider
    default_provider: LLMProvider = LLMProvider.OPENAI

    # OpenAI configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")  # gpt-4o supports structured outputs
    openai_max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "4096"))

    # Anthropic Claude configuration
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    anthropic_max_tokens: int = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))

    # General settings
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))  # 0.0 = deterministic
    timeout: int = int(os.getenv("LLM_TIMEOUT", "600"))  # 10 minutes for long extractions

    # PDF processing limits (API constraints for direct PDF upload)
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "100"))  # 100 page limit (OpenAI + Claude)
    max_pdf_size_mb: int = int(os.getenv("MAX_PDF_SIZE_MB", "10"))  # 32 MB limit (OpenAI + Claude)


@dataclass(frozen=True)
class Settings:
    """
    Legacy settings for backward compatibility.

    DEPRECATED: Use LLMSettings instead for multi-provider support.
    This class only supports OpenAI and is maintained for backward compatibility.
    """

    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o")  # Updated from gpt-4.1 to valid model
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))


# Global settings instances
llm_settings = LLMSettings()
settings = Settings()  # DEPRECATED: Use llm_settings instead
