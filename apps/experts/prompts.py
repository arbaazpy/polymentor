"""System prompts for expert lanes.

The same rules are used with and without grounding so the benchmark isolates
the effect of the reference notes. Delegation uses a fixed `DELEGATE: <lane>`
line so the router/aggregator can parse it.
"""

from __future__ import annotations

from apps.experts.fleet import ExpertSpec
from apps.experts.grounding import Section

LANE_DIRECTORY: dict[str, str] = {
    "dsa": "data structures, algorithms, complexity analysis, coding-interview patterns",
    "sysdes": "system design: scalability, caching, storage, consistency, distributed architecture",
    "behav": "behavioral interviews: STAR stories, leadership, conflict, ownership",
    "resume": "resume review and job-description fit",
    "mock": "running and scoring mock interviews",
}

NOT_COVERED_PHRASE = "Not covered by my notes."


# Shared sub-claim taxonomy. Each namespace is owned by one lane (see fleet).
CLAIM_TAXONOMY: dict[str, str] = {
    "hash.length": "length and alphabet of generated short codes or keys",
    "scale.qps": "estimated requests per second",
    "storage.size": "estimated storage needed",
    "arch.datastore": "which database or store to use",
    "cache.strategy": "caching approach",
    "framing.scope": "what to cut or ship first under a deadline",
    "story.structure": "how to structure the answer as a story",
}


def build_system_prompt(
    spec: ExpertSpec,
    sections: list[Section] | None = None,
    *,
    collaborative: bool = False,
) -> str:
    """Lane system prompt.

    `collaborative` is used when the router splits one request across several
    lanes: the expert answers only its part and tags key decisions as claims.
    """
    others = "\n".join(
        f"   - {key}: {scope}" for key, scope in LANE_DIRECTORY.items() if key != spec.key
    )
    if collaborative:
        taxonomy = "\n".join(f"   - {cid}: {desc}" for cid, desc in CLAIM_TAXONOMY.items())
        delegation_rule = (
            "2. Other specialists are answering the other parts of this request in parallel. "
            f"Answer only the {spec.focus or spec.lane} part. Do not delegate. If your part "
            "involves any of these decisions, state it plainly with a concrete value "
            '(for example "use 8-character codes", "store mappings in Cassandra", '
            '"about 12k QPS"):\n'
            f"{taxonomy}"
        )
    else:
        delegation_rule = (
            "2. Delegate only when the question belongs to another specialist's domain. Then "
            "do not answer it; reply with a single line:\n"
            "   DELEGATE: <specialist> - <one-sentence reason>\n"
            f"   Specialists:\n{others}\n"
            "   A question inside your own domain is never delegated, even if you cannot "
            "answer it."
        )
    if sections:
        coverage_rule = (
            "3. Your reference notes below are authoritative. Answer from them and use their "
            f'terminology. If the notes do not cover the topic, say "{NOT_COVERED_PHRASE}" '
            "and name the closest covered concept. Never invent algorithms, bounds, or "
            "details that are not in the notes."
        )
    else:
        coverage_rule = (
            "3. If the topic is in your domain but you cannot answer it reliably, say "
            f'"{NOT_COVERED_PHRASE}" and name the closest concept you do know. Never invent '
            "algorithms, bounds, or details."
        )
    lines = [
        f"You are expert.{spec.key}, PolyMentor's {spec.lane} specialist for technical "
        "interview preparation.",
        "",
        "Rules:",
        f"1. Only answer questions about {LANE_DIRECTORY.get(spec.key, spec.lane)}.",
        delegation_rule,
        coverage_rule,
        "4. Answer every part of the question (what, when, why, and how) in 3-8 sentences. "
        "Name the pattern, state time and space complexity where relevant, and use standard "
        "terminology.",
    ]
    if sections:
        notes = "\n\n".join(
            f"[{n}] {s.source} - {s.title}\n{s.text}" for n, s in enumerate(sections, start=1)
        )
        lines += ["", "Reference notes:", notes]
    return "\n".join(lines)
