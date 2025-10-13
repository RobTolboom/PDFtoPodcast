"""
Unit tests for src/llm/base.py

Tests base classes and exceptions for LLM provider abstraction.
"""

import pytest

from src.config import LLMSettings
from src.llm.base import BaseLLMProvider, LLMError, LLMProviderError

pytestmark = pytest.mark.unit


class TestLLMExceptions:
    """Test LLM exception classes."""

    def test_llm_error_is_exception(self):
        """Test that LLMError is a proper exception."""
        error = LLMError("Test error")

        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_llm_provider_error_is_llm_error(self):
        """Test that LLMProviderError inherits from LLMError."""
        error = LLMProviderError("Provider failed")

        assert isinstance(error, LLMError)
        assert isinstance(error, Exception)
        assert str(error) == "Provider failed"

    def test_llm_error_can_be_raised_and_caught(self):
        """Test that LLMError can be raised and caught."""
        with pytest.raises(LLMError) as exc_info:
            raise LLMError("LLM operation failed")

        assert "LLM operation failed" in str(exc_info.value)

    def test_llm_provider_error_can_be_caught_as_llm_error(self):
        """Test that LLMProviderError can be caught as LLMError."""
        with pytest.raises(LLMError):
            raise LLMProviderError("Provider-specific error")


class TestBaseLLMProvider:
    """Test the BaseLLMProvider abstract base class."""

    def test_base_llm_provider_is_abstract(self):
        """Test that BaseLLMProvider cannot be instantiated directly."""
        settings = LLMSettings()

        with pytest.raises(TypeError) as exc_info:
            BaseLLMProvider(settings)

        assert "abstract" in str(exc_info.value).lower()

    def test_base_llm_provider_stores_settings(self):
        """Test that BaseLLMProvider stores settings in subclass."""

        # Create concrete subclass for testing
        class TestProvider(BaseLLMProvider):
            def generate_text(self, prompt, system_prompt=None, **kwargs):
                return "test"

            def generate_json_with_schema(
                self, prompt, schema, system_prompt=None, schema_name=None, **kwargs
            ):
                return {}

            def generate_json_with_pdf(
                self,
                pdf_path,
                schema,
                system_prompt=None,
                max_pages=None,
                schema_name=None,
                **kwargs,
            ):
                return {}

        settings = LLMSettings()
        provider = TestProvider(settings)

        assert provider.settings is settings

    def test_base_llm_provider_has_generate_text_method(self):
        """Test that BaseLLMProvider defines generate_text abstract method."""
        assert hasattr(BaseLLMProvider, "generate_text")
        assert callable(BaseLLMProvider.generate_text)

    def test_base_llm_provider_has_generate_json_with_schema_method(self):
        """Test that BaseLLMProvider defines generate_json_with_schema abstract method."""
        assert hasattr(BaseLLMProvider, "generate_json_with_schema")
        assert callable(BaseLLMProvider.generate_json_with_schema)

    def test_base_llm_provider_has_generate_json_with_pdf_method(self):
        """Test that BaseLLMProvider defines generate_json_with_pdf abstract method."""
        assert hasattr(BaseLLMProvider, "generate_json_with_pdf")
        assert callable(BaseLLMProvider.generate_json_with_pdf)
