"""Router tests: lane selection and delegation arbitration (no network)."""

from __future__ import annotations

import pytest

from apps.routing import services as routing


@pytest.mark.parametrize(
    ("prompt", "primary"),
    [
        ("What is the time complexity of Dijkstra's algorithm with a binary heap?", "dsa"),
        ("Design a horizontally scalable rate limiter for our API.", "sysdes"),
        ("Tell me about a time you resolved a conflict with a teammate.", "behav"),
        ("Rewrite this resume bullet: 'Worked on the payments service.'", "resume"),
        ("Grill me with a mock system design question.", "mock"),
    ],
)
def test_route_picks_expected_primary_lane(prompt, primary):
    assert routing.route(prompt, use_llm_fallback=False).primary == primary


def test_hero_prompt_is_split_across_lanes():
    decision = routing.route(
        "Design a URL shortener for 1B redirects/day. I have 2 weeks to ship.",
        use_llm_fallback=False,
    )
    assert decision.primary == "sysdes"
    assert decision.collaborative
    assert {"dsa", "behav"} <= set(decision.lanes)


def test_no_keywords_uses_coordinator(monkeypatch):
    monkeypatch.setattr(routing, "_classify_with_coordinator", lambda prompt: ["behav"])
    decision = routing.route("hmm, any thoughts?")
    assert decision.lanes == ["behav"] and decision.method == "coordinator-llm"


def test_parse_delegation_variants():
    assert routing.parse_delegation("DELEGATE: sysdes - scaling question") == "sysdes"
    assert routing.parse_delegation("**DELEGATE:** dsa - complexity") == "dsa"
    assert routing.parse_delegation("delegate: nobody") is None
    assert routing.parse_delegation("Use two pointers.") is None


def test_in_domain_delegation_is_vetoed():
    prompt = "Explain the details of Dinic's maximum-flow algorithm."
    decision = routing.route(prompt, use_llm_fallback=False)
    honour, reason = routing.arbitrate_delegation("dsa", "sysdes", decision, prompt)
    assert not honour and "stays with dsa" in reason


def test_cross_lane_delegation_is_honoured():
    prompt = "Design a horizontally scalable rate limiter for an API."
    decision = routing.route(prompt, use_llm_fallback=False)
    honour, _ = routing.arbitrate_delegation("dsa", "sysdes", decision, prompt)
    assert honour
