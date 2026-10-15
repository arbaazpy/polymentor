"""Benchmark evaluation for expert versions.

Runs an expert's gold benchmark against several configurations so we can see
what each layer contributes:

    base              base model, lane prompt, no notes
    base_grounded     base model, lane prompt + retrieved corpus notes
    aligned           Nugen domain-aligned model, lane prompt, no notes
    aligned_grounded  aligned model + retrieved notes (production config)

Grading is deterministic keyword-group matching against `<expert>.keys.json`
so runs are reproducible and cheap; no LLM-as-judge.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from django.utils import timezone

from apps.experts import services as expert_services
from apps.experts.fleet import ExpertSpec
from apps.experts.nugen_client import NugenError

PASS_THRESHOLD = 0.75
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0


@dataclass(frozen=True)
class Mode:
    name: str
    aligned: bool
    grounded: bool


MODES: dict[str, Mode] = {
    m.name: m
    for m in (
        Mode("base", aligned=False, grounded=False),
        Mode("base_grounded", aligned=False, grounded=True),
        Mode("aligned", aligned=True, grounded=False),
        Mode("aligned_grounded", aligned=True, grounded=True),
    )
}


@dataclass
class ItemResult:
    question_num: int
    category: str
    score: float
    missing: list[list[str]] = field(default_factory=list)
    forbidden_hit: str | None = None
    answer: str = ""
    confidence: float | None = None
    latency_ms: int = 0
    error: str | None = None


def normalize(text: str) -> str:
    text = text.lower().replace("²", "^2").replace("−", "-")
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[`*_]", "", text)
    return re.sub(r"\s+", " ", text)


def score_answer(text: str, key: dict[str, Any]) -> tuple[float, list[list[str]], str | None]:
    """Return (score, missing groups, forbidden phrase hit)."""
    norm = normalize(text)
    for phrase in key.get("forbid", []):
        if normalize(phrase) in norm:
            return 0.0, key["groups"], phrase
    groups = key["groups"]
    missing = [g for g in groups if not any(normalize(alt) in norm for alt in g)]
    return round((len(groups) - len(missing)) / len(groups), 4), missing, None


def load_benchmark(spec: ExpertSpec) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if spec.benchmark_keys_path is None:
        raise ValueError(f"expert.{spec.key} has no benchmark_keys_file configured")
    items = json.loads(spec.benchmark_path.read_text(encoding="utf-8"))
    keys = json.loads(spec.benchmark_keys_path.read_text(encoding="utf-8"))["items"]
    missing = [str(i["question_num"]) for i in items if str(i["question_num"]) not in keys]
    if missing:
        raise ValueError(f"No grading keys for questions: {', '.join(missing)}")
    return items, keys


def _run_item(
    spec: ExpertSpec,
    mode: Mode,
    model_id: str,
    item: dict[str, Any],
    key: dict[str, Any],
    max_tokens: int,
) -> ItemResult:
    result = ItemResult(question_num=item["question_num"], category=key["category"], score=0.0)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = expert_services.answer(
                prompt=item["question"],
                expert_key=spec.key,
                grounded=mode.grounded,
                model_id=model_id,
                temperature=0.0,
                max_tokens=max_tokens,
            )
            break
        except NugenError as exc:
            if exc.retryable and attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            result.error = str(exc)
            return result
    result.score, result.missing, result.forbidden_hit = score_answer(reply.text, key)
    result.answer = reply.text
    result.confidence = reply.confidence
    result.latency_ms = reply.latency_ms
    return result


def summarize(results: list[ItemResult]) -> dict[str, Any]:
    by_category: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r.score)
    passed = [
        r.confidence for r in results if r.confidence is not None and r.score >= PASS_THRESHOLD
    ]
    failed = [
        r.confidence for r in results if r.confidence is not None and r.score < PASS_THRESHOLD
    ]
    latencies = [r.latency_ms for r in results if not r.error]
    return {
        "overall": round(statistics.fmean(r.score for r in results), 4) if results else 0.0,
        "pass_rate": round(sum(r.score >= PASS_THRESHOLD for r in results) / len(results), 4)
        if results
        else 0.0,
        "by_category": {c: round(statistics.fmean(s), 4) for c, s in sorted(by_category.items())},
        "confidence_when_pass": round(statistics.fmean(passed), 4) if passed else None,
        "confidence_when_fail": round(statistics.fmean(failed), 4) if failed else None,
        "p50_latency_ms": int(statistics.median(latencies)) if latencies else None,
        "errors": sum(1 for r in results if r.error),
    }


def run_benchmark(
    *,
    spec: ExpertSpec,
    mode_names: list[str],
    aligned_model_id: str | None,
    limit: int | None = None,
    workers: int = 4,
    max_tokens: int = 400,
    on_item: Callable[[str, ItemResult], None] | None = None,
) -> dict[str, Any]:
    items, keys = load_benchmark(spec)
    if limit:
        items = items[:limit]
    modes = [MODES[name] for name in mode_names]
    if any(m.aligned for m in modes) and not aligned_model_id:
        raise ValueError("aligned modes need an aligned model id (register the expert or pass one)")

    report: dict[str, Any] = {
        "expert": spec.key,
        "created_at": timezone.now().isoformat(timespec="seconds"),
        "models": {"base": spec.base_model, "aligned": aligned_model_id},
        "pass_threshold": PASS_THRESHOLD,
        "num_questions": len(items),
        "modes": {},
    }
    for mode in modes:
        model_id = aligned_model_id if mode.aligned else spec.base_model
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _run_item,
                    spec,
                    mode,
                    model_id,
                    item,
                    keys[str(item["question_num"])],
                    max_tokens,
                )
                for item in items
            ]
            results = []
            for future in futures:
                result = future.result()
                if on_item:
                    on_item(mode.name, result)
                results.append(result)
        report["modes"][mode.name] = {
            "model": model_id,
            "grounded": mode.grounded,
            "summary": summarize(results),
            "items": [asdict(r) for r in results],
        }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    categories = sorted({c for m in report["modes"].values() for c in m["summary"]["by_category"]})
    header = ["mode", "overall", "pass rate", *categories, "conf (pass)", "conf (fail)", "p50 ms"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]

    def fmt(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}"

    for name, mode in report["modes"].items():
        s = mode["summary"]
        row = [
            f"`{name}`",
            fmt(s["overall"]),
            fmt(s["pass_rate"]),
            *(fmt(s["by_category"].get(c)) for c in categories),
            fmt(s["confidence_when_pass"]),
            fmt(s["confidence_when_fail"]),
            str(s["p50_latency_ms"] or "-"),
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
