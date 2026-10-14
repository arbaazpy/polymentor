"""Celery application for PolyMentor.

Runs eager (synchronous) in development when CELERY_TASK_ALWAYS_EAGER is set,
so no broker is required to develop. In production a Redis broker + worker +
beat handle re-alignment and the nightly feedback miner.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("polymentor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:  # pragma: no cover - trivial
    print(f"Request: {self.request!r}")
