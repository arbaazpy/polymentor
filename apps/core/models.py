"""Shared base models and mixins used across PolyMentor apps."""

from __future__ import annotations

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Primary key is a UUID so object ids are safe to expose in URLs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Adds self-managed created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True
