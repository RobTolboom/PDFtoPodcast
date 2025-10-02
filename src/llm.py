# llm.py

import json
import logging
from abc import ABC, abstractmethod
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


class LLMError(Exception):
    """Base exception for LLM-related errors"""

    pass


class LLMProviderError(LLMError):
    """Error with specific LLM provider"""

    pass


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate text response from prompt"""
        pass

    @abstractmethod
    def generate_json(
        self, prompt: str, system_prompt: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Generate structured JSON response from prompt"""
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


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider implementation"""

    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        if not settings.openai_api_key:
            raise LLMProviderError("OpenAI API key not found in environment variables")

        self.client = openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.timeout)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    )
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate text using OpenAI API"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                max_tokens=self.settings.openai_max_tokens,
                temperature=self.settings.temperature,
                **kwargs,
            )

            return response.choices[0].message.content.strip()

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMProviderError(f"OpenAI API error: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    )
    def generate_json(
        self, prompt: str, system_prompt: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Generate structured JSON using OpenAI API (generic JSON mode)"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                max_tokens=self.settings.openai_max_tokens,
                temperature=self.settings.temperature,
                response_format={"type": "json_object"},
                **kwargs,
            )

            content = response.choices[0].message.content.strip()
            return json.loads(content)

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMProviderError(f"OpenAI API error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise LLMProviderError(f"Invalid JSON response: {e}")

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
        Generate structured JSON using OpenAI's Structured Outputs feature.

        This uses OpenAI's native schema validation which guarantees the output
        conforms to the provided JSON schema.
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Prepare schema name
            if schema_name is None:
                schema_name = schema.get("title", "extraction_schema").replace(" ", "_")

            # Use OpenAI's structured outputs with strict schema validation
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                max_tokens=self.settings.openai_max_tokens,
                temperature=self.settings.temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
                **kwargs,
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            logger.info(f"Successfully generated schema-conforming JSON using {schema_name}")
            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error with schema-based generation: {e}")
            # Log schema size for debugging
            schema_size = len(json.dumps(schema))
            logger.error(f"Schema size: {schema_size} bytes (~{schema_size//4} tokens)")
            raise LLMProviderError(f"OpenAI schema-based generation failed: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise LLMProviderError(f"Invalid JSON response: {e}")


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude API provider implementation"""

    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        if not settings.anthropic_api_key:
            raise LLMProviderError("Anthropic API key not found in environment variables")

        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.timeout
        )

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

            return response.content[0].text.strip()

        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error: {e}")
            raise LLMProviderError(f"Claude API error: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError)),
    )
    def generate_json(
        self, prompt: str, system_prompt: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Generate structured JSON using Claude API (generic JSON mode)"""
        try:
            # Add JSON instruction to system prompt
            json_instruction = "\n\nIMPORTANT: Return ONLY a valid JSON object, no additional text or explanations."
            full_system_prompt = (system_prompt or "") + json_instruction

            response = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=self.settings.anthropic_max_tokens,
                temperature=self.settings.temperature,
                system=full_system_prompt,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )

            content = response.content[0].text.strip()

            # Try to extract JSON if wrapped in markdown code blocks
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()

            return json.loads(content)

        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error: {e}")
            raise LLMProviderError(f"Claude API error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {content}")
            raise LLMProviderError(f"Invalid JSON response: {e}")

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

            # Try to extract JSON if wrapped in markdown code blocks
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()

            result = json.loads(content)

            # Validate against schema using jsonschema library
            try:
                import jsonschema

                jsonschema.validate(result, schema)
                logger.info("Successfully generated and validated schema-conforming JSON")
            except ImportError:
                logger.warning("jsonschema library not available - skipping validation")
            except jsonschema.ValidationError as e:
                logger.error(f"Schema validation failed: {e.message}")
                raise LLMProviderError(f"Generated JSON does not conform to schema: {e.message}")

            return result

        except anthropic.AnthropicError as e:
            logger.error(f"Claude API error with schema-based generation: {e}")
            raise LLMProviderError(f"Claude schema-based generation failed: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {content}")
            raise LLMProviderError(f"Invalid JSON response: {e}")


def get_llm_provider(
    provider: Union[str, LLMProvider], settings: Optional[LLMSettings] = None
) -> BaseLLMProvider:
    """Factory function to get LLM provider instance"""
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
    """Generate text using specified or default provider"""
    if provider is None:
        provider = llm_settings.default_provider

    llm = get_llm_provider(provider)
    return llm.generate_text(prompt, system_prompt, **kwargs)


def generate_json(
    prompt: str,
    provider: Union[str, LLMProvider] = None,
    system_prompt: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Generate JSON using specified or default provider"""
    if provider is None:
        provider = llm_settings.default_provider

    llm = get_llm_provider(provider)
    return llm.generate_json(prompt, system_prompt, **kwargs)
