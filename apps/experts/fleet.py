"""PolyMentor expert fleet manifest.

Single source of truth mapping each lane to its base model, corpus files, gold
benchmark, the sub-claim namespaces it owns (used by the aggregator's
lane-ownership reconciliation), and the deployed Nugen model that serves it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

CORPORA_DIR = Path(settings.BASE_DIR) / "corpora"
BENCHMARKS_DIR = Path(settings.BASE_DIR) / "benchmarks"

# Must be both alignment_ready and inference_ready on Nugen. Qwen2.5-3B is
# alignment-ready only and cannot host aligned adapters.
LLAMA_3B = "meta-llama/Llama-3.2-3B-Instruct"


@dataclass(frozen=True)
class ExpertSpec:
    key: str
    lane: str
    description: str
    base_model: str
    corpus_files: list[str]
    benchmark_file: str = ""
    owned_namespaces: list[str] = field(default_factory=list)
    # Local grading keys for the gold benchmark (not uploaded to Nugen).
    benchmark_keys_file: str = ""
    # Deployed Nugen model seeded by `sync_experts` (aligned id, or the base
    # model for grounded-only lanes). The DB's LIVE version takes precedence.
    live_model_id: str = ""
    # One-line focus used when the router splits a request across lanes.
    focus: str = ""

    @property
    def aligned(self) -> bool:
        return bool(self.live_model_id) and self.live_model_id != self.base_model

    @property
    def corpus_paths(self) -> list[Path]:
        return [CORPORA_DIR / f for f in self.corpus_files]

    @property
    def benchmark_path(self) -> Path | None:
        return BENCHMARKS_DIR / self.benchmark_file if self.benchmark_file else None

    @property
    def benchmark_keys_path(self) -> Path | None:
        return BENCHMARKS_DIR / self.benchmark_keys_file if self.benchmark_keys_file else None


FLEET: dict[str, ExpertSpec] = {
    "dsa": ExpertSpec(
        key="dsa",
        lane="Data Structures & Algorithms",
        description=(
            "Complexity analysis, interview patterns (two-pointer, sliding window, "
            "prefix sums, binary search on the answer, BFS/DFS, DP, union-find), "
            "hashing and collision math, and common implementation bugs."
        ),
        base_model=LLAMA_3B,
        corpus_files=["dsa/corpus.md", "dsa/quickref.txt"],
        benchmark_file="dsa.json",
        benchmark_keys_file="dsa.keys.json",
        owned_namespaces=["complexity", "pattern", "hash", "ds"],
        live_model_id="model_01m4zv707z9qzt7z",
        focus="algorithms, data structures, hashing and collision math, complexity",
    ),
    "sysdes": ExpertSpec(
        key="sysdes",
        lane="System Design",
        description=(
            "Scalability, caching, consistency models, partitioning and replication, "
            "queues, idempotency, back-pressure, rate limiting, and the classic "
            "interview designs (URL shortener, newsfeed, rate limiter, chat)."
        ),
        base_model=LLAMA_3B,
        corpus_files=["sysdes/corpus.md", "sysdes/quickref.txt"],
        benchmark_file="sysdes.json",
        benchmark_keys_file="sysdes.keys.json",
        owned_namespaces=["arch", "storage", "cache", "consistency", "scale", "queue", "api"],
        live_model_id="model_01m4zyvrxn5f988a",
        focus="architecture, capacity estimates, storage, caching, scaling and reliability",
    ),
    "behav": ExpertSpec(
        key="behav",
        lane="Behavioral Interviews",
        description=(
            "STAR stories, the eight situational buckets, the four-criterion story "
            "rubric, red and green flags, interviewer probes, and scoping and "
            "stakeholder framing."
        ),
        base_model=LLAMA_3B,
        corpus_files=["behav/corpus.md", "behav/quickref.txt"],
        benchmark_file="behav.json",
        benchmark_keys_file="behav.keys.json",
        owned_namespaces=["story", "framing", "stakeholder"],
        live_model_id="model_01m50db0jrcphjrw",
        focus="scoping, prioritization, stakeholder framing and how to tell the story",
    ),
    # Grounded-only lanes: served by the base model plus corpus grounding.
    "resume": ExpertSpec(
        key="resume",
        lane="Resume & JD Fit",
        description=(
            "Bullet impact (verb + artifact + metric), seniority signals, "
            "job-description fit, and resume red flags."
        ),
        base_model=LLAMA_3B,
        corpus_files=["resume/corpus.md"],
        owned_namespaces=["resume", "fit"],
        live_model_id=LLAMA_3B,
        focus="resume bullets, job-description fit and seniority signals",
    ),
    "mock": ExpertSpec(
        key="mock",
        lane="Mock Interviewer",
        description=(
            "Runs mock interviews: picks questions, asks follow-ups, and scores "
            "answers against a rubric."
        ),
        base_model=LLAMA_3B,
        corpus_files=["mock/corpus.md"],
        owned_namespaces=["rubric", "question"],
        live_model_id=LLAMA_3B,
        focus="interview questions to practise and how answers will be scored",
    ),
}

# The coordinator ("mother") model: lane classification fallback and synthesis.
COORDINATOR_MODEL = LLAMA_3B


def get_spec(key: str) -> ExpertSpec:
    try:
        return FLEET[key]
    except KeyError as exc:
        raise KeyError(f"Unknown expert '{key}'. Known: {', '.join(FLEET)}") from exc


def benchmarked_experts() -> list[str]:
    return [k for k, s in FLEET.items() if s.benchmark_file and s.benchmark_keys_file]


def namespace_owner(claim_id: str) -> str | None:
    namespace = claim_id.split(".", 1)[0]
    for spec in FLEET.values():
        if namespace in spec.owned_namespaces:
            return spec.key
    return None
