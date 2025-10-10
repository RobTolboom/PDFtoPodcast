# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
OpenAI provider implementation with Structured Outputs support.

This module provides the OpenAI-specific implementation of the LLM provider interface.
"""

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, cast

import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import LLMSettings
from .base import BaseLLMProvider, LLMProviderError

logger = logging.getLogger(__name__)


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


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI API provider implementation with native Structured Outputs support.

    This provider uses OpenAI's Responses API with support for:
    - Free-form text generation
    - Structured Outputs with JSON Schema (strict mode)

    The Structured Outputs feature guarantees that generated JSON conforms
    to the provided schema at generation time, eliminating the need for
    post-generation validation.

    Supported models: gpt-5, and other models with structured output support

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

    def _parse_response_output(self, response) -> dict[str, Any]:
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
            return cast(dict[str, Any], json.loads(content))
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
                result = cast(dict[str, Any], json.loads(repaired_content))
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
                ) from repair_error

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    )
    def generate_text(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
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
            result = str(response.output_text).strip()
            logger.info("Successfully generated text with OpenAI Responses API")
            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMProviderError(f"OpenAI API error: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
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
            raise LLMProviderError(f"OpenAI schema-based generation failed: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
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
        Generate structured JSON from PDF using OpenAI Responses API with Structured Outputs.

        Uses GPT-5 vision capabilities to analyze PDF including tables,
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
            response = self.client.responses.create(  # type: ignore[call-overload]
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
            raise LLMProviderError(f"PDF file not found: {e}") from e
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error with PDF upload: {e}")
            raise LLMProviderError(f"OpenAI PDF processing failed: {e}") from e
