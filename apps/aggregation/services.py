"""Turn orchestration: route, fan out to experts, reconcile, synthesize.

Event stream (each a dict with `type`):
    route           RouteDecision
    expert_start    {lane}
    expert          one expert's result (text, confidence, claims, sources)
    delegation      {from, to, honoured, reason}
    reconciliation  [{claim_id, owner, winner, candidates, rule}]
    delta           coordinator synthesis text
    done            {turn_id, url, latency_ms}
    error           {error}
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from apps.experts import services as expert_services
from apps.experts.fleet import COORDINATOR_MODEL, FLEET, get_spec, namespace_owner
from apps.experts.models import Expert
from apps.experts.nugen_client import ChatMessage, NugenClient, NugenError
from apps.experts.prompts import NOT_COVERED_PHRASE
from apps.feedback.services import exemplar_sections
from apps.routing import services as routing
from apps.sessions.models import Turn

logger = logging.getLogger("polymentor.aggregation")

EXPERT_MAX_TOKENS = 450
EXPERT_ATTEMPTS = 2  # one retry for transient Nugen failures (dropped streams, 429, 5xx)
SYNTHESIS_MAX_TOKENS = 320
CLAIM_RE = re.compile(
    r"\[\[\s*claim\s+id\s*=\s*[\"']?([a-z_]+\.[a-z_]+)[\"']?[^\]]*\]\](.*?)\[\[\s*/\s*claim\s*\]\]",
    re.IGNORECASE | re.DOTALL,
)
STRAY_TAG_RE = re.compile(r"\[\[[^\]\n]{0,80}\]\]")

# 3B models do not reliably follow a tagging protocol, so the decisions that
# actually collide across lanes are also extracted deterministically.
DECISION_PATTERNS: dict[str, re.Pattern] = {
    "hash.length": re.compile(r"\b(\d{1,2})[- ]?(?:char(?:acter)?s?|symbols?)\b", re.I),
    "arch.datastore": re.compile(
        r"\b(cassandra|dynamodb|postgres(?:ql)?|mysql|mongodb|bigtable|scylladb|cockroachdb)\b",
        re.I,
    ),
    "scale.qps": re.compile(
        r"(\d[\d,.]*\s?[km]?)\s*(?:qps|(?:req(?:uest)?s?|redirects?|reads?|writes?)\s*"
        r"(?:/\s*s(?:ec(?:ond)?)?\b|per second))",
        re.I,
    ),
    "storage.size": re.compile(r"\b(\d[\d,.]*\s?(?:tb|pb|gb))\b", re.I),
    "cache.strategy": re.compile(
        r"\b(cache-aside|read-through|write-through|write-back|write-around)\b", re.I
    ),
}
VALUE_ALIASES = {"postgresql": "postgres"}


@dataclass
class Claim:
    id: str
    text: str
    lane: str
    value: str = ""

    @property
    def owner(self) -> str | None:
        return namespace_owner(self.id)


def _normalize_value(raw: str) -> str:
    value = re.sub(r"[\s,]", "", raw.lower())
    return VALUE_ALIASES.get(value, value)


SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)|\n")


def _snippet(text: str, start: int, end: int, width: int = 120) -> str:
    """The sentence containing text[start:end], clipped to `width` either side."""
    left = max([m.end() for m in SENTENCE_END_RE.finditer(text, 0, start)] + [start - width, 0])
    stop = SENTENCE_END_RE.search(text, end)
    right = min(stop.end() if stop else len(text), end + width)
    return " ".join(text[left:right].replace("*", "").split()).lstrip("- ")


def extract_claims(text: str, lane: str) -> list[Claim]:
    """Tagged claims first; then the first detected value per decision pattern."""
    text = text or ""
    claims = [
        Claim(id=cid.lower(), text=" ".join(body.split()), lane=lane, value="")
        for cid, body in CLAIM_RE.findall(text)
    ]
    tagged = {c.id for c in claims}
    for claim_id, pattern in DECISION_PATTERNS.items():
        match = pattern.search(text)
        if claim_id in tagged or not match:
            continue
        claims.append(
            Claim(
                id=claim_id,
                text=_snippet(text, match.start(), match.end()),
                lane=lane,
                value=_normalize_value(match.group(1)),
            )
        )
    return claims


def strip_claim_tags(text: str) -> str:
    return STRAY_TAG_RE.sub("", CLAIM_RE.sub(lambda m: m.group(2), text or "")).strip()


def reconcile(claims: list[Claim]) -> list[dict[str, Any]]:
    """Resolve claims made by more than one lane using lane ownership.

    The owning lane's claim wins. If the owner made no claim, the conflict is
    surfaced as unresolved rather than silently picking a non-owner.
    """
    by_id: dict[str, list[Claim]] = {}
    for claim in claims:
        by_id.setdefault(claim.id, []).append(claim)
    notes = []
    for claim_id, group in by_id.items():
        lanes = {c.lane for c in group}
        if len(lanes) < 2:
            continue
        owner = namespace_owner(claim_id)
        owner_claim = next((c for c in group if c.lane == owner), None)
        values = {c.value for c in group}
        agreed = len(values) == 1 and "" not in values
        if agreed:
            rule = f"all lanes agree ({values.pop()})"
        elif owner_claim:
            rule = f"lane ownership: {claim_id.split('.')[0]}.* belongs to {owner}"
        else:
            rule = f"owner lane ({owner or 'none'}) made no claim; left unresolved"
        notes.append(
            {
                "claim_id": claim_id,
                "owner": owner,
                "agreed": agreed,
                "winner": owner_claim.lane if owner_claim else None,
                "resolved_text": owner_claim.text if owner_claim else None,
                "candidates": [{"lane": c.lane, "text": c.text, "value": c.value} for c in group],
                "rule": rule,
            }
        )
    return notes


def _versions() -> dict[str, str]:
    return {
        e.key: e.current_version.semver
        for e in Expert.objects.select_related("current_version")
        if e.current_version
    }


def _ask_expert(
    lane: str,
    prompt: str,
    *,
    model_id: str,
    version: str,
    collaborative: bool,
    exemplars: list,
) -> dict[str, Any]:
    spec = get_spec(lane)
    question = f"{prompt}\n\n(Your part: {spec.focus}.)" if collaborative else prompt
    entry: dict[str, Any] = {
        "lane": lane,
        "lane_name": spec.lane,
        "version": version,
        "model": model_id,
        "aligned": spec.aligned,
    }
    for attempt in range(1, EXPERT_ATTEMPTS + 1):
        try:
            result = expert_services.answer(
                prompt=question,
                expert_key=lane,
                model_id=model_id,
                collaborative=collaborative,
                exemplars=exemplars,
                max_tokens=EXPERT_MAX_TOKENS,
            )
            break
        except NugenError as exc:
            logger.warning("expert %s failed (attempt %d): %s", lane, attempt, exc)
            if not exc.retryable or attempt == EXPERT_ATTEMPTS:
                return entry | {"status": "error", "error": str(exc), "text": "", "raw": ""}
    claims = extract_claims(result.text, lane)
    return entry | {
        "status": "answered",
        "raw": result.text,
        "text": strip_claim_tags(result.text),
        "claims": [
            {"id": c.id, "text": c.text, "value": c.value, "owner": c.owner} for c in claims
        ],
        "confidence": result.confidence,
        "sections": result.sections,
        "latency_ms": result.latency_ms,
    }


def run_turn(prompt: str, *, client_hash: str = "") -> Iterator[dict[str, Any]]:
    started = time.monotonic()
    turn = Turn(prompt=prompt, client_hash=client_hash)
    try:
        decision = routing.route(prompt)
    except Exception:  # routing must never take the request down
        logger.exception("routing failed")
        decision = routing.RouteDecision(lanes=["sysdes"], rationale="routing error; default lane")
    turn.route = decision.as_dict()
    yield {"type": "route", **turn.route}

    versions = _versions()
    exemplars = {lane: exemplar_sections(lane) for lane in FLEET}

    def ask(lane: str, *, collaborative: bool) -> dict[str, Any]:
        return _ask_expert(
            lane,
            prompt,
            model_id=expert_services.resolve_model_id(lane),
            version=versions.get(lane, "0.1.0"),
            collaborative=collaborative,
            exemplars=exemplars[lane],
        )

    if decision.collaborative:
        yield from _run_collaborative(turn, decision, ask)
    else:
        yield from _run_single(turn, decision, prompt, ask)

    answered = [e for e in turn.experts if e["status"] == "answered"]
    if not answered and not any(e["status"] == "abstained" for e in turn.experts):
        turn.status = Turn.Status.ERROR
    elif len(answered) < len([e for e in turn.experts if e["status"] != "abstained"]):
        turn.status = Turn.Status.PARTIAL
    turn.latency_ms = int((time.monotonic() - started) * 1000)
    turn.save()
    yield {"type": "done", "turn_id": str(turn.pk), "url": f"/t/{turn.pk}", "status": turn.status}


def _run_single(turn, decision, prompt, ask) -> Iterator[dict[str, Any]]:
    lane = decision.primary
    yield {"type": "expert_start", "lane": lane}
    entry = ask(lane, collaborative=False)
    target = routing.parse_delegation(entry.get("text", ""))
    if target:
        honour, reason = routing.arbitrate_delegation(lane, target, decision, prompt)
        delegation = {"from": lane, "to": target, "honoured": honour, "reason": reason}
        turn.delegations.append(delegation)
        yield {"type": "delegation", **delegation}
        if honour:
            entry["status"] = "delegated"
            turn.experts.append(entry)
            yield {"type": "expert", **entry}
            lane = target
            yield {"type": "expert_start", "lane": lane}
            entry = ask(lane, collaborative=False)
        else:
            entry = entry | {
                "status": "abstained",
                "text": (
                    f"{NOT_COVERED_PHRASE} expert.{lane} tried to hand this to {target}, but "
                    f"the router vetoed it ({reason}). Treat this topic as outside the "
                    "curated notes rather than trusting a guess."
                ),
            }
    turn.experts.append(entry)
    yield {"type": "expert", **entry}


def _run_collaborative(turn, decision, ask) -> Iterator[dict[str, Any]]:
    for lane in decision.lanes:
        yield {"type": "expert_start", "lane": lane}
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(decision.lanes)) as pool:
        futures = {pool.submit(ask, lane, collaborative=True): lane for lane in decision.lanes}
        for future in as_completed(futures):
            entry = future.result()
            results[entry["lane"]] = entry
            yield {"type": "expert", **entry}
    turn.experts = [results[lane] for lane in decision.lanes]

    claims = [
        Claim(id=c["id"], text=c["text"], lane=e["lane"], value=c.get("value", ""))
        for e in turn.experts
        for c in e.get("claims", [])
    ]
    turn.reconciliation = reconcile(claims)
    yield {"type": "reconciliation", "notes": turn.reconciliation}

    answered = [e for e in turn.experts if e["status"] == "answered"]
    if answered:
        parts = []
        for delta in synthesize(turn.prompt, answered, turn.reconciliation):
            parts.append(delta)
            yield {"type": "delta", "text": delta}
        turn.synthesis = "".join(parts).strip()


def synthesize(prompt: str, experts: list[dict], notes: list[dict]) -> Iterator[str]:
    """Stream the coordinator's combined plan. Falls back to nothing on error."""
    expert_text = "\n\n".join(f"[{e['lane']}] {e['text']}" for e in experts)
    rulings = "\n".join(
        f"- {n['claim_id']}: use {n['winner']}'s position: {n['resolved_text']}"
        for n in notes
        if n["winner"] and not n.get("agreed")
    )
    system = (
        "You are PolyMentor's coordinator. Specialists answered parts of the user's request. "
        "Merge their advice into one short plan: at most 6 bullet points, in the order the "
        "user should act. Use only facts from the specialist notes and credit each bullet "
        "with its specialist in brackets, e.g. [sysdes]. Do not add new facts."
    )
    if rulings:
        system += f"\nWhere specialists disagreed, these rulings are final:\n{rulings}"
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=f"Request: {prompt}\n\nSpecialist notes:\n{expert_text}"),
    ]
    try:
        yield from NugenClient().chat_stream(
            model=COORDINATOR_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=SYNTHESIS_MAX_TOKENS,
        )
    except NugenError as exc:
        logger.warning("synthesis failed: %s", exc)
