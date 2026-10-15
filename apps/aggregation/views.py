"""Public turn API (SSE), feedback, and the bearer-protected miner trigger."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.aggregation.services import run_turn
from apps.feedback import services as feedback_services
from apps.sessions.models import Turn


def client_hash(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()[:32]


def _rate_limit_error(chash: str) -> str | None:
    now = timezone.now()
    window_start = now - timedelta(minutes=settings.TURN_RATE_WINDOW_MINUTES)
    if Turn.objects.filter(client_hash=chash, created_at__gte=window_start).count() >= (
        settings.TURN_RATE_LIMIT
    ):
        return (
            f"Rate limit: {settings.TURN_RATE_LIMIT} questions per "
            f"{settings.TURN_RATE_WINDOW_MINUTES} minutes. Browse the example answers meanwhile."
        )
    day_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    if Turn.objects.filter(created_at__gte=day_start).count() >= settings.DAILY_TURN_CAP:
        return "The daily demo budget is used up. Example answers below are still browsable."
    return None


@api_view(["POST"])
def turn_stream(request):
    prompt = (request.data.get("prompt") or "").strip()
    if not prompt:
        return Response({"error": "prompt is required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(prompt) > settings.MAX_PROMPT_CHARS:
        return Response(
            {"error": f"Keep questions under {settings.MAX_PROMPT_CHARS} characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    chash = client_hash(request)
    limited = _rate_limit_error(chash)
    if limited:
        return Response({"error": limited}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    def events():
        try:
            for event in run_turn(prompt, client_hash=chash):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # surface instead of a silently dropped stream
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
def turn_feedback(request, turn_id):
    turn = get_object_or_404(Turn, pk=turn_id)
    try:
        rating = int(request.data.get("rating"))
        fb = feedback_services.record_feedback(
            turn=turn,
            rating=rating,
            expert_key=(request.data.get("expert") or "").strip(),
            correction=request.data.get("correction") or "",
        )
    except (TypeError, ValueError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"ok": True, "id": str(fb.pk)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def admin_mine(request):
    token = settings.ADMIN_BEARER_TOKEN
    supplied = request.META.get("HTTP_AUTHORIZATION", "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, supplied):
        return Response({"error": "unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(
        {"mined": feedback_services.mine_feedback(), "health": feedback_services.lane_health()}
    )
