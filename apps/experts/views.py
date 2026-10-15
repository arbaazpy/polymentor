"""HTTP surface for single-expert inference.

Exposes a direct expert ask (streaming + non-streaming). The router/aggregator
flow builds on the same services in later milestones.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.experts import services
from apps.experts.nugen_client import NugenError


def _parse_request(request) -> tuple[dict | None, Response | None]:
    prompt = (request.data.get("prompt") or "").strip()
    if not prompt:
        return None, Response({"error": "prompt is required"}, status=status.HTTP_400_BAD_REQUEST)
    grounded = request.data.get("grounded", True)
    if isinstance(grounded, str):
        grounded = grounded.lower() not in {"0", "false", "no"}
    try:
        params = {
            "prompt": prompt,
            "expert_key": request.data.get("expert") or None,
            "grounded": bool(grounded),
            "system": request.data.get("system") or None,
            "temperature": float(request.data.get("temperature", 0.2)),
            "max_tokens": int(request.data.get("max_tokens", 512)),
        }
    except (TypeError, ValueError):
        return None, Response(
            {"error": "temperature and max_tokens must be numeric"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return params, None


@api_view(["POST"])
def ask(request):
    """Non-streaming expert ask.

    Body: {"prompt": str, "expert": str|null, "grounded": bool?, "system": str|null,
           "temperature": float?, "max_tokens": int?}
    """
    params, error = _parse_request(request)
    if error:
        return error
    try:
        result = services.answer(**params)
    except KeyError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except NugenError as exc:
        return Response(
            {"error": str(exc), "hint": exc.hint, "status": exc.status},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return Response(asdict(result))


@api_view(["POST"])
def ask_stream(request):
    """Streaming expert ask via Server-Sent Events.

    Each frame is a JSON event: meta, delta, confidence, usage, done, or error.
    """
    params, error = _parse_request(request)
    if error:
        return error

    def event_stream():
        try:
            for event in services.stream_answer(**params):
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: [DONE]\n\n"
        except KeyError as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
        except NugenError as exc:
            payload = {"type": "error", "error": str(exc), "hint": exc.hint}
            yield f"data: {json.dumps(payload)}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
