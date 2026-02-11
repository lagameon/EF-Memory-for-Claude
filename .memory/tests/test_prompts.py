"""
Tests for EF Memory V2 — LLM Prompt Templates (M6)

Covers: _truncate, _entries_to_compact_text, correlation_prompt,
        contradiction_prompt, synthesis_prompt, risk_prompt,
        single_entry_prompt
"""

import sys
import unittest
from pathlib import Path

# Import path setup
_MEMORY_DIR = Path(__file__).resolve().parent.parent
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))

from lib.prompts import (
    _DEFAULT_MAX_INPUT_CHARS,
    _entries_to_compact_text,
    _truncate,
    contradiction_prompt,
    correlation_prompt,
    risk_prompt,
    single_entry_prompt,
    synthesis_prompt,
)


# ===========================================================================
# Test: _truncate
# ===========================================================================

class TestTruncate(unittest.TestCase):

    def test_short_text_unchanged(self):
        self.assertEqual(_truncate("hello", 100), "hello")

    def test_long_text_truncated(self):
        result = _truncate("a" * 200, 50)
        self.assertEqual(len(result), 50)
        self.assertTrue(result.endswith("..."))

    def test_exact_limit_unchanged(self):
        text = "x" * 100
        result = _truncate(text, 100)
        self.assertEqual(result, text)

    def test_empty_string(self):
        self.assertEqual(_truncate("", 10), "")


# ===========================================================================
# Test: _entries_to_compact_text
# ===========================================================================

class TestEntriesToCompactText(unittest.TestCase):

    def test_single_entry(self):
        entries = [{
            "id": "lesson-test-12345678",
            "type": "lesson",
            "classification": "hard",
            "severity": "S1",
            "title": "Test entry",
            "rule": "MUST test",
            "tags": ["test"],
            "source": ["src/test.py:L1-L10"],
        }]
        text = _entries_to_compact_text(entries, 5000)
        self.assertIn("lesson-test-12345678", text)
        self.assertIn("Test entry", text)
        self.assertIn("MUST test", text)
        self.assertIn("test", text)

    def test_truncation_on_limit(self):
        entries = [
            {"id": f"entry-{i:08d}", "type": "lesson", "classification": "soft",
             "severity": "S3", "title": f"Entry number {i} with some content",
             "tags": ["tag1", "tag2"], "source": [f"file{i}.py"]}
            for i in range(100)
        ]
        text = _entries_to_compact_text(entries, 500)
        self.assertIn("truncated", text)
        self.assertLessEqual(len(text), 1000)  # Some overhead from join

    def test_empty_entries(self):
        text = _entries_to_compact_text([], 5000)
        self.assertEqual(text, "")

    def test_no_rule_no_tags(self):
        entries = [{
            "id": "fact-simple-12345678",
            "type": "fact",
            "classification": "soft",
            "severity": None,
            "title": "Simple fact",
        }]
        text = _entries_to_compact_text(entries, 5000)
        self.assertIn("Simple fact", text)
        self.assertNotIn("Rule:", text)


# ===========================================================================
# Test: correlation_prompt
# ===========================================================================

class TestCorrelationPrompt(unittest.TestCase):

    def test_returns_tuple(self):
        system, user = correlation_prompt("entries", "groups")
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)

    def test_system_mentions_json(self):
        system, _ = correlation_prompt("entries", "groups")
        self.assertIn("JSON", system)

    def test_user_contains_entries(self):
        _, user = correlation_prompt("my entries here", "my groups")
        self.assertIn("my entries here", user)

    def test_truncation_applied(self):
        long_text = "x" * 20000
        _, user = correlation_prompt(long_text, "groups", max_input_chars=100)
        self.assertLessEqual(len(user), 110)  # small overhead


# ===========================================================================
# Test: contradiction_prompt
# ===========================================================================

class TestContradictionPrompt(unittest.TestCase):

    def test_returns_tuple(self):
        system, user = contradiction_prompt("pairs text")
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)

    def test_mentions_contradiction(self):
        system, _ = contradiction_prompt("pairs")
        self.assertIn("contradict", system.lower())


# ===========================================================================
# Test: synthesis_prompt
# ===========================================================================

class TestSynthesisPrompt(unittest.TestCase):

    def test_returns_tuple(self):
        system, user = synthesis_prompt("cluster text")
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)

    def test_mentions_synthesis(self):
        system, _ = synthesis_prompt("clusters")
        self.assertIn("synthe", system.lower())


# ===========================================================================
# Test: risk_prompt
# ===========================================================================

class TestRiskPrompt(unittest.TestCase):

    def test_returns_tuple(self):
        system, user = risk_prompt("query", "results", "context")
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)

    def test_includes_query(self):
        _, user = risk_prompt("my query", "results", "context")
        self.assertIn("my query", user)


# ===========================================================================
# Test: single_entry_prompt
# ===========================================================================

class TestSingleEntryPrompt(unittest.TestCase):

    def test_returns_tuple(self):
        system, user = single_entry_prompt("entry text", "related text")
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)

    def test_mentions_analysis(self):
        system, _ = single_entry_prompt("entry", "related")
        self.assertIn("analysis", system.lower())


# ===========================================================================
# Test: Default constant
# ===========================================================================

class TestDefaults(unittest.TestCase):

    def test_default_max_input_chars(self):
        self.assertEqual(_DEFAULT_MAX_INPUT_CHARS, 12000)


if __name__ == "__main__":
    unittest.main()
