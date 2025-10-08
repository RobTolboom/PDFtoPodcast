# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

# llm.py
"""
Multi-provider LLM abstraction layer with schema-enforced JSON generation.

This module provides a unified interface for interacting with different LLM providers
(OpenAI, Claude) with two generation modes:
1. Free-form text generation
2. Schema-based JSON generation (strict schema compliance)

Supported Providers:
    OpenAI:
        - Uses Responses API with Structured Outputs (strict mode)
        - Guarantees output conforms to JSON schema at generation time
        - Requires models with structured output support (e.g., gpt-4o, gpt-5)
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
    >>> from src.llm import generate_text, generate_json
    >>> text = generate_text("Hello", provider="claude")
    >>> data = generate_json("Return user data as JSON", provider="openai")

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

import base64
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

import anthropic
import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import LLMProvider, LLMSettings, llm_settings

logger = logging.getLogger(__name__)

# Check jsonschema availability for Claude provider
try:
    import jsonschema

    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False
    logger.warning(
        "jsonschema library not available. Claude schema validation will be disabled. "
        "Install with: pip install jsonschema"
    )


class LLMError(Exception):
    """Base exception for LLM-related errors"""

    pass


class LLMProviderError(LLMError):
    """Error with specific LLM provider"""

    pass


def _repair_json_quotes(json_str: str) -> str:
    """
    Attempt to repair JSON with unescaped quotes in string values.

    This is a workaround for OpenAI Responses API bug where strict mode
    doesn't properly escape quotes within string values.

    Strategy:
    - Find patterns like: "key": "value with "unescaped" quotes"
    - Escape the internal quotes: "key": "value with \"unescaped\" quotes"

    Args:
        json_str: Malformed JSON string with unescaped quotes

    Returns:
        Repaired JSON string (best effort)

    Warning:
        This is heuristic-based and may not work for all cases.
        It's a workaround for API bugs, not a robust solution.
    """
    import re

    # Pattern to find string values that contain unescaped quotes
    # Match: "key": "value with potential "quote" inside"
    # This is simplified and won't catch all cases, but handles common ones

    def escape_quotes_in_match(match):
        """Escape quotes within a JSON string value"""
        key_part = match.group(1)  # Everything before the value
        value_part = match.group(2)  # The string value content

        # Escape any unescaped quotes in the value
        # Already escaped quotes (\") should remain as-is
        escaped_value = value_part.replace(r"\"", "\x00")  # Protect already escaped
        escaped_value = escaped_value.replace('"', r"\"")  # Escape unescaped quotes
        escaped_value = escaped_value.replace("\x00", r"\"")  # Restore protected

        return f'{key_part}"{escaped_value}"'

    # Pattern: "key": "value content that might have "quotes""
    # This matches from the key to the end quote, capturing the value
    pattern = r'("(?:[^"\\]|\\.)*"\s*:\s*)"([^"]*(?:"[^"]*)*)"'

    try:
        repaired = re.sub(pattern, escape_quotes_in_match, json_str)
        logger.info("JSON repair attempt completed")
        return repaired
    except Exception as e:
        logger.warning(f"JSON repair failed: {e}, returning original")
        return json_str


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
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
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
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        schema_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response conforming to a specific JSON schema.

        Args:
            prompt: The user prompt/content to process
            schema: JSON schema dictionary defining the expected output structure
            system_prompt: Optional system prompt for additional instructions
            schema_name: Optional name for the schema (used by some providers)
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
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        max_pages: Optional[int] = None,
        schema_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
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


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI API provider implementation with native Structured Outputs support.

    This provider uses OpenAI's Responses API with support for:
    - Free-form text generation
    - Structured Outputs with JSON Schema (strict mode)

    The Structured Outputs feature guarantees that generated JSON conforms
    to the provided schema at generation time, eliminating the need for
    post-generation validation.

    Supported models: gpt-4o, gpt-4o-mini, and other models with structured output support

    Attributes:
        client: OpenAI client instance
        settings: LLM configuration

    Note:
        Requires OPENAI_API_KEY environment variable to be set.
    """

    def __init__(self, settings: LLMSettings):
        """
        Initialize OpenAI provider.

        Args:
            settings: LLM configuration containing API key and model settings

        Raises:
            LLMProviderError: If OPENAI_API_KEY is not set in environment
        """
        super().__init__(settings)
        if not settings.openai_api_key:
            raise LLMProviderError("OpenAI API key not found in environment variables")

        self.client = openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.timeout)
        logger.info(f"Initialized OpenAI provider with model: {settings.openai_model}")

    def _parse_response_output(self, response) -> Dict[str, Any]:
        """
        Extract and parse JSON from OpenAI Responses API response.

        Handles extraction from response.output_text with fallback to manual
        extraction from response.output array structure. Includes extensive
        debug logging for troubleshooting response parsing issues.

        Args:
            response: OpenAI Responses API response object

        Returns:
            Parsed JSON dictionary

        Raises:
            LLMProviderError: If no text output found or JSON parsing fails
        """
        # Log response structure for debugging
        logger.info(f"Response status: {response.status if hasattr(response, 'status') else 'N/A'}")
        logger.info(f"Response output type: {type(response.output)}")
        logger.info(
            f"Response output length: {len(response.output) if hasattr(response, 'output') else 'N/A'}"
        )

        # Log token usage if available
        if hasattr(response, "usage"):
            usage = response.usage
            logger.info("=== TOKEN USAGE ===")
            logger.info(f"  Input tokens: {getattr(usage, 'input_tokens', 'N/A')}")
            logger.info(f"  Output tokens: {getattr(usage, 'output_tokens', 'N/A')}")
            logger.info(f"  Total tokens: {getattr(usage, 'total_tokens', 'N/A')}")

            # Check for completion token details (reasoning tokens for GPT-5/o-series)
            if hasattr(usage, "completion_tokens_details"):
                details = usage.completion_tokens_details
                logger.info(f"  Reasoning tokens: {getattr(details, 'reasoning_tokens', 'N/A')}")
                logger.info(
                    f"  Accepted prediction tokens: {getattr(details, 'accepted_prediction_tokens', 'N/A')}"
                )
            logger.info("===================")
        else:
            logger.warning("No usage information available in response")

        # Try convenience property first
        content = None
        if hasattr(response, "output_text") and response.output_text:
            content = response.output_text
            logger.info(f"✓ Using response.output_text ({len(content)} chars)")
            logger.info(f"Preview: {content[:200]}")

        # Fallback: extract from output array structure
        if not content:
            logger.warning("output_text is empty, trying to extract from output array")

            # DEBUG: Dump full output array for analysis
            try:
                import json as json_module

                output_json = json_module.dumps(response.output, indent=2, default=str)
                logger.info(f"=== FULL response.output ARRAY ===\n{output_json}\n=== END ===")
            except Exception as serialize_error:
                logger.error(f"Could not serialize response.output: {serialize_error}")
                logger.error(f"Raw response.output repr: {repr(response.output)}")

            if response.output and len(response.output) > 0:
                # Try multiple extraction strategies
                for i, output_item in enumerate(response.output):
                    logger.info(f"Checking output item {i}: type={type(output_item)}")

                    # Strategy 1: output_item is a dict with type="message" and content array
                    if isinstance(output_item, dict):
                        logger.info(f"  Dict keys: {list(output_item.keys())}")

                        if output_item.get("type") == "message" and "content" in output_item:
                            logger.info("  Found message with content array")
                            for content_item in output_item["content"]:
                                logger.info(f"    Content item type: {content_item.get('type')}")
                                if content_item.get("type") == "output_text":
                                    content = content_item.get("text", "")
                                    logger.info(
                                        f"✓ Extracted from content[].output_text: {len(content)} chars"
                                    )
                                    break
                                elif content_item.get("type") == "text":
                                    content = content_item.get("text", "")
                                    logger.info(
                                        f"✓ Extracted from content[].text: {len(content)} chars"
                                    )
                                    break

                        # Strategy 2: Direct text field in output_item
                        elif "text" in output_item:
                            content = output_item["text"]
                            logger.info(f"✓ Extracted from output[{i}].text: {len(content)} chars")
                            break

                    # Strategy 3: output_item is an object with attributes
                    elif hasattr(output_item, "text"):
                        content = output_item.text
                        logger.info(
                            f"✓ Extracted from output[{i}].text attribute: {len(content)} chars"
                        )
                        break

                    # Strategy 4: output_item has content attribute
                    elif hasattr(output_item, "content"):
                        if isinstance(output_item.content, str):
                            content = output_item.content
                            logger.info(
                                f"✓ Extracted from output[{i}].content: {len(content)} chars"
                            )
                            break
                        elif isinstance(output_item.content, list):
                            for content_sub in output_item.content:
                                if hasattr(content_sub, "text"):
                                    content = content_sub.text
                                    logger.info(
                                        f"✓ Extracted from output[{i}].content[].text: {len(content)} chars"
                                    )
                                    break

                    if content:
                        break

        # Validate we got content
        if not content:
            logger.error("Failed to extract any text content from response")
            logger.error(f"Response attributes: {dir(response)}")

            # DEBUG: Serialize entire output structure for analysis
            if hasattr(response, "output"):
                try:
                    import json as json_module

                    output_json = json_module.dumps(response.output, indent=2, default=str)
                    logger.error(
                        f"=== FULL response.output (NO CONTENT FOUND) ===\n{output_json}\n=== END ==="
                    )
                except Exception as serialize_error:
                    logger.error(f"Could not serialize response.output: {serialize_error}")
                    logger.error(f"Raw response.output repr: {repr(response.output)}")

            raise LLMProviderError("No text output received from model")

        # Parse JSON
        content = content.strip()

        # Check if JSON appears complete
        if content and not (content.endswith("}") or content.endswith("]")):
            logger.warning(
                f"JSON response may be truncated - does not end with }} or ]. "
                f"Last 50 chars: {content[-50:]}"
            )

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Full content length: {len(content)} characters")
            logger.error(f"First 200 chars: {content[:200]}")
            logger.error(f"Last 200 chars: {content[-200:]}")

            # Extract context around error position if available
            if hasattr(e, "pos") and e.pos:
                error_pos = e.pos
                context_start = max(0, error_pos - 50)
                context_end = min(len(content), error_pos + 50)
                context = content[context_start:context_end]
                logger.error(
                    f"Context around error position {error_pos} "
                    f"(chars {context_start}-{context_end}): {context}"
                )

            # Attempt to repair common JSON issues (unescaped quotes)
            logger.warning(
                "Attempting JSON repair for unescaped quotes (OpenAI API bug workaround)..."
            )
            try:
                repaired_content = _repair_json_quotes(content)
                result = json.loads(repaired_content)
                logger.warning(
                    "✓ JSON repair successful! This is a workaround for OpenAI Responses API bug. "
                    "Consider reporting to OpenAI that strict mode doesn't escape quotes properly."
                )
                return result
            except json.JSONDecodeError as repair_error:
                logger.error(f"JSON repair also failed: {repair_error}")
                raise LLMProviderError(
                    f"Invalid JSON response at position {e.pos if hasattr(e, 'pos') else 'unknown'}: {e}. "
                    f"Repair attempt also failed. This may be an OpenAI API bug with strict mode."
                )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    )
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate text using OpenAI Responses API"""
        try:
            response = self.client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                instructions=system_prompt,
                max_output_tokens=self.settings.openai_max_tokens,
                # temperature not supported for reasoning models (GPT-5, o-series)
                **kwargs,
            )

            # Use SDK convenience property for aggregated text output
            result = response.output_text.strip()
            logger.info("Successfully generated text with OpenAI Responses API")
            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMProviderError(f"OpenAI API error: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    )
    def generate_json_with_schema(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        schema_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON using OpenAI Responses API with Structured Outputs.

        This uses OpenAI's native schema validation which guarantees the output
        conforms to the provided JSON schema.
        """
        try:
            # Prepare schema name
            if schema_name is None:
                schema_name = schema.get("title", "extraction_schema").replace(" ", "_")

            # Use OpenAI Responses API with structured outputs
            # strict=False allows flexible schema guidance while maintaining prompt control
            # Validation happens post-generation via dual-validation strategy
            response = self.client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                instructions=system_prompt,
                max_output_tokens=self.settings.openai_max_tokens,
                # temperature not supported for reasoning models (GPT-5, o-series)
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema,
                        "strict": False,
                    }
                },
                **kwargs,
            )

            # Parse JSON response
            result = self._parse_response_output(response)
            logger.info(f"Successfully generated schema-conforming JSON using {schema_name}")
            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error with schema-based generation: {e}")
            # Log schema size for debugging
            schema_size = len(json.dumps(schema))
            logger.error(f"Schema size: {schema_size} bytes (~{schema_size//4} tokens)")
            raise LLMProviderError(f"OpenAI schema-based generation failed: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    )
    def generate_json_with_pdf(
        self,
        pdf_path: Union[Path, str],
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        max_pages: Optional[int] = None,
        schema_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON from PDF using OpenAI Responses API with Structured Outputs.

        Uses GPT-4o/GPT-4o-mini vision capabilities to analyze PDF including tables,
        images, and charts. PDF is sent as base64-encoded file for direct processing.
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

            logger.info(f"Uploading PDF to OpenAI: {pdf_path.name} ({file_size_mb:.1f} MB)")

            # Prepare schema name
            if schema_name is None:
                schema_name = schema.get("title", "extraction_schema").replace(" ", "_")

            # Build input with PDF content (Responses API format)
            content_items = [
                {
                    "type": "input_file",
                    "filename": pdf_path.name,
                    "file_data": f"data:application/pdf;base64,{pdf_data}",
                }
            ]

            # Add page limit instruction if specified
            if max_pages:
                content_items.append(
                    {
                        "type": "input_text",
                        "text": f"Process only the first {max_pages} pages of this PDF.",
                    }
                )

            input_content = [{"role": "user", "content": content_items}]

            # Use OpenAI Responses API with structured outputs
            # strict=False allows flexible schema guidance while maintaining prompt control
            # Validation happens post-generation via dual-validation strategy
            response = self.client.responses.create(
                model=self.settings.openai_model,
                input=input_content,
                instructions=system_prompt,
                max_output_tokens=self.settings.openai_max_tokens,
                # temperature not supported for reasoning models (GPT-5, o-series)
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema,
                        "strict": False,
                    }
                },
                **kwargs,
            )

            # Parse JSON response
            result = self._parse_response_output(response)
            logger.info(
                f"Successfully extracted schema-conforming JSON from PDF using {schema_name}"
            )
            return result

        except FileNotFoundError as e:
            logger.error(f"PDF file not found: {pdf_path}")
            raise LLMProviderError(f"PDF file not found: {e}")
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error with PDF upload: {e}")
            raise LLMProviderError(f"OpenAI PDF processing failed: {e}")


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
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
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
            raise LLMProviderError(f"Claude API error: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
    )
    def generate_json_with_schema(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        schema_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
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
                    )
            else:
                logger.warning(
                    "jsonschema library not available - skipping schema validation. "
                    "Schema guidance was provided to LLM but compliance is not guaranteed."
                )

            return result

        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error with schema-based generation: {e}")
            raise LLMProviderError(f"Claude schema-based generation failed: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            # Truncate long responses to avoid logging sensitive data
            content_preview = content[:200] + "..." if len(content) > 200 else content
            logger.error(f"Raw response preview: {content_preview}")
            raise LLMProviderError(f"Invalid JSON response: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
    )
    def generate_json_with_pdf(
        self,
        pdf_path: Union[Path, str],
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        max_pages: Optional[int] = None,
        schema_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
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
                    )
            else:
                logger.warning(
                    "jsonschema library not available - skipping schema validation. "
                    "Schema guidance was provided to LLM but compliance is not guaranteed."
                )

            return result

        except FileNotFoundError as e:
            logger.error(f"PDF file not found: {pdf_path}")
            raise LLMProviderError(f"PDF file not found: {e}")
        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error with PDF upload: {e}")
            raise LLMProviderError(f"Claude PDF processing failed: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            # Truncate long responses to avoid logging sensitive data
            content_preview = content[:200] + "..." if len(content) > 200 else content
            logger.error(f"Raw response preview: {content_preview}")
            raise LLMProviderError(f"Invalid JSON response: {e}")


def get_llm_provider(
    provider: Union[str, LLMProvider], settings: Optional[LLMSettings] = None
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
        except ValueError:
            raise LLMError(
                f"Unsupported provider: {provider}. Supported: {[p.value for p in LLMProvider]}"
            )

    if provider == LLMProvider.OPENAI:
        return OpenAIProvider(settings)
    elif provider == LLMProvider.CLAUDE:
        return ClaudeProvider(settings)
    else:
        raise LLMError(f"Unsupported provider: {provider}")


# Convenience functions for backward compatibility and easy usage
def generate_text(
    prompt: str,
    provider: Union[str, LLMProvider] = None,
    system_prompt: Optional[str] = None,
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
    schema: Dict[str, Any],
    provider: Union[str, LLMProvider] = None,
    system_prompt: Optional[str] = None,
    schema_name: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
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
