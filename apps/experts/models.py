"""Expert registry and versioning.

An Expert is a stable lane (dsa, sysdes, ...). Each alignment run produces an
ExpertVersion that points at a concrete deployed Nugen model id. Expert.current
flips atomically on promotion (see apps.alignment).
"""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Expert(BaseModel):
    """A stable domain lane. `key` is the public identifier, e.g. 'dsa'."""

    key = models.SlugField(unique=True, max_length=32)
    lane = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    # Dotted sub-claim namespaces this expert owns, e.g. ["hash", "complexity"].
    owned_namespaces = models.JSONField(default=list, blank=True)
    current_version = models.ForeignKey(
        "experts.ExpertVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return f"expert.{self.key}"


class ExpertVersion(BaseModel):
    """A specific aligned+deployed model for an expert lane."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ALIGNING = "ALIGNING", "Aligning"
        DEPLOYING = "DEPLOYING", "Deploying"
        EVALUATING = "EVALUATING", "Evaluating"
        LIVE = "LIVE", "Live"
        GATED_OUT = "GATED_OUT", "Gated out"
        FAILED = "FAILED", "Failed"
        RETIRED = "RETIRED", "Retired"

    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name="versions")
    semver = models.CharField(max_length=20)  # e.g. "0.2.0"
    nugen_model_id = models.CharField(max_length=256, blank=True)
    base_model = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Benchmark aggregates for the version, e.g. {"overall": 0.89, "definition": 1.0, ...}
    metrics = models.JSONField(default=dict, blank=True)
    gate_reason = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["expert", "semver"], name="uniq_expert_semver"),
        ]

    def __str__(self) -> str:
        return f"{self.expert.key} v{self.semver} ({self.status})"
