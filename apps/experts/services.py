"""Business logic for calling experts.

Views stay thin; all Nugen interaction and model resolution lives here.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from django.conf import settings

from apps.experts.models import Expert
from apps.experts.nugen_client import ChatMessage, NugenClient, NugenError, extract_full_text

logger = logging.getLogger("polymentor.experts")


def _client() -> NugenClient:
    return NugenClient()


def resolve_model_id(expert_key: str | None = None) -> str:
    """Resolve which Nugen model to call.

    Preference order:
      1. The live version of the requested expert lane.
      2. The NUGEN_DEFAULT_MODEL env fallback (used for smoke tests before any
         experts are aligned/deployed).
    """
    if expert_key:
        expert = Expert.objects.filter(key=expert_key).select_related("current_version").first()
        if expert and expert.current_version and expert.current_version.nugen_model_id:
            return expert.current_version.nugen_model_id
    if settings.NUGEN_DEFAULT_MODEL:
        return settings.NUGEN_DEFAULT_MODEL
    raise NugenError(
        "No model available: no live expert version and NUGEN_DEFAULT_MODEL is unset."
    )


def ask_once(
    *,
    prompt: str,
    expert_key: str | None = None,
    system: str | None = None,
    temperature: float = 0.25,
    max_tokens: int = 512,
) -> str:
    """Single non-streaming inference call. Returns the full answer text."""
    model = resolve_model_id(expert_key)
    messages = _build_messages(system, prompt)
    response = _client().chat(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return extract_full_text(response)


def ask_stream(
    *,
    prompt: str,
    expert_key: str | None = None,
    system: str | None = None,
    temperature: float = 0.25,
    max_tokens: int = 512,
) -> Iterator[str]:
    """Streaming inference. Yields text deltas."""
    model = resolve_model_id(expert_key)
    messages = _build_messages(system, prompt)
    yield from _client().chat_stream(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _build_messages(system: str | None, prompt: str) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    if system:
        messages.append(ChatMessage(role="system", content=system))
    messages.append(ChatMessage(role="user", content=prompt))
    return messages
