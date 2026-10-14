"""Core views: health check and the landing page."""

from __future__ import annotations

import subprocess
from functools import lru_cache

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@lru_cache(maxsize=1)
def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # pragma: no cover - defensive
        return "unknown"


@require_GET
def healthz(request):
    """Liveness probe. Counts live experts without hitting the Nugen API."""
    from apps.experts.models import ExpertVersion

    try:
        experts_live = ExpertVersion.objects.filter(status="LIVE").count()
    except Exception:
        experts_live = 0

    return JsonResponse(
        {
            "ok": True,
            "version": _git_sha(),
            "experts_live": experts_live,
        }
    )
