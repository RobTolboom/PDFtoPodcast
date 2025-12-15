# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

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
    OPENAI_MODEL: Model name (default: gpt-5.1, supports structured outputs + reasoning)
    OPENAI_MAX_TOKENS: Maximum output tokens (default: 128000)

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
    OPENAI_MODEL=gpt-5.1
    REASONING_EFFORT_EXTRACTION=high
    REASONING_EFFORT_APPRAISAL=high
    ANTHROPIC_API_KEY=sk-ant-...
    LLM_TEMPERATURE=0.0
    LLM_TIMEOUT=120

Usage:
    >>> from src.config import llm_settings
    >>> llm_settings.openai_model
    'gpt-5.1'
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
        openai_model: Model name (default: gpt-5.1, supports structured outputs + reasoning)
        openai_max_tokens: Max output tokens for OpenAI (default: 128000)
        reasoning_effort_classification: Reasoning effort for classification (low/medium/high, default: low)
        reasoning_effort_extraction: Reasoning effort for extraction (low/medium/high, default: high)
        reasoning_effort_validation: Reasoning effort for validation (low/medium/high, default: medium)
        reasoning_effort_correction: Reasoning effort for correction (low/medium/high, default: medium)
        reasoning_effort_appraisal: Reasoning effort for appraisal (low/medium/high, default: high)
        reasoning_effort_report: Reasoning effort for report generation (low/medium/high, default: medium)
        reasoning_effort_podcast: Reasoning effort for podcast generation (low/medium/high, default: medium)
        anthropic_api_key: Anthropic API key from ANTHROPIC_API_KEY env var
        anthropic_model: Claude model name (default: claude-3-5-sonnet-20241022)
        anthropic_max_tokens: Max output tokens for Claude (default: 4096)
        temperature: Sampling temperature, 0.0 = deterministic (default: 0.0)
        timeout: Request timeout in seconds (default: 1800 = 30 minutes for long extractions)
        max_pdf_pages: Maximum pages to process from PDF (default: 100, API limit)
        max_pdf_size_mb: Maximum PDF file size in MB (default: 10, provider max: 32)
    """

    # Default provider
    default_provider: LLMProvider = LLMProvider.OPENAI

    # OpenAI configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv(
        "OPENAI_MODEL", "gpt-5.1"
    )  # gpt-5.1 supports structured outputs + reasoning
    # Set very high default (128K context window for gpt-5.1)
    # Actual output limit depends on model (typically 4K-16K for completion)
    # OpenAI API will enforce model-specific limits automatically
    openai_max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "128000"))

    # Reasoning effort per pipeline step (low/medium/high)
    # Higher effort = more thinking tokens, better quality, higher cost/latency
    reasoning_effort_classification: str = os.getenv("REASONING_EFFORT_CLASSIFICATION", "low")
    reasoning_effort_extraction: str = os.getenv("REASONING_EFFORT_EXTRACTION", "high")
    reasoning_effort_validation: str = os.getenv("REASONING_EFFORT_VALIDATION", "medium")
    reasoning_effort_correction: str = os.getenv("REASONING_EFFORT_CORRECTION", "medium")
    reasoning_effort_appraisal: str = os.getenv("REASONING_EFFORT_APPRAISAL", "high")
    reasoning_effort_report: str = os.getenv("REASONING_EFFORT_REPORT", "medium")
    reasoning_effort_podcast: str = os.getenv("REASONING_EFFORT_PODCAST", "medium")

    # Anthropic Claude configuration
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    anthropic_max_tokens: int = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))

    # General settings
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))  # 0.0 = deterministic
    timeout: int = int(os.getenv("LLM_TIMEOUT", "1800"))  # 30 minutes for long extractions

    # PDF processing limits (API constraints for direct PDF upload)
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "100"))  # 100 page limit (OpenAI + Claude)
    max_pdf_size_mb: int = int(
        os.getenv("MAX_PDF_SIZE_MB", "10")
    )  # Default 10 MB, max 32 MB (provider limit)


@dataclass(frozen=True)
class Settings:
    """
    Legacy settings for backward compatibility.

    DEPRECATED: Use LLMSettings instead for multi-provider support.
    This class only supports OpenAI and is maintained for backward compatibility.
    """

    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("OPENAI_MODEL", "gpt-5.1")  # Updated from gpt-4.1 to valid model
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))


# Global settings instances
llm_settings = LLMSettings()
settings = Settings()  # DEPRECATED: Use llm_settings instead
