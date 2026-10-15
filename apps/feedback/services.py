"""The learning loop.

1. Users rate the combined answer or a single expert, optionally with a
   correction.
2. `mine_feedback` turns signals into PENDING exemplars:
   - a downvote with a correction becomes the corrected Q&A pair;
   - an upvoted expert answer becomes a positive exemplar.
3. A reviewer approves exemplars in the Django admin. Approved exemplars are
   retrieved alongside the corpus immediately (exemplar refresh, no retraining).
4. `export_realign_set` writes approved exemplars as a corpus document for a
   Nugen re-alignment; `promote_expert` gates the new model on the benchmark.
"""

from __future__ import annotations

from pathlib import Path

from django.db import transaction
from django.db.models import Count, Q

from apps.experts.fleet import CORPORA_DIR, FLEET
from apps.experts.grounding import Section
from apps.feedback.models import Feedback, LearnedExemplar
from apps.sessions.models import Turn

MIN_CORRECTION_CHARS = 20
REALIGN_MIN_DOWNVOTES = 5
REALIGN_DOWNVOTE_RATE = 0.3
MAX_EXEMPLARS_PER_LANE = 50


def record_feedback(
    *, turn: Turn, rating: int, expert_key: str = "", correction: str = ""
) -> Feedback:
    if rating not in (Feedback.Rating.UP, Feedback.Rating.DOWN):
        raise ValueError("rating must be 1 or -1")
    if expert_key and expert_key not in {e.get("lane") for e in turn.experts}:
        raise ValueError(f"expert '{expert_key}' did not answer this turn")
    return Feedback.objects.create(
        turn=turn, rating=rating, expert_key=expert_key, correction=correction.strip()[:4000]
    )


def _expert_text(turn: Turn, expert_key: str) -> str:
    for entry in turn.experts:
        if entry.get("lane") == expert_key and entry.get("status") == "answered":
            return entry.get("text", "")
    return ""


def mine_feedback() -> dict[str, int]:
    """Convert unmined feedback into PENDING exemplars. Returns counts."""
    created = skipped = 0
    with transaction.atomic():
        pending = Feedback.objects.select_for_update().filter(mined=False).select_related("turn")
        for fb in pending:
            lane = fb.expert_key or (fb.turn.route.get("primary") if fb.turn.route else "")
            answer = ""
            if fb.rating == Feedback.Rating.DOWN and len(fb.correction) >= MIN_CORRECTION_CHARS:
                answer = fb.correction
            elif fb.rating == Feedback.Rating.UP and fb.expert_key:
                answer = _expert_text(fb.turn, fb.expert_key)
            if lane in FLEET and answer:
                LearnedExemplar.objects.create(
                    expert_key=lane, question=fb.turn.prompt, answer=answer, source_feedback=fb
                )
                created += 1
            else:
                skipped += 1
            fb.mined = True
            fb.save(update_fields=["mined", "updated_at"])
    return {"created": created, "skipped": skipped}


def exemplar_sections(expert_key: str) -> list[Section]:
    rows = LearnedExemplar.objects.filter(
        expert_key=expert_key, status=LearnedExemplar.Status.APPROVED
    ).values_list("question", "answer")[:MAX_EXEMPLARS_PER_LANE]
    return [
        Section(source="learned", title=f"Reviewed answer: {q[:80]}", text=f"Q: {q}\nA: {a}")
        for q, a in rows
    ]


def lane_health() -> list[dict]:
    """Per-lane feedback stats and whether a re-alignment is recommended."""
    votes = {
        row["expert_key"]: row
        for row in Feedback.objects.exclude(expert_key="")
        .values("expert_key")
        .annotate(up=Count("id", filter=Q(rating=1)), down=Count("id", filter=Q(rating=-1)))
    }
    exemplars = {
        row["expert_key"]: row
        for row in LearnedExemplar.objects.values("expert_key").annotate(
            approved=Count("id", filter=Q(status=LearnedExemplar.Status.APPROVED)),
            pending=Count("id", filter=Q(status=LearnedExemplar.Status.PENDING)),
        )
    }
    health = []
    for lane in FLEET:
        up = votes.get(lane, {}).get("up", 0)
        down = votes.get(lane, {}).get("down", 0)
        rate = down / (up + down) if up + down else 0.0
        health.append(
            {
                "lane": lane,
                "up": up,
                "down": down,
                "downvote_rate": round(rate, 2),
                "approved_exemplars": exemplars.get(lane, {}).get("approved", 0),
                "pending_exemplars": exemplars.get(lane, {}).get("pending", 0),
                "realign_recommended": down >= REALIGN_MIN_DOWNVOTES
                and rate >= REALIGN_DOWNVOTE_RATE,
            }
        )
    return health


def export_realign_set(expert_key: str) -> tuple[Path, int]:
    """Write approved exemplars as `corpora/<lane>/learned.md` for a Nugen re-align."""
    spec = FLEET[expert_key]
    rows = LearnedExemplar.objects.filter(
        expert_key=expert_key, status=LearnedExemplar.Status.APPROVED
    ).order_by("created_at")
    blocks = [
        f"### {n}. {ex.question.strip()}\n\n{ex.answer.strip()}" for n, ex in enumerate(rows, 1)
    ]
    text = (
        f"# {spec.lane} — Reviewed Answers\n\n"
        "License: user feedback reviewed by a maintainer; no private data.\n"
        f"Lane: {expert_key}\n\n## Reviewed question and answer pairs\n\n" + "\n\n".join(blocks)
    )
    path = CORPORA_DIR / expert_key / "learned.md"
    path.write_text(text + "\n", encoding="utf-8")
    return path, len(text.split())
