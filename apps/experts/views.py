"""HTTP surface for inference.

For H 0-4 this exposes a minimal ask endpoint (streaming + non-streaming) so we
can prove the Nugen client works end-to-end before experts are aligned. The
full router/aggregator flow lands in later milestones.
"""

from __future__ import annotations

import json

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.experts import services
from apps.experts.nugen_client import NugenError


@api_view(["POST"])
def ask(request):
    """Non-streaming single-expert (or default-model) ask.

    Body: {"prompt": str, "expert": str|null, "system": str|null,
           "temperature": float?, "max_tokens": int?}
    """
    prompt = (request.data.get("prompt") or "").strip()
    if not prompt:
        return Response({"error": "prompt is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        answer = services.ask_once(
            prompt=prompt,
            expert_key=request.data.get("expert"),
            system=request.data.get("system"),
            temperature=float(request.data.get("temperature", 0.25)),
            max_tokens=int(request.data.get("max_tokens", 512)),
        )
    except NugenError as exc:
        return Response(
            {"error": str(exc), "hint": exc.hint, "status": exc.status},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return Response({"answer": answer})


@api_view(["POST"])
def ask_stream(request):
    """Streaming ask via Server-Sent Events."""
    prompt = (request.data.get("prompt") or "").strip()
    if not prompt:
        return Response({"error": "prompt is required"}, status=status.HTTP_400_BAD_REQUEST)

    expert_key = request.data.get("expert")
    system = request.data.get("system")
    temperature = float(request.data.get("temperature", 0.25))
    max_tokens = int(request.data.get("max_tokens", 512))

    def event_stream():
        try:
            for delta in services.ask_stream(
                prompt=prompt,
                expert_key=expert_key,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
            yield "data: [DONE]\n\n"
        except NugenError as exc:
            yield f"data: {json.dumps({'error': str(exc), 'hint': exc.hint})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
