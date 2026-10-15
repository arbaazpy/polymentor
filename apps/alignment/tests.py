"""Tests for benchmark grading and the evaluation runner (Nugen mocked)."""

from __future__ import annotations

import pytest

from apps.alignment import services
from apps.experts import services as expert_services
from apps.experts.fleet import get_spec


def test_score_answer_counts_groups():
    key = {"groups": [["sorted", "monoton"], ["o(n)"], ["o(n^2)", "quadratic"]]}
    score, missing, forbidden = services.score_answer("Works on SORTED input, O(n²) -> O(n).", key)
    assert score == 1.0 and missing == [] and forbidden is None

    score, missing, _ = services.score_answer("Use two indices.", key)
    assert score == 0.0 and len(missing) == 3


def test_score_answer_forbidden_phrase_zeroes_abstention_item():
    key = {"groups": [["delegate", "system design"]], "forbid": ["token bucket"]}
    assert services.score_answer("DELEGATE: sysdes - system design question", key)[0] == 1.0
    score, _, forbidden = services.score_answer("This is system design; use a token bucket.", key)
    assert score == 0.0 and forbidden == "token bucket"


def test_dsa_keys_cover_every_benchmark_question():
    items, keys = services.load_benchmark(get_spec("dsa"))
    assert len(items) == 20
    assert all(str(i["question_num"]) in keys for i in items)


def test_gold_answers_score_well_against_their_own_keys():
    """Sanity check on the keys: the gold answers should pass (abstention items aside)."""
    items, keys = services.load_benchmark(get_spec("dsa"))
    for item in items:
        score, missing, _ = services.score_answer(item["answer"], keys[str(item["question_num"])])
        assert score >= services.PASS_THRESHOLD, (item["question_num"], missing)


def test_run_benchmark_reports_each_mode(monkeypatch):
    calls = []

    def fake_answer(**kwargs):
        calls.append(kwargs)
        text = "sorted monotonic O(n) O(n^2) pair" if kwargs["grounded"] else "no idea"
        return expert_services.ExpertAnswer(
            text=text,
            model_id=kwargs["model_id"],
            expert_key="dsa",
            grounded=kwargs["grounded"],
            confidence=0.9 if kwargs["grounded"] else 0.4,
            confidence_min=0.5,
            latency_ms=10,
        )

    monkeypatch.setattr(expert_services, "answer", fake_answer)
    report = services.run_benchmark(
        spec=get_spec("dsa"),
        mode_names=["aligned", "aligned_grounded"],
        aligned_model_id="aligned-x",
        limit=1,
        workers=1,
    )
    assert {c["model_id"] for c in calls} == {"aligned-x"}
    assert report["modes"]["aligned"]["summary"]["overall"] == 0.0
    assert report["modes"]["aligned_grounded"]["summary"]["overall"] == 1.0
    assert report["modes"]["aligned_grounded"]["summary"]["confidence_when_pass"] == 0.9
    assert "`aligned_grounded`" in services.render_markdown(report)


def test_run_benchmark_requires_aligned_model_for_aligned_modes():
    with pytest.raises(ValueError):
        services.run_benchmark(spec=get_spec("dsa"), mode_names=["aligned"], aligned_model_id=None)
