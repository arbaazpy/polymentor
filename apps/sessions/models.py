"""A Turn is one user request and everything PolyMentor did to answer it."""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Turn(BaseModel):
    class Status(models.TextChoices):
        OK = "OK", "OK"
        PARTIAL = "PARTIAL", "Partial"
        ERROR = "ERROR", "Error"

    prompt = models.TextField()
    # RouteDecision.as_dict(): lanes, scores, hints, method, rationale.
    route = models.JSONField(default=dict, blank=True)
    # One entry per expert call: lane, version, model, text, raw, confidence, claims...
    experts = models.JSONField(default=list, blank=True)
    delegations = models.JSONField(default=list, blank=True)
    reconciliation = models.JSONField(default=list, blank=True)
    synthesis = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OK)
    latency_ms = models.PositiveIntegerField(default=0)
    # Salted hash of the client IP (rate limiting / abuse); the raw IP is never stored.
    client_hash = models.CharField(max_length=32, blank=True, db_index=True)
    is_example = models.BooleanField(default=False, help_text="Pin on the home page")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.prompt[:60]

    @property
    def final_text(self) -> str:
        if self.synthesis:
            return self.synthesis
        answered = [e for e in self.experts if e.get("status") == "answered"]
        return answered[-1]["text"] if answered else ""
