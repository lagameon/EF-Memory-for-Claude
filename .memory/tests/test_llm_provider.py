"""
Tests for EF Memory V2 — LLM Provider Factory + Helpers

Covers: create_llm_provider, _resolve_api_key, factory patterns.
Provider classes (Anthropic/OpenAI/Gemini/Ollama) require external SDKs
and are not tested here.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Import path setup
_MEMORY_DIR = Path(__file__).resolve().parent.parent
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

from lib.llm_provider import (
    LLMResponse,
    create_llm_provider,
    _resolve_api_key,
)
from tests.conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------

class TestLLMResponse(unittest.TestCase):

    def test_basic_construction(self):
        r = LLMResponse(text="hello", model="m", provider="p")
        self.assertEqual(r.text, "hello")
        self.assertEqual(r.model, "m")
        self.assertEqual(r.provider, "p")
        self.assertEqual(r.input_tokens, 0)
        self.assertEqual(r.output_tokens, 0)

    def test_with_token_counts(self):
        r = LLMResponse(
            text="world", model="m", provider="p",
            input_tokens=100, output_tokens=50,
        )
        self.assertEqual(r.input_tokens, 100)
        self.assertEqual(r.output_tokens, 50)


# ---------------------------------------------------------------------------
# _resolve_api_key
# ---------------------------------------------------------------------------

class TestResolveApiKey(unittest.TestCase):

    def test_returns_env_var_value(self):
        with patch.dict("os.environ", {"MY_LLM_KEY": "secret456"}):
            result = _resolve_api_key({"api_key_env": "MY_LLM_KEY"})
            self.assertEqual(result, "secret456")

    def test_returns_none_when_env_var_missing(self):
        result = _resolve_api_key({"api_key_env": "NONEXISTENT_LLM_KEY_99999"})
        self.assertIsNone(result)

    def test_returns_none_when_no_env_key_configured(self):
        result = _resolve_api_key({})
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# create_llm_provider — factory tests
# ---------------------------------------------------------------------------

class TestCreateLLMProvider(unittest.TestCase):

    def test_disabled_returns_none(self):
        result = create_llm_provider({"enabled": False})
        self.assertIsNone(result)

    def test_disabled_by_default(self):
        result = create_llm_provider({})
        self.assertIsNone(result)

    def test_unknown_provider_returns_none(self):
        config = {
            "enabled": True,
            "provider": "nonexistent_provider_xyz",
            "fallback": [],
        }
        result = create_llm_provider(config)
        self.assertIsNone(result)

    def test_import_error_graceful(self):
        """Providers whose SDK is not installed should be skipped."""
        config = {
            "enabled": True,
            "provider": "anthropic",
            "fallback": ["openai", "ollama"],
            "providers": {},
        }
        result = create_llm_provider(config)
        # All SDKs should fail to import or fail with missing API key
        self.assertIsNone(result)

    def test_fallback_chain_skips_duplicate_primary(self):
        config = {
            "enabled": True,
            "provider": "anthropic",
            "fallback": ["anthropic", "openai"],
            "providers": {},
        }
        result = create_llm_provider(config)
        self.assertIsNone(result)

    def test_fallback_chain_skips_none(self):
        config = {
            "enabled": True,
            "provider": "anthropic",
            "fallback": ["none", "openai"],
            "providers": {},
        }
        result = create_llm_provider(config)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# MockLLMProvider (from conftest)
# ---------------------------------------------------------------------------

class TestMockLLMProvider(unittest.TestCase):

    def test_provider_id(self):
        mock = MockLLMProvider()
        self.assertEqual(mock.provider_id, "mock")

    def test_model_name(self):
        mock = MockLLMProvider()
        self.assertEqual(mock.model_name, "mock-llm-v1")

    def test_default_response(self):
        mock = MockLLMProvider()
        result = mock.complete("sys", "hello")
        self.assertIsNotNone(result.text)
        self.assertEqual(result.model, "mock-llm-v1")
        self.assertEqual(result.provider, "mock")

    def test_keyword_matching(self):
        mock = MockLLMProvider(responses={
            "correlation": '{"groups": []}',
            "contradiction": '{"pairs": []}',
        })
        r1 = mock.complete("sys", "analyze correlation between entries")
        self.assertEqual(r1.text, '{"groups": []}')
        r2 = mock.complete("sys", "detect contradiction in rules")
        self.assertEqual(r2.text, '{"pairs": []}')

    def test_call_tracking(self):
        mock = MockLLMProvider()
        self.assertEqual(mock._call_count, 0)
        mock.complete("sys1", "user1")
        mock.complete("sys2", "user2")
        self.assertEqual(mock._call_count, 2)
        self.assertEqual(len(mock._calls), 2)
        self.assertEqual(mock._calls[0], ("sys1", "user1"))
        self.assertEqual(mock._calls[1], ("sys2", "user2"))

    def test_token_counts_present(self):
        mock = MockLLMProvider()
        result = mock.complete("system prompt", "user prompt with words")
        self.assertIsInstance(result.input_tokens, int)
        self.assertIsInstance(result.output_tokens, int)
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)


# ---------------------------------------------------------------------------
# Provider import error tests
# ---------------------------------------------------------------------------

class TestProviderImportErrors(unittest.TestCase):
    """Test that each provider raises ImportError when SDK is missing."""

    def test_anthropic_import_error(self):
        """AnthropicProvider should raise ImportError when SDK not installed."""
        # The anthropic SDK may or may not be installed; test the factory path
        config = {
            "enabled": True,
            "provider": "anthropic",
            "fallback": [],
            "providers": {"anthropic": {}},
        }
        # Either SDK not installed (ImportError) or no API key (ValueError)
        # Both are caught by factory → returns None
        result = create_llm_provider(config)
        self.assertIsNone(result)

    def test_openai_import_error(self):
        config = {
            "enabled": True,
            "provider": "openai",
            "fallback": [],
            "providers": {"openai": {}},
        }
        result = create_llm_provider(config)
        self.assertIsNone(result)

    def test_gemini_import_error(self):
        config = {
            "enabled": True,
            "provider": "gemini",
            "fallback": [],
            "providers": {"gemini": {}},
        }
        result = create_llm_provider(config)
        self.assertIsNone(result)

    def test_ollama_import_error(self):
        config = {
            "enabled": True,
            "provider": "ollama",
            "fallback": [],
            "providers": {"ollama": {}},
        }
        result = create_llm_provider(config)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
