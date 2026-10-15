"""Server-rendered pages: ask, turn permalink, expert registry/history."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from apps.experts.fleet import FLEET
from apps.experts.models import Expert
from apps.feedback.services import lane_health
from apps.sessions.models import Turn

TRY_THESE = [
    "Design a URL shortener for 1B redirects/day. I have 2 weeks to ship.",
    "My binary search uses while l < r and l = mid and never terminates. Why?",
    "Tell me about a time you disagreed with your manager: how should I structure my answer?",
    "Rewrite this resume bullet: 'Worked on the payments service.'",
    "Grill me with one system design question and tell me how you'll score it.",
]


@require_GET
@ensure_csrf_cookie
def home(request):
    examples = Turn.objects.filter(is_example=True).only("id", "prompt")[:6]
    return render(request, "home.html", {"try_these": TRY_THESE, "examples": examples})


@require_GET
@ensure_csrf_cookie
def turn_detail(request, turn_id):
    turn = get_object_or_404(Turn, pk=turn_id)
    payload = {
        "id": str(turn.pk),
        "prompt": turn.prompt,
        "route": turn.route,
        "experts": turn.experts,
        "delegations": turn.delegations,
        "reconciliation": turn.reconciliation,
        "synthesis": turn.synthesis,
        "status": turn.status,
        "latency_ms": turn.latency_ms,
        "created_at": turn.created_at.isoformat(),
    }
    return render(request, "turn.html", {"turn": turn, "payload": payload})


def _latest_eval(lane: str) -> dict | None:
    runs = sorted((Path(settings.BASE_DIR) / "evals" / lane).glob("*.json"))
    if not runs:
        return None
    report = json.loads(runs[-1].read_text(encoding="utf-8"))
    return {
        "file": f"evals/{lane}/{runs[-1].name}",
        "modes": {m: d["summary"] for m, d in report["modes"].items()},
    }


@require_GET
def experts(request):
    db = {e.key: e for e in Expert.objects.prefetch_related("versions")}
    health = {h["lane"]: h for h in lane_health()}
    rows = []
    for key, spec in FLEET.items():
        expert = db.get(key)
        rows.append(
            {
                "spec": spec,
                "versions": list(expert.versions.all()) if expert else [],
                "current": expert.current_version if expert else None,
                "health": health.get(key, {}),
                "eval": _latest_eval(key),
            }
        )
    return render(request, "experts.html", {"rows": rows})
