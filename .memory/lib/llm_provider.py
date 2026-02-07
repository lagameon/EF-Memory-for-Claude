"""
EF Memory V2 — LLM Provider Abstraction (M6)

Unified interface for Anthropic, OpenAI, Gemini, and Ollama LLM providers.
Each provider SDK is lazily imported via try/except — install only what you need.

Usage:
    from llm_provider import create_llm_provider
    llm = create_llm_provider(config["reasoning"])
    # Returns None if no provider is available (graceful degradation)
"""

import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("efm.llm_provider")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Result of an LLM completion call."""
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """
    Base class for all LLM providers.

    Subclasses must implement:
    - complete(): single text completion
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider identifier: 'anthropic', 'openai', 'gemini', 'ollama'."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name used for completion."""
        ...

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Generate a text completion.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User message / query.
            max_tokens: Maximum output tokens.

        Returns:
            LLMResponse with generated text and token counts.
        """
        ...


# ---------------------------------------------------------------------------
# Anthropic Provider
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude via anthropic SDK.

    Models:
    - claude-sonnet-4-20250514 (default)
    - claude-haiku-4-20250514
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "Anthropic LLM requires the anthropic package.\n"
                "Install with: pip install anthropic"
            )

        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY "
                "environment variable, or pass api_key directly."
            )

        self._client = Anthropic(api_key=resolved_key)
        self._model = model

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text if response.content else ""
        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)
        return LLMResponse(
            text=text,
            model=self._model,
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):
    """
    OpenAI via openai SDK.

    Models:
    - gpt-4o-mini (default)
    - gpt-4o
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI LLM requires the openai package.\n"
                "Install with: pip install openai"
            )

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY "
                "environment variable, or pass api_key directly."
            )

        self._client = OpenAI(api_key=resolved_key)
        self._model = model

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choice = response.choices[0] if response.choices else None
        text = choice.message.content if choice and choice.message else ""
        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        return LLMResponse(
            text=text or "",
            model=self._model,
            provider="openai",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------

class GeminiLLMProvider(LLMProvider):
    """
    Google Gemini via google-genai SDK.

    Models:
    - gemini-2.0-flash (default)
    - gemini-1.5-pro
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
    ):
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "Gemini LLM requires the google-genai package.\n"
                "Install with: pip install google-genai"
            )

        resolved_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Gemini API key not found. Set GOOGLE_API_KEY or GEMINI_API_KEY "
                "environment variable, or pass api_key directly."
            )

        self._client = genai.Client(api_key=resolved_key)
        self._types = types
        self._model = model

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
            ),
        )
        text = response.text if hasattr(response, "text") and response.text else ""
        # Token counts from usage metadata
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        return LLMResponse(
            text=text,
            model=self._model,
            provider="gemini",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Ollama Provider
# ---------------------------------------------------------------------------

class OllamaLLMProvider(LLMProvider):
    """
    Ollama local LLM via ollama SDK.

    Models:
    - llama3.1 (default)
    - mistral
    - qwen2.5
    """

    def __init__(
        self,
        model: str = "llama3.1",
        host: str = "http://localhost:11434",
    ):
        try:
            import ollama as ollama_sdk
        except ImportError:
            raise ImportError(
                "Ollama LLM requires the ollama package.\n"
                "Install with: pip install ollama"
            )

        self._client = ollama_sdk.Client(host=host)
        self._model = model

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"num_predict": max_tokens},
        )
        text = ""
        if isinstance(response, dict):
            msg = response.get("message", {})
            text = msg.get("content", "") if isinstance(msg, dict) else ""
        input_tokens = 0
        output_tokens = 0
        if isinstance(response, dict):
            input_tokens = response.get("prompt_eval_count", 0) or 0
            output_tokens = response.get("eval_count", 0) or 0
        return LLMResponse(
            text=text,
            model=self._model,
            provider="ollama",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDER_CONSTRUCTORS = {
    "anthropic": lambda cfg: AnthropicProvider(
        api_key=_resolve_api_key(cfg),
        model=cfg.get("model", "claude-sonnet-4-20250514"),
    ),
    "openai": lambda cfg: OpenAIProvider(
        api_key=_resolve_api_key(cfg),
        model=cfg.get("model", "gpt-4o-mini"),
    ),
    "gemini": lambda cfg: GeminiLLMProvider(
        api_key=_resolve_api_key(cfg),
        model=cfg.get("model", "gemini-2.0-flash"),
    ),
    "ollama": lambda cfg: OllamaLLMProvider(
        model=cfg.get("model", "llama3.1"),
        host=cfg.get("host", "http://localhost:11434"),
    ),
}


def _resolve_api_key(provider_config: dict) -> Optional[str]:
    """Resolve API key from provider config or environment."""
    env_var = provider_config.get("api_key_env")
    if env_var:
        return os.environ.get(env_var)
    return None


def create_llm_provider(reasoning_config: dict) -> Optional[LLMProvider]:
    """
    Create an LLM provider from the reasoning section of config.json.

    Tries the primary provider first, then walks the fallback chain.
    Returns None if no provider is available (graceful degradation).

    Args:
        reasoning_config: The "reasoning" section of .memory/config.json

    Returns:
        An LLMProvider instance, or None if all providers fail.
    """
    if not reasoning_config.get("enabled", False):
        logger.info("LLM reasoning layer is disabled.")
        return None

    providers_config = reasoning_config.get("providers", {})
    primary = reasoning_config.get("provider", "anthropic")
    fallbacks = reasoning_config.get("fallback", [])

    # Build ordered list of providers to try
    to_try = [primary] + [f for f in fallbacks if f != "none" and f != primary]

    for provider_id in to_try:
        constructor = _PROVIDER_CONSTRUCTORS.get(provider_id)
        if not constructor:
            logger.warning(f"Unknown LLM provider: {provider_id}")
            continue

        provider_cfg = providers_config.get(provider_id, {})
        try:
            provider = constructor(provider_cfg)
            logger.info(
                f"LLM provider initialized: {provider.provider_id} "
                f"({provider.model_name})"
            )
            return provider
        except ImportError as e:
            logger.warning(f"LLM provider '{provider_id}' SDK not installed: {e}")
        except ValueError as e:
            logger.warning(f"LLM provider '{provider_id}' config error: {e}")
        except Exception as e:
            logger.warning(f"LLM provider '{provider_id}' init failed: {e}")

    logger.info("No LLM provider available. Reasoning will use heuristic-only mode.")
    return None
