"""Learning-loop tests: feedback -> exemplars -> grounding, and the eval gate."""

from __future__ import annotations

import json

import pytest

from apps.alignment.services import gate_decision
from apps.experts import grounding
from apps.feedback import services
from apps.feedback.models import Feedback, LearnedExemplar
from apps.sessions.models import Turn


def _turn():
    return Turn.objects.create(
        prompt="Why does my binary search with l = mid loop forever?",
        route={"primary": "dsa", "lanes": ["dsa"]},
        experts=[{"lane": "dsa", "status": "answered", "text": "Use l = mid + 1."}],
    )


@pytest.mark.django_db
def test_feedback_mining_creates_exemplars_and_grounding_uses_them():
    turn = _turn()
    services.record_feedback(
        turn=turn,
        rating=-1,
        expert_key="dsa",
        correction="Floor rounding means l never advances; use l = mid + 1 so the range shrinks.",
    )
    services.record_feedback(turn=turn, rating=1, expert_key="dsa")
    services.record_feedback(turn=turn, rating=-1)  # no correction: skipped
    assert services.mine_feedback() == {"created": 2, "skipped": 1}
    assert services.mine_feedback() == {"created": 0, "skipped": 0}

    assert services.exemplar_sections("dsa") == []  # pending until reviewed
    LearnedExemplar.objects.update(status=LearnedExemplar.Status.APPROVED)
    learned = services.exemplar_sections("dsa")
    hits = grounding.retrieve("dsa", "binary search l = mid loops forever", extra=learned)
    assert hits[0].source == "learned"

    health = {h["lane"]: h for h in services.lane_health()}["dsa"]
    assert health["up"] == 1 and health["down"] == 1 and health["approved_exemplars"] == 2


@pytest.mark.django_db
def test_record_feedback_validates_expert_and_rating():
    turn = _turn()
    with pytest.raises(ValueError):
        services.record_feedback(turn=turn, rating=1, expert_key="sysdes")
    with pytest.raises(ValueError):
        services.record_feedback(turn=turn, rating=5)


@pytest.mark.django_db
def test_feedback_endpoint(client):
    turn = _turn()
    resp = client.post(
        f"/v1/turns/{turn.pk}/feedback",
        json.dumps({"rating": 1, "expert": "dsa"}),
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert Feedback.objects.count() == 1


def test_gate_blocks_regressions_and_passes_improvements():
    current = {"overall": 0.80, "by_category": {"abstention": 0.5}, "errors": 0}
    better = {"overall": 0.85, "by_category": {"abstention": 0.5}, "errors": 0}
    worse_abstention = {"overall": 0.90, "by_category": {"abstention": 0.25}, "errors": 0}
    assert gate_decision(better, current).passed
    assert not gate_decision(worse_abstention, current).passed
    assert not gate_decision({**better, "overall": 0.7}, current).passed
    assert not gate_decision({**better, "errors": 2}, current).passed
    assert gate_decision(better, None).passed
