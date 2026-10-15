"""Feedback signals and the exemplars mined from them (the learning loop)."""

from __future__ import annotations

from django.db import models

from apps.core.models import BaseModel


class Feedback(BaseModel):
    class Rating(models.IntegerChoices):
        UP = 1, "Helpful"
        DOWN = -1, "Not helpful"

    turn = models.ForeignKey(
        "polymentor_sessions.Turn", on_delete=models.CASCADE, related_name="feedback"
    )
    # Blank means feedback on the combined answer rather than one expert.
    expert_key = models.SlugField(max_length=32, blank=True)
    rating = models.SmallIntegerField(choices=Rating.choices)
    correction = models.TextField(blank=True)
    mined = models.BooleanField(default=False, db_index=True)

    def __str__(self) -> str:
        return f"{self.expert_key or 'turn'} {self.rating:+d}"


class LearnedExemplar(BaseModel):
    """A reviewed Q&A pair added to an expert's grounding (exemplar refresh)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    expert_key = models.SlugField(max_length=32, db_index=True)
    question = models.TextField()
    answer = models.TextField()
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    source_feedback = models.OneToOneField(
        Feedback, null=True, blank=True, on_delete=models.SET_NULL, related_name="exemplar"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.expert_key}: {self.question[:50]}"
