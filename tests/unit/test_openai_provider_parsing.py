# Copyright (c) 2025 Tolboom Medical
# Licensed under Prosperity Public License 3.0.0
# Commercial use requires separate license - see LICENSE and COMMERCIAL_LICENSE.md

"""
Unit tests for OpenAI provider response parsing and JSON repair logic.
"""

import pytest

from src.config import LLMSettings
from src.llm.base import LLMProviderError
from src.llm.openai_provider import OpenAIProvider, _repair_json_quotes

pytestmark = pytest.mark.unit


class DummyUsage:
    def __init__(self):
        self.input_tokens = 1
        self.output_tokens = 2
        self.total_tokens = 3


class DummyResponse:
    def __init__(self, output_text=None, output=None):
        self.output_text = output_text
        self.output = output or []
        self.usage = DummyUsage()
        self.status = "completed"
        self.model = "gpt-5.1"
        self.id = "resp_123"
        self.created_at = 1234567890


def _make_provider():
    """
    Create an OpenAIProvider instance without invoking the real constructor.
    """
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.settings = LLMSettings(openai_api_key="dummy-key")
    provider.client = None
    return provider


class TestRepairQuotes:
    def test_repairs_unescaped_quotes(self):
        malformed = '{"title": "Study with "quotes" inside"}'
        repaired = _repair_json_quotes(malformed)
        assert '\\"quotes\\"' in repaired
        assert repaired.count('\\"') == 2


class TestParseResponseOutput:
    def test_parses_output_text_json_and_attaches_usage(self):
        provider = _make_provider()
        response = DummyResponse(output_text='{"a": 1}')

        result = provider._parse_response_output(response)

        assert result["a"] == 1
        assert result["usage"]["input_tokens"] == 1
        assert result["_metadata"]["model"] == "gpt-5.1"

    def test_repairs_unescaped_quotes_and_parses(self):
        provider = _make_provider()
        response = DummyResponse(output_text='{"title": "Study with "quotes" inside"}')

        result = provider._parse_response_output(response)

        assert result["title"] == 'Study with "quotes" inside'

    def test_raises_on_missing_content(self):
        provider = _make_provider()
        response = DummyResponse(output_text=None, output=[])

        with pytest.raises(LLMProviderError):
            provider._parse_response_output(response)
