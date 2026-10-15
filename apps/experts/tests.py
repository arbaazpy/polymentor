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


def test_chat_stream_raises_on_embedded_error():
    """Undeployed models return HTTP 200 with an error frame; we must raise."""
    lines = [
        'data: {"error": {"message": "Nugen inference failed: Model not deployed", '
        '"type": "server_error", "code": 404}}',
        "",
    ]
    fake_resp = mock.Mock()
    fake_resp.status_code = 200
    fake_resp.iter_lines.return_value = iter(lines)

    client = NugenClient(api_key="k", base_url="https://api.nugen.in")
    with mock.patch.object(client._session, "request", return_value=fake_resp):
        with pytest.raises(NugenError) as excinfo:
            list(client.chat_stream(model="m", messages=[{"role": "user", "content": "hi"}]))
    assert excinfo.value.status == 404
    assert "not deployed" in str(excinfo.value).lower()


def test_error_hints():
    assert "401" in NugenError("x", status=401).hint
    assert "404" in NugenError("x", status=404).hint
    assert "504" in NugenError("x", status=504).hint


@pytest.mark.django_db
@override_settings(NUGEN_DEFAULT_MODEL="base-fallback-model")
def test_resolve_model_prefers_live_expert_then_default():
    # No DB version: the fleet manifest's committed model, then the env default.
    assert services.resolve_model_id("dsa") == "model_01m4zv707z9qzt7z"
    assert services.resolve_model_id(None) == "base-fallback-model"

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


def test_chat_events_surface_confidence_frames(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hi"}}]}',
        'data: {"object":"confidence","confidence_score":80.0}',
        'data: {"choices":[{"delta":{"content":"!"}}]}',
        'data: {"object":"confidence","confidence_score":90.0}',
        "data: [DONE]",
    ]

    def fake_request(self, *args, **kwargs):
        resp = mock.Mock(status_code=200)
        resp.iter_lines.return_value = iter(lines)
        return resp

    monkeypatch.setattr(NugenClient, "_request", fake_request)
    client = NugenClient(api_key="k")
    events = list(client.chat_events(model="m", messages=[]))
    assert [e["type"] for e in events] == ["delta", "confidence", "delta", "confidence"]
    assert events[1]["score"] == 80.0
    assert "".join(client.chat_stream(model="m", messages=[])) == "Hi!"


def test_stream_interrupted_mid_body_raises_retryable_nugen_error(monkeypatch):
    import requests

    def broken_lines():
        yield 'data: {"choices":[{"delta":{"content":"partial"}}]}'
        raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")

    def fake_request(self, *args, **kwargs):
        resp = mock.Mock(status_code=200)
        resp.iter_lines.return_value = broken_lines()
        return resp

    monkeypatch.setattr(NugenClient, "_request", fake_request)
    with pytest.raises(NugenError) as excinfo:
        list(NugenClient(api_key="k").chat_events(model="m", messages=[]))
    assert excinfo.value.retryable
    assert not NugenError("bad", status=404).retryable


def test_answer_grounds_prompt_and_averages_confidence(monkeypatch):
    captured = {}

    def fake_events(self, **kwargs):
        captured.update(kwargs)
        yield {"type": "delta", "text": "Use l = mid + 1."}
        yield {"type": "confidence", "score": 70.0}
        yield {"type": "confidence", "score": 90.0}

    monkeypatch.setattr(NugenClient, "chat_events", fake_events)
    result = services.answer(
        prompt="My binary search with l = mid loops forever. Why?",
        expert_key="dsa",
        model_id="aligned-dsa",
    )
    system = captured["messages"][0].content
    assert captured["model"] == "aligned-dsa"
    assert "Reference notes:" in system
    assert "DELEGATE:" in system
    assert result.text == "Use l = mid + 1."
    assert result.confidence == 0.8
    assert result.confidence_min == 0.7
    assert result.grounded and any("Failure modes" in ref for ref in result.sections)


def test_answer_ungrounded_has_rules_but_no_notes(monkeypatch):
    captured = {}

    def fake_events(self, **kwargs):
        captured.update(kwargs)
        yield {"type": "delta", "text": "ok"}

    monkeypatch.setattr(NugenClient, "chat_events", fake_events)
    result = services.answer(prompt="q", expert_key="dsa", grounded=False, model_id="m")
    system = captured["messages"][0].content
    assert "DELEGATE:" in system and "Reference notes:" not in system
    assert result.confidence is None and not result.grounded


@pytest.mark.django_db
def test_register_live_version_is_idempotent():
    from apps.experts.fleet import get_spec

    spec = get_spec("dsa")
    first = services.register_live_version(spec=spec, model_id="model_x")
    again = services.register_live_version(spec=spec, model_id="model_x")
    assert first.pk == again.pk
    expert = Expert.objects.get(key="dsa")
    assert expert.current_version_id == first.pk
    assert services.resolve_model_id("dsa") == "model_x"
