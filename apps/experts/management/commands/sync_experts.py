"""Seed the expert registry from the fleet manifest (idempotent; runs on deploy).

Registers each lane's committed `live_model_id` as LIVE (unless the DB already
has a different LIVE version, e.g. after a promotion) and attaches metrics from
the latest committed benchmark report.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.alignment.services import save_version_metrics
from apps.experts import services
from apps.experts.fleet import FLEET
from apps.experts.models import Expert


class Command(BaseCommand):
    help = "Register fleet models as LIVE expert versions and load benchmark metrics."

    def handle(self, *args, **opts):
        for key, spec in FLEET.items():
            expert = Expert.objects.filter(key=key).select_related("current_version").first()
            if expert and expert.current_version:
                self.stdout.write(f"expert.{key}: keeping v{expert.current_version.semver}")
            elif spec.live_model_id:
                version = services.register_live_version(spec=spec, model_id=spec.live_model_id)
                self.stdout.write(f"expert.{key}: registered v{version.semver}")
            runs = sorted((Path(settings.BASE_DIR) / "evals" / key).glob("2*[0-9].json"))
            if runs:
                save_version_metrics(json.loads(runs[-1].read_text(encoding="utf-8")))
        self.stdout.write(self.style.SUCCESS("Expert registry in sync."))
