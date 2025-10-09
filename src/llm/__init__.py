# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Multi-provider LLM abstraction layer with schema-enforced JSON generation.

This package provides a unified interface for interacting with different LLM providers
(OpenAI, Claude) with two generation modes:
1. Free-form text generation
2. Schema-based JSON generation (strict schema compliance)

Supported Providers:
    OpenAI:
        - Uses Responses API with Structured Outputs (strict mode)
        - Guarantees output conforms to JSON schema at generation time
        - Requires models with structured output support (e.g., gpt-5)
        - All schemas must be OpenAI Strict Mode compliant

    Claude:
        - Uses prompt-based schema guidance
        - Validates output post-generation using jsonschema library
        - Includes full schema in system prompt for LLM guidance
        - Handles markdown code block extraction

Key Features:
    - Abstract base class (BaseLLMProvider) for provider implementations
    - Factory pattern (get_llm_provider) for easy provider instantiation
    - Automatic retry logic with exponential backoff for rate limits
    - Comprehensive error handling with custom exceptions
    - Logging for debugging and monitoring

Usage Examples:
    >>> # Using factory function with default provider
    >>> from src.llm import get_llm_provider
    >>> llm = get_llm_provider("openai")
    >>> text = llm.generate_text("Explain photosynthesis", system_prompt="You are a teacher")
    >>>
    >>> # Schema-based JSON generation
    >>> from src.schemas_loader import load_schema
    >>> schema = load_schema("interventional_trial")
    >>> result = llm.generate_json_with_schema(
    ...     prompt=pdf_text,
    ...     schema=schema,
    ...     system_prompt="Extract trial data"
    ... )
    >>>
    >>> # Using convenience functions
    >>> from src.llm import generate_text, generate_json_with_schema
    >>> text = generate_text("Hello", provider="claude")
    >>> data = generate_json_with_schema(prompt, schema, provider="openai")

Dependencies:
    - openai>=1.0 - OpenAI API client
    - anthropic>=0.25 - Anthropic Claude API client
    - tenacity>=8.0 - Retry logic with exponential backoff
    - jsonschema>=4.20 - JSON schema validation (required for Claude)

Note:
    API keys must be set via environment variables:
    - OPENAI_API_KEY for OpenAI
    - ANTHROPIC_API_KEY for Claude
"""

import logging
from typing import Any

from ..config import LLMProvider, LLMSettings, llm_settings
from .base import BaseLLMProvider, LLMError, LLMProviderError
from .claude_provider import ClaudeProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Public API exports
__all__ = [
    # Base classes and exceptions
    "BaseLLMProvider",
    "LLMError",
    "LLMProviderError",
    # Provider implementations
    "OpenAIProvider",
    "ClaudeProvider",
    # Factory function
    "get_llm_provider",
    # Convenience functions
    "generate_text",
    "generate_json_with_schema",
]


def get_llm_provider(
    provider: str | LLMProvider, settings: LLMSettings | None = None
) -> BaseLLMProvider:
    """
    Factory function to instantiate LLM provider.

    Uses factory pattern to create provider instances based on provider name
    or enum. Automatically loads settings from global configuration if not provided.

    Args:
        provider: Provider name ("openai" or "claude") or LLMProvider enum
        settings: Optional custom LLM settings (uses global llm_settings if None)

    Returns:
        Provider instance (OpenAIProvider or ClaudeProvider)

    Raises:
        LLMError: If provider is unsupported
        LLMProviderError: If provider initialization fails (e.g., missing API key)

    Example:
        >>> llm = get_llm_provider("openai")
        >>> text = llm.generate_text("Hello world")
        >>>
        >>> # With custom settings
        >>> from src.config import LLMSettings
        >>> custom_settings = LLMSettings(temperature=0.5)
        >>> llm = get_llm_provider("claude", settings=custom_settings)
    """
    if settings is None:
        settings = llm_settings

    if isinstance(provider, str):
        try:
            provider = LLMProvider(provider.lower())
        except ValueError as e:
            raise LLMError(
                f"Unsupported provider: {provider}. Supported: {[p.value for p in LLMProvider]}"
            ) from e

    if provider == LLMProvider.OPENAI:
        return OpenAIProvider(settings)
    elif provider == LLMProvider.CLAUDE:
        return ClaudeProvider(settings)
    else:
        raise LLMError(f"Unsupported provider: {provider}")


# Convenience functions for backward compatibility and easy usage
def generate_text(
    prompt: str,
    provider: str | LLMProvider = None,
    system_prompt: str | None = None,
    **kwargs,
) -> str:
    """
    Generate text using specified or default provider.

    Convenience function that wraps provider instantiation and generation
    in a single call. Uses default provider from settings if not specified.

    Args:
        prompt: User prompt/content to process
        provider: Provider to use (defaults to llm_settings.default_provider)
        system_prompt: Optional system prompt with instructions
        **kwargs: Provider-specific arguments

    Returns:
        Generated text response

    Raises:
        LLMError: If provider is invalid
        LLMProviderError: If generation fails

    Example:
        >>> text = generate_text("Explain photosynthesis", provider="openai")
        >>> text = generate_text("Hello", system_prompt="Friendly assistant")
    """
    if provider is None:
        provider = llm_settings.default_provider

    llm = get_llm_provider(provider)
    return llm.generate_text(prompt, system_prompt, **kwargs)


def generate_json_with_schema(
    prompt: str,
    schema: dict[str, Any],
    provider: str | LLMProvider = None,
    system_prompt: str | None = None,
    schema_name: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """
    Generate schema-conforming JSON using specified or default provider.

    Convenience function for schema-based JSON generation with guaranteed
    (OpenAI) or validated (Claude) schema compliance. Uses default provider
    from settings if not specified.

    Args:
        prompt: User prompt/content to process
        schema: JSON schema dictionary (Draft 2020-12 format)
        provider: Provider to use (defaults to llm_settings.default_provider)
        system_prompt: Optional system prompt with extraction instructions
        schema_name: Optional name for schema (used by OpenAI)
        **kwargs: Provider-specific arguments

    Returns:
        Dictionary conforming to provided schema

    Raises:
        LLMError: If provider is invalid
        LLMProviderError: If generation fails or schema validation fails

    Example:
        >>> from src.schemas_loader import load_schema
        >>> schema = load_schema("interventional_trial")
        >>> data = generate_json_with_schema(
        ...     prompt=pdf_text,
        ...     schema=schema,
        ...     provider="openai",
        ...     system_prompt="Extract trial data"
        ... )
    """
    if provider is None:
        provider = llm_settings.default_provider

    llm = get_llm_provider(provider)
    return llm.generate_json_with_schema(prompt, schema, system_prompt, schema_name, **kwargs)
