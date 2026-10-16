"""Aggregator tests: claims, reconciliation, and full turns with Nugen mocked."""

from __future__ import annotations

import json

import pytest
from django.test import override_settings

from apps.aggregation import services as agg
from apps.experts import services as expert_services
from apps.experts.nugen_client import NugenError
from apps.sessions.models import Turn


def _answer(text, lane="dsa", confidence=0.8):
    return expert_services.ExpertAnswer(
        text=text,
        model_id="m",
        expert_key=lane,
        grounded=True,
        confidence=confidence,
        confidence_min=confidence,
        sections=["corpus.md#x"],
    )


def test_extract_and_strip_claims():
    text = 'Use base62. [[claim id="hash.length"]]Use 8-char codes.[[/claim]] Done.'
    claims = agg.extract_claims(text, "dsa")
    assert [(c.id, c.text, c.owner) for c in claims] == [
        ("hash.length", "Use 8-char codes.", "dsa")
    ]
    assert agg.strip_claim_tags(text) == "Use base62. Use 8-char codes. Done."


def test_untagged_decisions_are_extracted_from_prose():
    sysdes = (
        "**Claim id: 1** [[architecture]]: Store mappings in PostgreSQL behind a cache. "
        "Peak is about 35k QPS. Generate 7-character base62 codes."
    )
    claims = {c.id: c for c in agg.extract_claims(sysdes, "sysdes")}
    assert claims["arch.datastore"].value == "postgres"
    assert claims["scale.qps"].value == "35k"
    assert claims["hash.length"].value == "7"
    assert claims["hash.length"].text == "Generate 7-character base62 codes."
    assert "[[" not in agg.strip_claim_tags(sysdes)


def test_reconcile_marks_agreement_and_conflict():
    dsa = agg.extract_claims("Random codes need 8 characters to keep collisions low.", "dsa")
    sysdes = agg.extract_claims("Use 7-char codes. Cassandra stores them.", "sysdes")
    behav = agg.extract_claims("Pick Cassandra and ship.", "behav")
    notes = {n["claim_id"]: n for n in agg.reconcile(dsa + sysdes + behav)}
    assert notes["hash.length"]["agreed"] is False
    assert notes["hash.length"]["winner"] == "dsa"
    assert notes["arch.datastore"]["agreed"] is True
    assert notes["arch.datastore"]["rule"] == "all lanes agree (cassandra)"


def test_reconcile_owner_wins_and_unowned_conflict_is_surfaced():
    claims = [
        agg.Claim("hash.length", "7 chars is plenty", "sysdes"),
        agg.Claim("hash.length", "use 8 chars or a counter", "dsa"),
        agg.Claim("framing.scope", "ship redirects first", "sysdes"),
        agg.Claim("framing.scope", "cut analytics", "dsa"),
    ]
    notes = {n["claim_id"]: n for n in agg.reconcile(claims)}
    assert notes["hash.length"]["winner"] == "dsa"
    assert notes["hash.length"]["resolved_text"] == "use 8 chars or a counter"
    assert notes["framing.scope"]["winner"] is None
    assert "left unresolved" in notes["framing.scope"]["rule"]


@pytest.mark.django_db
def test_collaborative_turn_reconciles_and_synthesizes(monkeypatch):
    replies = {
        "sysdes": 'Counter ids. [[claim id="hash.length"]]7-char base62 codes.[[/claim]]',
        "dsa": '[[claim id="hash.length"]]Hashed codes need 8 chars.[[/claim]]',
        "behav": "Ship redirects first on Cassandra; cut analytics.",
    }
    replies["sysdes"] += " Store mappings in Cassandra."

    def fake_answer(**kwargs):
        assert kwargs["collaborative"] is True
        return _answer(replies[kwargs["expert_key"]], lane=kwargs["expert_key"])

    monkeypatch.setattr(expert_services, "answer", fake_answer)
    monkeypatch.setattr(agg, "synthesize", lambda prompt, experts, notes: iter(["- plan [dsa]"]))
    events = list(agg.run_turn("Design a URL shortener for 1B redirects/day. 2 weeks to ship."))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "route" and kinds[-1] == "done"
    recon = {
        n["claim_id"]: n for n in next(e for e in events if e["type"] == "reconciliation")["notes"]
    }
    assert recon["hash.length"]["winner"] == "dsa"
    assert recon["arch.datastore"]["agreed"] is True
    turn = Turn.objects.get()
    assert turn.synthesis == "- plan [dsa]"
    assert turn.status == Turn.Status.OK
    assert {e["lane"] for e in turn.experts} == {"sysdes", "dsa", "behav"}


def test_expert_retries_transient_failure_once(monkeypatch):
    calls = []

    def flaky(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise NugenError("stream dropped", transient=True)
        return _answer("Use l = mid + 1.")

    monkeypatch.setattr(expert_services, "answer", flaky)
    entry = agg._ask_expert(
        "dsa", "q", model_id="m", version="0.1.0", collaborative=False, exemplars=[]
    )
    assert entry["status"] == "answered" and len(calls) == 2

    monkeypatch.setattr(
        expert_services, "answer", lambda **kw: (_ for _ in ()).throw(NugenError("bad", 400))
    )
    entry = agg._ask_expert(
        "dsa", "q", model_id="m", version="0.1.0", collaborative=False, exemplars=[]
    )
    assert entry["status"] == "error"


@pytest.mark.django_db
def test_single_lane_vetoed_delegation_becomes_not_covered(monkeypatch):
    monkeypatch.setattr(
        expert_services,
        "answer",
        lambda **kw: _answer("DELEGATE: sysdes - system design", lane=kw["expert_key"]),
    )
    events = list(agg.run_turn("Explain the details of Dinic's maximum-flow algorithm."))
    delegation = next(e for e in events if e["type"] == "delegation")
    assert delegation == delegation | {"from": "dsa", "to": "sysdes", "honoured": False}
    expert = [e for e in events if e["type"] == "expert"][-1]
    assert expert["status"] == "abstained" and "Not covered" in expert["text"]


@pytest.mark.django_db
def test_single_lane_honoured_delegation_redispatches(monkeypatch):
    def fake_answer(**kwargs):
        if kwargs["expert_key"] == "behav":
            return _answer("DELEGATE: sysdes - design question", lane="behav")
        return _answer("Use a token bucket in Redis.", lane=kwargs["expert_key"])

    monkeypatch.setattr(expert_services, "answer", fake_answer)
    monkeypatch.setattr(
        agg.routing,
        "route",
        lambda prompt: agg.routing.RouteDecision(
            lanes=["behav"], scores={"behav": 1.0, "sysdes": 2.0}, hints={"sysdes": ["rate limit"]}
        ),
    )
    events = list(agg.run_turn("rate limit design"))
    experts = [e for e in events if e["type"] == "expert"]
    assert [e["status"] for e in experts] == ["delegated", "answered"]
    assert experts[-1]["lane"] == "sysdes"


@pytest.mark.django_db
@override_settings(TURN_RATE_LIMIT=1)
def test_turn_stream_endpoint_streams_and_rate_limits(client, monkeypatch):
    monkeypatch.setattr(expert_services, "answer", lambda **kw: _answer("Use two pointers."))
    url = "/v1/turns/stream"
    body = json.dumps({"prompt": "Explain the two-pointer pattern for sorted arrays."})
    resp = client.post(url, body, content_type="application/json")
    assert resp.status_code == 200
    frames = b"".join(resp.streaming_content).decode()
    assert '"type": "done"' in frames
    again = client.post(url, body, content_type="application/json")
    assert again.status_code == 429


@pytest.mark.django_db
def test_pages_render(client, monkeypatch):
    monkeypatch.setattr(expert_services, "answer", lambda **kw: _answer("Use two pointers."))
    list(agg.run_turn("Explain the two-pointer pattern."))
    turn = Turn.objects.get()
    assert client.get("/").status_code == 200
    assert client.get(f"/t/{turn.pk}").status_code == 200
    assert client.get("/experts").status_code == 200
