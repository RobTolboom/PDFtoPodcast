# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Anthropic Claude API provider implementation.

This module implements the Claude provider with prompt-based schema guidance.
Unlike OpenAI, Claude doesn't have native structured outputs, so schemas are
included in system prompts and validated post-generation using jsonschema.

Key Features:
    - Free-form text generation via messages API
    - JSON mode via prompt instructions
    - Schema-based generation via prompt guidance + post-validation
    - PDF processing with vision capabilities
    - Markdown code block extraction
    - Automatic retry logic with exponential backoff

Supported Models:
    - claude-3-opus
    - claude-3-sonnet
    - claude-3-haiku
    - claude-3.5-sonnet (latest)

Note:
    Requires ANTHROPIC_API_KEY environment variable.
    Requires jsonschema library for schema validation.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import LLMSettings
from .base import BaseLLMProvider, LLMProviderError

logger = logging.getLogger(__name__)

# Check jsonschema availability
try:
    import jsonschema

    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False
    logger.warning(
        "jsonschema library not available. Schema validation will be disabled. "
        "Install with: pip install jsonschema"
    )


def _extract_json_from_markdown(content: str) -> str:
    """
    Extract JSON content from markdown code blocks.

    Handles Claude responses that wrap JSON in markdown code blocks like:
    ```json
    {...}
    ```

    Args:
        content: Raw response content from LLM

    Returns:
        Extracted JSON string (unwrapped if it was in code blocks)

    Example:
        >>> _extract_json_from_markdown('```json\\n{"key": "value"}\\n```')
        '{"key": "value"}'
        >>> _extract_json_from_markdown('{"key": "value"}')
        '{"key": "value"}'
    """
    content = content.strip()

    # Check for ```json opening
    if content.startswith("```json"):
        # Find closing ```
        if content.endswith("```"):
            # Extract content between ```json and ```
            return content[7:-3].strip()  # len("```json") = 7, len("```") = 3
        else:
            # Malformed: has opening but no closing
            logger.warning("Malformed markdown: found ```json but no closing ```")
            return content[7:].strip()

    # Check for generic ``` opening
    elif content.startswith("```"):
        if content.endswith("```"):
            return content[3:-3].strip()
        else:
            logger.warning("Malformed markdown: found ``` but no closing ```")
            return content[3:].strip()

    # Not wrapped in code blocks
    return content


class ClaudeProvider(BaseLLMProvider):
    """
    Anthropic Claude API provider implementation with prompt-based schema guidance.

    This provider uses Claude's messages API with:
    - Free-form text generation
    - JSON mode via prompt instructions
    - Schema-based generation via prompt guidance + post-validation

    Unlike OpenAI, Claude doesn't have native structured outputs, so schemas
    are included in system prompts and validated after generation using the
    jsonschema library.

    Supported models: claude-3-opus, claude-3-sonnet, claude-3-haiku, etc.

    Attributes:
        client: Anthropic client instance
        settings: LLM configuration

    Note:
        Requires ANTHROPIC_API_KEY environment variable to be set.
        Requires jsonschema library for schema validation.
    """

    def __init__(self, settings: LLMSettings):
        """
        Initialize Claude provider.

        Args:
            settings: LLM configuration containing API key and model settings

        Raises:
            LLMProviderError: If ANTHROPIC_API_KEY is not set or jsonschema unavailable
        """
        super().__init__(settings)
        if not settings.anthropic_api_key:
            raise LLMProviderError("Anthropic API key not found in environment variables")

        if not HAVE_JSONSCHEMA:
            logger.warning(
                "jsonschema library not available. Schema validation will be disabled. "
                "Install with: pip install jsonschema"
            )

        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.timeout
        )
        logger.info(f"Initialized Claude provider with model: {settings.anthropic_model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
    )
    def generate_text(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        """Generate text using Claude API"""
        try:
            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=self.settings.anthropic_max_tokens,
                temperature=self.settings.temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )

            result = response.content[0].text.strip()
            logger.info("Successfully generated text with Claude")
            return result

        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error: {e}")
            raise LLMProviderError(f"Claude API error: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
    )
    def generate_json_with_schema(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
        schema_name: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate structured JSON using Claude API with schema guidance.

        Note: Claude doesn't have native structured outputs like OpenAI,
        so we include schema information in the prompt and validate post-generation.
        """
        try:
            # Include schema information in system prompt
            schema_instruction = (
                f"\n\nYou must return a JSON object that conforms to this JSON schema:\n"
                f"{json.dumps(schema, indent=2)}\n\n"
                f"CRITICAL: Follow the schema exactly. Include all required fields. "
                f"Return ONLY valid JSON, no markdown or explanations."
            )
            full_system_prompt = (system_prompt or "") + schema_instruction

            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=self.settings.anthropic_max_tokens,
                temperature=self.settings.temperature,
                system=full_system_prompt,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )

            content = response.content[0].text.strip()

            # Extract JSON from markdown code blocks if present
            content = _extract_json_from_markdown(content)

            result = json.loads(content)

            # Validate against schema using jsonschema library
            if HAVE_JSONSCHEMA:
                try:
                    jsonschema.validate(result, schema)
                    logger.info(
                        "Successfully generated and validated schema-conforming JSON with Claude"
                    )
                except jsonschema.ValidationError as e:
                    logger.error(f"Schema validation failed: {e.message}")
                    raise LLMProviderError(
                        f"Generated JSON does not conform to schema: {e.message}"
                    ) from e
            else:
                logger.warning(
                    "jsonschema library not available - skipping schema validation. "
                    "Schema guidance was provided to LLM but compliance is not guaranteed."
                )

            return result

        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error with schema-based generation: {e}")
            raise LLMProviderError(f"Claude schema-based generation failed: {e}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            # Truncate long responses to avoid logging sensitive data
            content_preview = content[:200] + "..." if len(content) > 200 else content
            logger.error(f"Raw response preview: {content_preview}")
            raise LLMProviderError(f"Invalid JSON response: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
    )
    def generate_json_with_pdf(
        self,
        pdf_path: Path | str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
        max_pages: int | None = None,
        schema_name: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate structured JSON from PDF using Claude API with vision capabilities.

        Uses Claude's PDF processing to analyze documents including tables, images,
        and charts. PDF is base64-encoded and sent directly in the message.
        """
        try:
            # Normalize to Path object
            pdf_path = Path(pdf_path)

            if not pdf_path.exists():
                raise LLMProviderError(f"PDF file not found: {pdf_path}")

            # Check file size (32 MB limit)
            file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 32:
                raise LLMProviderError(f"PDF file too large: {file_size_mb:.1f} MB (max 32 MB)")

            # Read and encode PDF as base64
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = base64.b64encode(pdf_file.read()).decode("utf-8")

            logger.info(f"Uploading PDF to Claude: {pdf_path.name} ({file_size_mb:.1f} MB)")

            # Include schema information in system prompt
            schema_instruction = (
                f"\n\nYou must return a JSON object that conforms to this JSON schema:\n"
                f"{json.dumps(schema, indent=2)}\n\n"
                f"CRITICAL: Follow the schema exactly. Include all required fields. "
                f"Return ONLY valid JSON, no markdown or explanations."
            )
            full_system_prompt = (system_prompt or "") + schema_instruction

            # Add page limit instruction if specified
            if max_pages:
                full_system_prompt += f"\n\nProcess only the first {max_pages} pages of the PDF."

            # Create message with PDF document
            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=self.settings.anthropic_max_tokens,
                temperature=self.settings.temperature,
                system=full_system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Extract structured data from this PDF document according to the schema.",
                            },
                        ],
                    }
                ],
                **kwargs,
            )

            content = response.content[0].text.strip()

            # Extract JSON from markdown code blocks if present
            content = _extract_json_from_markdown(content)

            result = json.loads(content)

            # Validate against schema using jsonschema library
            if HAVE_JSONSCHEMA:
                try:
                    jsonschema.validate(result, schema)
                    logger.info(
                        "Successfully extracted and validated schema-conforming JSON from PDF with Claude"
                    )
                except jsonschema.ValidationError as e:
                    logger.error(f"Schema validation failed: {e.message}")
                    raise LLMProviderError(
                        f"Generated JSON does not conform to schema: {e.message}"
                    ) from e
            else:
                logger.warning(
                    "jsonschema library not available - skipping schema validation. "
                    "Schema guidance was provided to LLM but compliance is not guaranteed."
                )

            return result

        except FileNotFoundError as e:
            logger.error(f"PDF file not found: {pdf_path}")
            raise LLMProviderError(f"PDF file not found: {e}") from e
        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error with PDF upload: {e}")
            raise LLMProviderError(f"Claude PDF processing failed: {e}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            # Truncate long responses to avoid logging sensitive data
            content_preview = content[:200] + "..." if len(content) > 200 else content
            logger.error(f"Raw response preview: {content_preview}")
            raise LLMProviderError(f"Invalid JSON response: {e}") from e
