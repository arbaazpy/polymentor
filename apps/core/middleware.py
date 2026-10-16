"""Middleware that must run before host validation and the HTTPS redirect."""

from __future__ import annotations

from apps.core.views import healthz


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz":
            return healthz(request)
        return self.get_response(request)
