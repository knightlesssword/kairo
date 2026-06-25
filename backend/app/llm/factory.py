"""LLM provider factory.

selects a concrete LLMProvider from settings.llm_provider. v1 supports openrouter
(default) and ollama only; openai/anthropic are deferred to v2 and raise a clear
LLMError if selected (fail loud, no silent fallback).

two entry points used by services:
  get_answer_llm()     -> answer model (settings.llm_model); user-facing streaming
  get_extraction_llm() -> extraction model (settings.llm_extraction_model, falling
                          back to llm_model); cheap structured calls

both accept an optional settings override so tests can inject config without env.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.llm.base import LLMError, LLMProvider
from app.llm.openrouter import OpenRouterProvider

# providers whose interface exists in plan.md but is intentionally not shipped in v1.
# openrouter already proxies these models, so there is no v1 need.
_DEFERRED_TO_V2 = {"openai", "anthropic"}


def _build_provider(settings: Settings, model: str) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "openrouter":
        return OpenRouterProvider(api_key=settings.llm_api_key, model=model)
    if provider == "ollama":
        # lazy import: only load ollama code (and its deps) when actually selected,
        # so an openrouter-only deployment never imports it.
        from app.llm.ollama import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_base_url, model=model)
    if provider in _DEFERRED_TO_V2:
        raise LLMError(
            f"LLM_PROVIDER='{provider}' is deferred to v2; use 'openrouter' or 'ollama'"
        )
    raise LLMError(f"unknown LLM_PROVIDER='{provider}'")


def get_answer_llm(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if not settings.llm_model:
        raise LLMError("LLM_MODEL is not set")
    return _build_provider(settings, settings.llm_model)


def get_extraction_llm(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    model = settings.llm_extraction_model or settings.llm_model
    if not model:
        raise LLMError("neither LLM_EXTRACTION_MODEL nor LLM_MODEL is set")
    return _build_provider(settings, model)
