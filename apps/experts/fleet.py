"""PolyMentor expert fleet manifest.

Single source of truth mapping each lane to its base model, corpus files, gold
benchmark, and the sub-claim namespaces it owns (used later by the aggregator's
lane-ownership reconciliation). The bootstrap command reads this to upload,
align, and deploy each expert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

CORPORA_DIR = Path(settings.BASE_DIR) / "corpora"
BENCHMARKS_DIR = Path(settings.BASE_DIR) / "benchmarks"


@dataclass(frozen=True)
class ExpertSpec:
    key: str
    lane: str
    description: str
    base_model: str
    corpus_files: list[str]
    benchmark_file: str
    owned_namespaces: list[str] = field(default_factory=list)
    # Local grading keys for the gold benchmark (not uploaded to Nugen).
    benchmark_keys_file: str = ""

    @property
    def corpus_paths(self) -> list[Path]:
        return [CORPORA_DIR / f for f in self.corpus_files]

    @property
    def benchmark_path(self) -> Path:
        return BENCHMARKS_DIR / self.benchmark_file

    @property
    def benchmark_keys_path(self) -> Path | None:
        return BENCHMARKS_DIR / self.benchmark_keys_file if self.benchmark_keys_file else None


# v1 fleet. More lanes are added as their corpora land.
FLEET: dict[str, ExpertSpec] = {
    "dsa": ExpertSpec(
        key="dsa",
        lane="Data Structures & Algorithms",
        description=(
            "Complexity analysis, interview patterns (two-pointer, sliding window, "
            "prefix sums, binary search on the answer, BFS/DFS, DP, union-find), and "
            "common implementation bugs."
        ),
        # Must be both alignment_ready and inference_ready.
        # Qwen2.5-3B is alignment-ready only and cannot host aligned adapters.
        base_model="meta-llama/Llama-3.2-3B-Instruct",
        corpus_files=["dsa/corpus.md", "dsa/quickref.txt"],
        benchmark_file="dsa.json",
        benchmark_keys_file="dsa.keys.json",
        owned_namespaces=["complexity", "pattern", "hash", "ds"],
    ),
    "sysdes": ExpertSpec(
        key="sysdes",
        lane="System Design",
        description=(
            "Scalability, caching, consistency models, partitioning and replication, "
            "queues, idempotency, back-pressure, rate limiting, and the classic "
            "interview designs (URL shortener, newsfeed, rate limiter, chat)."
        ),
        base_model="meta-llama/Llama-3.2-3B-Instruct",
        corpus_files=["sysdes/corpus.md", "sysdes/quickref.txt"],
        benchmark_file="sysdes.json",
        benchmark_keys_file="sysdes.keys.json",
        owned_namespaces=["arch", "storage", "cache", "consistency", "scale", "queue", "api"],
    ),
    "behav": ExpertSpec(
        key="behav",
        lane="Behavioral Interviews",
        description=(
            "STAR stories, the eight situational buckets, the four-criterion story "
            "rubric, red and green flags, interviewer probes, and scoping and "
            "stakeholder framing."
        ),
        base_model="meta-llama/Llama-3.2-3B-Instruct",
        corpus_files=["behav/corpus.md", "behav/quickref.txt"],
        benchmark_file="behav.json",
        benchmark_keys_file="behav.keys.json",
        owned_namespaces=["story", "framing", "stakeholder"],
    ),
}


def get_spec(key: str) -> ExpertSpec:
    try:
        return FLEET[key]
    except KeyError as exc:
        raise KeyError(f"Unknown expert '{key}'. Known: {', '.join(FLEET)}") from exc
