"""Tests for the Nugen client parsing and the experts service layer.

No network: the client's HTTP layer is mocked. These guard the stream parsing
and model-resolution logic that the whole app depends on.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.test import override_settings

from apps.experts import services
from apps.experts.models import Expert, ExpertVersion
from apps.experts.nugen_client import (
    NugenClient,
    NugenError,
    _extract_delta,
    extract_full_text,
)


def test_extract_delta_streaming_shape():
    chunk = {"choices": [{"delta": {"content": "Hello"}}]}
    assert _extract_delta(chunk) == "Hello"


def test_extract_delta_message_shape():
    chunk = {"choices": [{"message": {"content": "World"}}]}
    assert _extract_delta(chunk) == "World"


def test_extract_delta_empty():
    assert _extract_delta({"choices": []}) == ""
    assert _extract_delta({}) == ""


def test_extract_full_text():
    resp = {"choices": [{"message": {"content": "Full answer"}}]}
    assert extract_full_text(resp) == "Full answer"


def test_chat_payload_puts_prompt_in_user_role():
    from apps.experts.nugen_client import ChatMessage

    payload = NugenClient._chat_payload(
        model="m",
        messages=[ChatMessage("system", "s"), ChatMessage("user", "q")],
        temperature=0.25,
        max_tokens=10,
        stream=False,
        extra=None,
    )
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert payload["model"] == "m"
    assert payload["stream"] is False


def test_chat_stream_parses_sse_lines():
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]
    fake_resp = mock.Mock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter(lines)

    client = NugenClient(api_key="k", base_url="https://api.nugen.in")
    with mock.patch.object(client._session, "request", return_value=fake_resp):
        out = list(
            client.chat_stream(
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
    assert "".join(out) == "Hello"


def test_error_hints():
    assert "401" in NugenError("x", status=401).hint
    assert "404" in NugenError("x", status=404).hint
    assert "504" in NugenError("x", status=504).hint


@pytest.mark.django_db
@override_settings(NUGEN_DEFAULT_MODEL="base-fallback-model")
def test_resolve_model_prefers_live_expert_then_default():
    # With no expert, falls back to the default model.
    assert services.resolve_model_id("dsa") == "base-fallback-model"

    expert = Expert.objects.create(key="dsa", lane="DSA")
    version = ExpertVersion.objects.create(
        expert=expert,
        semver="0.1.0",
        nugen_model_id="aligned-dsa-123",
        status=ExpertVersion.Status.LIVE,
    )
    expert.current_version = version
    expert.save(update_fields=["current_version"])

    assert services.resolve_model_id("dsa") == "aligned-dsa-123"


@pytest.mark.django_db
@override_settings(NUGEN_DEFAULT_MODEL="")
def test_resolve_model_raises_when_nothing_available():
    with pytest.raises(NugenError):
        services.resolve_model_id(None)


def test_ask_once_uses_service(monkeypatch):
    captured = {}

    def fake_chat(self, **kwargs):
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "answer"}}]}

    monkeypatch.setattr(NugenClient, "chat", fake_chat)
    with override_settings(NUGEN_DEFAULT_MODEL="m"):
        out = services.ask_once(prompt="q", system="s")
    assert out == "answer"
    assert captured["model"] == "m"
    assert captured["messages"][-1].content == "q"
