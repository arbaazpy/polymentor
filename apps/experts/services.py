"""Business logic for calling experts.

Views stay thin; all Nugen interaction, grounding, prompt construction and
model resolution lives here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.experts import grounding
from apps.experts.fleet import ExpertSpec, get_spec
from apps.experts.models import Expert, ExpertVersion
from apps.experts.nugen_client import ChatMessage, NugenClient, NugenError
from apps.experts.prompts import build_system_prompt

logger = logging.getLogger("polymentor.experts")


@dataclass
class ExpertAnswer:
    text: str
    model_id: str
    expert_key: str | None
    grounded: bool
    # Mean / min of Nugen's per-answer confidence frames, scaled to 0..1.
    confidence: float | None
    confidence_min: float | None
    sections: list[str] = field(default_factory=list)
    latency_ms: int = 0
    usage: dict[str, Any] = field(default_factory=dict)


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
    raise NugenError("No model available: no live expert version and NUGEN_DEFAULT_MODEL is unset.")


def prepare_messages(
    *,
    prompt: str,
    expert_key: str | None,
    grounded: bool = True,
    system: str | None = None,
) -> tuple[list[ChatMessage], list[grounding.Section]]:
    """Build the chat messages for an expert call.

    An explicit `system` overrides the lane prompt. Without an expert key the
    prompt is sent as-is (default-model smoke tests).
    """
    sections: list[grounding.Section] = []
    if system is None and expert_key:
        spec = get_spec(expert_key)
        if grounded:
            sections = grounding.retrieve(expert_key, prompt)
        system = build_system_prompt(spec, sections)
    messages: list[ChatMessage] = []
    if system:
        messages.append(ChatMessage(role="system", content=system))
    messages.append(ChatMessage(role="user", content=prompt))
    return messages, sections


def stream_answer(
    *,
    prompt: str,
    expert_key: str | None = None,
    grounded: bool = True,
    system: str | None = None,
    model_id: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> Iterator[dict[str, Any]]:
    """Stream an expert answer as events.

    Emits `meta` (model + grounding refs) first, then `delta` / `confidence`
    events from Nugen, and finally `done` with the aggregated confidence.
    """
    model = model_id or resolve_model_id(expert_key)
    messages, sections = prepare_messages(
        prompt=prompt, expert_key=expert_key, grounded=grounded, system=system
    )
    yield {
        "type": "meta",
        "model": model,
        "expert": expert_key,
        "sections": [s.ref for s in sections],
    }

    scores: list[float] = []
    for event in _client().chat_events(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    ):
        if event["type"] == "confidence":
            scores.append(event["score"])
        yield event
    yield {"type": "done", **_confidence_summary(scores)}


def answer(
    *,
    prompt: str,
    expert_key: str | None = None,
    grounded: bool = True,
    system: str | None = None,
    model_id: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> ExpertAnswer:
    """Collect a full expert answer (streams under the hood to avoid 504s)."""
    started = time.monotonic()
    parts: list[str] = []
    model, refs, usage = "", [], {}
    summary: dict[str, float | None] = {"confidence": None, "confidence_min": None}
    for event in stream_answer(
        prompt=prompt,
        expert_key=expert_key,
        grounded=grounded,
        system=system,
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        kind = event["type"]
        if kind == "meta":
            model, refs = event["model"], event["sections"]
        elif kind == "delta":
            parts.append(event["text"])
        elif kind == "usage":
            usage = event["usage"]
        elif kind == "done":
            summary = {"confidence": event["confidence"], "confidence_min": event["confidence_min"]}
    return ExpertAnswer(
        text="".join(parts).strip(),
        model_id=model,
        expert_key=expert_key,
        grounded=bool(refs),
        sections=refs,
        latency_ms=int((time.monotonic() - started) * 1000),
        usage=usage,
        **summary,
    )


def _confidence_summary(scores: list[float]) -> dict[str, float | None]:
    if not scores:
        return {"confidence": None, "confidence_min": None}
    return {
        "confidence": round(sum(scores) / len(scores) / 100, 4),
        "confidence_min": round(min(scores) / 100, 4),
    }


def register_live_version(*, spec: ExpertSpec, model_id: str) -> ExpertVersion:
    """Record a deployed Nugen model as the LIVE version of an expert lane."""
    with transaction.atomic():
        expert, _ = Expert.objects.update_or_create(
            key=spec.key,
            defaults={
                "lane": spec.lane,
                "description": spec.description,
                "owned_namespaces": spec.owned_namespaces,
            },
        )
        version = expert.versions.filter(nugen_model_id=model_id).first()
        if version is None:
            version = ExpertVersion.objects.create(
                expert=expert,
                semver=f"0.{expert.versions.count() + 1}.0",
                nugen_model_id=model_id,
                base_model=spec.base_model,
                status=ExpertVersion.Status.LIVE,
            )
        elif version.status != ExpertVersion.Status.LIVE:
            version.status = ExpertVersion.Status.LIVE
            version.save(update_fields=["status", "updated_at"])
        expert.current_version = version
        expert.save(update_fields=["current_version", "updated_at"])
    logger.info("expert %s -> %s (%s)", spec.key, version.semver, model_id)
    return version
