# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Base classes and exceptions for LLM provider abstraction layer.

This module defines the abstract base class and exceptions used by all LLM providers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Union

from ..config import LLMSettings


class LLMError(Exception):
    """Base exception for LLM-related errors"""

    pass


class LLMProviderError(LLMError):
    """Error with specific LLM provider"""

    pass


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Defines the interface that all LLM providers must implement. Each provider
    must support three generation modes: text, JSON, and schema-based JSON.

    Subclasses should:
    1. Call super().__init__(settings) to store settings
    2. Initialize provider-specific client (openai.OpenAI, anthropic.Anthropic, etc.)
    3. Implement all three abstract methods with retry logic
    4. Raise LLMProviderError for provider-specific errors

    Attributes:
        settings: LLM configuration (API keys, models, timeouts, etc.)
    """

    def __init__(self, settings: LLMSettings):
        """
        Initialize provider with settings.

        Args:
            settings: LLM configuration containing API keys, model names, etc.
        """
        self.settings = settings

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        """
        Generate free-form text response from prompt.

        Args:
            prompt: User prompt/content to process
            system_prompt: Optional system prompt with instructions
            **kwargs: Provider-specific arguments (temperature override, etc.)

        Returns:
            Generated text response

        Raises:
            LLMProviderError: If generation fails

        Example:
            >>> llm = get_llm_provider("openai")
            >>> text = llm.generate_text(
            ...     prompt="Explain photosynthesis",
            ...     system_prompt="You are a biology teacher"
            ... )
        """
        pass

    @abstractmethod
    def generate_json_with_schema(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
        schema_name: str | None = None,
        reasoning_effort: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate structured JSON response conforming to a specific JSON schema.

        Args:
            prompt: The user prompt/content to process
            schema: JSON schema dictionary defining the expected output structure
            system_prompt: Optional system prompt for additional instructions
            schema_name: Optional name for the schema (used by some providers)
            reasoning_effort: Optional reasoning effort level ("low", "medium", "high") for GPT-5.1+ (ignored by Claude)
            **kwargs: Additional provider-specific arguments

        Returns:
            Dictionary conforming to the provided schema

        Raises:
            LLMProviderError: If generation or schema validation fails
        """
        pass

    @abstractmethod
    def generate_json_with_pdf(
        self,
        pdf_path: Union["Path", str],
        schema: dict[str, Any],
        system_prompt: str | None = None,
        max_pages: int | None = None,
        schema_name: str | None = None,
        reasoning_effort: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate structured JSON from PDF file using vision capabilities.

        Uploads PDF to LLM with vision support to extract structured data including
        tables, images, charts, and text. This method preserves document structure
        that would be lost with text-only extraction.

        Both OpenAI and Claude convert PDF pages to images internally and analyze
        both textual and visual content. This is critical for medical research papers
        where tables, figures, and charts contain essential data.

        Args:
            pdf_path: Path to PDF file (str or Path object)
            schema: JSON schema dictionary defining expected output structure
            system_prompt: Optional system prompt with extraction instructions
            max_pages: Optional limit on pages to process (max 100 per API limits)
            schema_name: Optional name for schema (used by some providers)
            reasoning_effort: Optional reasoning effort level ("low", "medium", "high") for GPT-5.1+ (ignored by Claude)
            **kwargs: Additional provider-specific arguments

        Returns:
            Dictionary conforming to the provided schema, extracted from PDF

        Raises:
            LLMProviderError: If PDF upload fails, file too large, or extraction fails
            LLMProviderError: If PDF exceeds API limits (100 pages, 32 MB)

        Note:
            Cost: ~1,500-3,000 tokens per page (3-6x more than text extraction)
            Worth it for complete data including tables and figures.

        Example:
            >>> from pathlib import Path
            >>> from src.schemas_loader import load_schema
            >>> schema = load_schema("interventional_trial")
            >>> llm = get_llm_provider("openai")
            >>> data = llm.generate_json_with_pdf(
            ...     pdf_path=Path("paper.pdf"),
            ...     schema=schema,
            ...     system_prompt="Extract clinical trial data",
            ...     max_pages=20
            ... )
            >>> # data includes tables, figures, complete extraction
        """
        pass
