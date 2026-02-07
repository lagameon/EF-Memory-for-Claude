"""
EF Memory V2 — Test Fixtures

Shared sample data and mock objects for unit tests.

Run from project root:
    python3 -m unittest discover -s .memory/tests -v
"""

import sys
import math
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Ensure .memory/ is on the import path so 'lib' is importable
_MEMORY_DIR = Path(__file__).resolve().parent.parent
if str(_MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(_MEMORY_DIR))


# Sample memory entries matching SCHEMA.md
SAMPLE_ENTRIES = [
    {
        "id": "lesson-inc036-a3f8c2d1",
        "type": "lesson",
        "classification": "hard",
        "severity": "S1",
        "title": "Rolling statistics without shift(1) caused 999x backtest inflation",
        "content": [
            "42 rolling/ewm/pct_change calls missing shift(1) in feature engine",
            "Model learned to explain past, not predict future",
            "IC with T-5 returns (-0.115) > IC with T+1 returns (0.018)",
            "Backtest showed 49,979% return; after fix only 52%",
        ],
        "rule": "shift(1) MUST precede any rolling(), ewm(), pct_change() on price-derived data",
        "implication": "Backtest returns inflated 100-1000x; predictions structurally encode future information",
        "verify": "grep -rn 'rolling\\|ewm\\|pct_change' src/features/*.py | grep -v 'shift(1)'",
        "source": ["docs/decisions/INCIDENTS.md#INC-036:L553-L699"],
        "tags": ["leakage", "feature-engine", "shift", "rolling"],
        "created_at": "2026-02-01T14:30:00Z",
        "last_verified": None,
        "deprecated": False,
        "_meta": {},
    },
    {
        "id": "lesson-inc035-7b2e4f9a",
        "type": "lesson",
        "classification": "hard",
        "severity": "S1",
        "title": "Walk-Forward labels on full data caused 191x performance inflation",
        "content": [
            "Labels generated on full dataset before walk-forward split",
            "Training windows included future label information",
            "191x backtest inflation detected",
        ],
        "rule": "Labels MUST be generated inside each WF training window, then drop tail MAX_HORIZON rows",
        "implication": "All WF predictions invalid; model trained on future information",
        "source": ["docs/decisions/INCIDENTS.md#INC-035:L407-L498"],
        "tags": ["leakage", "walk-forward", "label"],
        "created_at": "2026-02-01T14:00:00Z",
        "last_verified": None,
        "deprecated": False,
        "_meta": {},
    },
    {
        "id": "fact-risk_adjusted-9c3a1e5f",
        "type": "fact",
        "classification": "soft",
        "severity": "S3",
        "title": "3K label uses dual-condition (return + drawdown), not just ATR breakout",
        "content": [
            "CLAUDE.md describes 3K as: close[t+3]/close[t] - 1 > ATR_14/close[t]",
            "Actual implementation uses create_return_drawdown_label(horizon=3)",
            "Dual conditions: future_return > 0.1% AND max_drawdown < 0.5%",
        ],
        "rule": None,
        "implication": "Stricter than documented; may affect threshold tuning expectations",
        "source": ["src/labels/risk_adjusted_labels.py:L93-L144"],
        "tags": ["label", "3k", "documentation"],
        "created_at": "2026-02-01T15:00:00Z",
        "last_verified": None,
        "deprecated": False,
        "_meta": {},
    },
]


@dataclass
class _EmbeddingResult:
    vector: List[float]
    model: str
    dimensions: int


class MockEmbedder:
    """Mock embedding provider for testing (returns deterministic vectors)."""

    def __init__(self, dimensions: int = 768):
        self._dims = dimensions

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-embed-v1"

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed_documents(self, texts):
        """Return deterministic vectors based on text hash."""
        return [
            _EmbeddingResult(
                vector=self._text_to_vector(text),
                model="mock-embed-v1",
                dimensions=self._dims,
            )
            for text in texts
        ]

    def embed_query(self, text):
        return _EmbeddingResult(
            vector=self._text_to_vector(text),
            model="mock-embed-v1",
            dimensions=self._dims,
        )

    def _text_to_vector(self, text: str) -> List[float]:
        """Generate a deterministic vector from text using simple hashing."""
        h = hashlib.sha256(text.encode()).digest()
        vec = [0.0] * self._dims
        for i in range(self._dims):
            byte_idx = i % len(h)
            vec[i] = (h[byte_idx] - 128) / 128.0
            vec[i] += (i % 7 - 3) * 0.01
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


# ---------------------------------------------------------------------------
# Mock LLM Provider (M6)
# ---------------------------------------------------------------------------

@dataclass
class _LLMResponse:
    """Mirrors lib.llm_provider.LLMResponse for test independence."""
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class MockLLMProvider:
    """Mock LLM provider for testing (returns canned responses by keyword)."""

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self._responses = responses or {}
        self._default_response = '{"result": "mock analysis"}'
        self._call_count = 0
        self._calls: List[Tuple[str, str]] = []

    @property
    def provider_id(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-llm-v1"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> _LLMResponse:
        self._call_count += 1
        self._calls.append((system_prompt, user_prompt))
        # Match response by keyword in user_prompt
        for keyword, response_text in self._responses.items():
            if keyword.lower() in user_prompt.lower():
                text = response_text
                break
        else:
            text = self._default_response
        return _LLMResponse(
            text=text,
            model="mock-llm-v1",
            provider="mock",
            input_tokens=len(user_prompt.split()),
            output_tokens=len(text.split()),
        )


# ---------------------------------------------------------------------------
# Extended sample entries for M6 reasoning tests
# ---------------------------------------------------------------------------

SAMPLE_ENTRIES_EXTENDED = SAMPLE_ENTRIES + [
    {
        "id": "lesson-deploy01-1a2b3c4d",
        "type": "lesson",
        "classification": "hard",
        "severity": "S2",
        "title": "Rolling window must use shift before pct_change in deployment pipeline",
        "content": [
            "Deployment pipeline had same shift-before-rolling bug",
            "Caught during staging review",
        ],
        "rule": "shift(1) MUST precede pct_change() in deployment feature generation",
        "implication": "Deployment predictions would be invalid without shift",
        "source": ["deployment/feature_gen.py:L45-L60"],
        "tags": ["leakage", "shift", "deployment", "rolling"],
        "created_at": "2026-02-02T10:00:00Z",
        "last_verified": "2026-02-05T09:00:00Z",
        "deprecated": False,
        "_meta": {},
    },
    {
        "id": "rule-cache01-5e6f7a8b",
        "type": "rule",
        "classification": "hard",
        "severity": "S2",
        "title": "Cache TTL must be explicitly set for all API responses",
        "content": [
            "Default cache TTL caused stale predictions served to users",
            "Must set TTL on every cache.set() call",
        ],
        "rule": "Every cache.set() call MUST include explicit ttl parameter",
        "implication": "Stale data served to users; incorrect trading signals",
        "source": ["src/api/cache.py:L30-L55"],
        "tags": ["cache", "api", "ttl"],
        "created_at": "2026-02-03T11:00:00Z",
        "last_verified": None,
        "deprecated": False,
        "_meta": {},
    },
    {
        "id": "lesson-contra01-9c0d1e2f",
        "type": "lesson",
        "classification": "soft",
        "severity": "S3",
        "title": "Never apply shift before rolling window calculations",
        "content": [
            "Initial implementation applied shift before rolling",
            "This caused look-ahead bias in a different way",
        ],
        "rule": "NEVER apply shift(1) before rolling() — shift must come after",
        "implication": "Different form of data leakage through premature shifting",
        "source": ["src/features/engine.py:L100-L120"],
        "tags": ["leakage", "shift", "rolling", "feature-engine"],
        "created_at": "2025-06-15T08:00:00Z",
        "last_verified": None,
        "deprecated": False,
        "_meta": {},
    },
]
