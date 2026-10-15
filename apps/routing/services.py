"""Router: decide which expert lanes handle a request.

Scoring is deterministic and cheap: lane keyword hints plus BM25 relevance of
the request against each lane's own corpus. Only when no lane shows any
signal does the coordinator ("mother") model classify the request.

The router also arbitrates `DELEGATE:` replies. An expert's hand-off is honoured
only if the router independently sees signal for the target lane; otherwise it
is vetoed and treated as "not covered". This fixes the two systematic failures
in EVALUATION.md (in-domain questions delegated away; cross-lane questions
answered by the wrong expert).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from apps.experts import grounding
from apps.experts.fleet import COORDINATOR_MODEL, FLEET
from apps.experts.nugen_client import ChatMessage, NugenClient, NugenError

logger = logging.getLogger("polymentor.routing")

MAX_LANES = 3
SECONDARY_RATIO = 0.35
DELEGATE_RE = re.compile(r"^\s*\**\s*DELEGATE\s*:?\**\s*:?\s*\**\s*([a-z]+)", re.IGNORECASE)

LANE_HINTS: dict[str, tuple[str, ...]] = {
    "dsa": (
        "algorithm",
        "complexity",
        "big-o",
        "big o",
        "o(n",
        "array",
        "binary search",
        "dynamic programming",
        " dp ",
        "graph",
        "bfs",
        "dfs",
        "heap",
        "linked list",
        " tree",
        "leetcode",
        "two pointer",
        "two-pointer",
        "sliding window",
        "data structure",
        " sort",
        "dijkstra",
        "union-find",
        "recursi",
        "memoiz",
        "subproblem",
        "hash",
        "collision",
        "url shortener",
    ),
    "sysdes": (
        "design a",
        "design an",
        "system design",
        "scale",
        "scalab",
        "architecture",
        "cache",
        "database",
        "shard",
        "partition",
        "replicat",
        "queue",
        "rate limit",
        "url shortener",
        "load balancer",
        "consistency",
        "throughput",
        "latency",
        "microservice",
        "distributed",
        "newsfeed",
        "news feed",
        "chat system",
        "redirects",
        "requests per",
    ),
    "behav": (
        "tell me about a time",
        "conflict",
        "leadership",
        "star method",
        "star format",
        "behavioral",
        "behavioural",
        "stakeholder",
        "disagree",
        "teammate",
        "my manager",
        "weakness",
        "failure story",
        " ship",
        "deadline",
        "weeks to",
        "prioritiz",
        " scope",
    ),
    "resume": ("resume", "résumé", " cv", "bullet", "job description", " jd", "linkedin"),
    "mock": (
        "mock",
        "grill me",
        "interview me",
        "quiz me",
        "ask me a",
        "practice interview",
        "score my",
        "rate my answer",
        "evaluate my answer",
        "then grill",
    ),
}


@dataclass
class RouteDecision:
    lanes: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    hints: dict[str, list[str]] = field(default_factory=dict)
    method: str = "keywords+bm25"
    rationale: str = ""

    @property
    def primary(self) -> str:
        return self.lanes[0]

    @property
    def collaborative(self) -> bool:
        return len(self.lanes) > 1

    def as_dict(self) -> dict:
        return asdict(self) | {"primary": self.primary, "collaborative": self.collaborative}


def _hint_hits(prompt: str) -> dict[str, list[str]]:
    text = f" {prompt.lower()} "
    return {lane: [h for h in hints if h in text] for lane, hints in LANE_HINTS.items()}


def _corpus_scores(prompt: str) -> dict[str, float]:
    query_tokens = set(grounding.tokenize(prompt))
    scores = {}
    for lane in FLEET:
        index = grounding.get_index(lane)
        scores[lane] = max(
            (index.score(query_tokens, i) for i in range(len(index.sections))), default=0.0
        )
    return scores


def score_lanes(prompt: str) -> tuple[dict[str, float], dict[str, list[str]]]:
    hits = _hint_hits(prompt)
    corpus = _corpus_scores(prompt)
    top = max(corpus.values()) or 1.0
    scores = {lane: round(len(hits[lane]) + corpus[lane] / top, 3) for lane in FLEET}
    return scores, {lane: h for lane, h in hits.items() if h}


def route(prompt: str, *, use_llm_fallback: bool = True) -> RouteDecision:
    scores, hits = score_lanes(prompt)
    ranked = sorted(scores, key=lambda lane: -scores[lane])
    if not hits and use_llm_fallback:
        llm_lanes = _classify_with_coordinator(prompt)
        if llm_lanes:
            return RouteDecision(
                lanes=llm_lanes,
                scores=scores,
                method="coordinator-llm",
                rationale="no lane keywords matched; the coordinator model classified the request",
            )
    if not hits:
        return RouteDecision(
            lanes=[ranked[0]], scores=scores, rationale="closest corpus match (no lane keywords)"
        )

    primary = max(hits, key=lambda lane: (scores[lane], len(hits[lane])))
    lanes = [primary] + [
        lane
        for lane in ranked
        if lane != primary and lane in hits and scores[lane] >= SECONDARY_RATIO * scores[primary]
    ]
    lanes = lanes[:MAX_LANES]
    rationale = "; ".join(f"{lane}: {', '.join(hits[lane][:3])}" for lane in lanes)
    return RouteDecision(lanes=lanes, scores=scores, hints=hits, rationale=rationale)


def parse_delegation(text: str) -> str | None:
    match = DELEGATE_RE.match(text or "")
    if not match:
        return None
    target = match.group(1).lower()
    return target if target in FLEET else None


def arbitrate_delegation(
    source: str, target: str, decision: RouteDecision, prompt: str
) -> tuple[bool, str]:
    """Return (honour, reason) for an expert's `DELEGATE: target` reply."""
    if target == source:
        return False, "expert delegated to itself"
    scores, hits = (decision.scores, decision.hints) if decision.scores else score_lanes(prompt)
    if target in hits:
        return True, f"router also sees {target} signal ({', '.join(hits[target][:3])})"
    if scores.get(target, 0) > scores.get(source, 0):
        return True, f"{target} corpus matches the request better than {source}"
    return False, f"no {target} signal in the request, so it stays with {source}"


def _classify_with_coordinator(prompt: str) -> list[str]:
    lanes_text = "\n".join(f"- {k}: {s.description}" for k, s in FLEET.items())
    messages = [
        ChatMessage(
            role="system",
            content=(
                "You route interview-prep requests to specialists. Reply with only a JSON "
                f'list of 1-3 specialist keys, most relevant first, e.g. ["sysdes"].\n{lanes_text}'
            ),
        ),
        ChatMessage(role="user", content=prompt),
    ]
    try:
        text = "".join(
            NugenClient().chat_stream(
                model=COORDINATOR_MODEL, messages=messages, temperature=0, max_tokens=30
            )
        )
    except NugenError as exc:
        logger.warning("coordinator routing failed: %s", exc)
        return []
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    try:
        lanes = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        return []
    return [lane for lane in lanes if lane in FLEET][:MAX_LANES]
