"""Tests for benchmark grading and the evaluation runner (Nugen mocked)."""

from __future__ import annotations

import pytest

from apps.alignment import services
from apps.experts import services as expert_services
from apps.experts.fleet import FLEET, get_spec
from apps.experts.nugen_client import NugenError


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


@pytest.mark.parametrize("expert_key", list(FLEET))
def test_keys_cover_every_benchmark_question(expert_key):
    items, keys = services.load_benchmark(get_spec(expert_key))
    assert len(items) == 20
    assert all(str(i["question_num"]) in keys for i in items)


@pytest.mark.parametrize("expert_key", list(FLEET))
def test_gold_answers_score_well_against_their_own_keys(expert_key):
    """Sanity check on the keys: every gold answer must pass its own key."""
    items, keys = services.load_benchmark(get_spec(expert_key))
    for item in items:
        score, missing, _ = services.score_answer(item["answer"], keys[str(item["question_num"])])
        assert score >= services.PASS_THRESHOLD, (item["question_num"], missing)


@pytest.mark.parametrize("expert_key", list(FLEET))
def test_corpus_files_meet_nugen_minimum_words(expert_key):
    for path in get_spec(expert_key).corpus_paths:
        assert len(path.read_text(encoding="utf-8").split()) >= 500, path.name


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


def test_run_benchmark_retries_transient_errors(monkeypatch):
    attempts = []

    def flaky_answer(**kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise NugenError("Nugen stream interrupted", transient=True)
        return expert_services.ExpertAnswer(
            text="sorted O(n) O(n^2) pair",
            model_id="m",
            expert_key="dsa",
            grounded=False,
            confidence=None,
            confidence_min=None,
        )

    monkeypatch.setattr(expert_services, "answer", flaky_answer)
    monkeypatch.setattr(services, "RETRY_BACKOFF_SECONDS", 0)
    report = services.run_benchmark(
        spec=get_spec("dsa"), mode_names=["base"], aligned_model_id=None, limit=1, workers=1
    )
    item = report["modes"]["base"]["items"][0]
    assert len(attempts) == 2
    assert item["error"] is None and item["score"] == 1.0


def test_run_benchmark_requires_aligned_model_for_aligned_modes():
    with pytest.raises(ValueError):
        services.run_benchmark(spec=get_spec("dsa"), mode_names=["aligned"], aligned_model_id=None)
