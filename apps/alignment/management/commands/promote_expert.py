"""Evaluation-gated promotion of a re-aligned expert model.

    uv run python manage.py promote_expert dsa --model <new_nugen_model_id>

Benchmarks the candidate (aligned + grounded) and compares it with the current
LIVE version's stored metrics. The candidate goes LIVE only if the gate
passes; otherwise it is recorded as GATED_OUT with the reason.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.alignment import services
from apps.experts import services as expert_services
from apps.experts.fleet import get_spec
from apps.experts.models import Expert, ExpertVersion


class Command(BaseCommand):
    help = "Benchmark a candidate model and promote it only if it passes the eval gate."

    def add_arguments(self, parser):
        parser.add_argument("expert")
        parser.add_argument("--model", required=True, help="Candidate Nugen model id")
        parser.add_argument("--workers", type=int, default=3)

    def handle(self, *args, **opts):
        try:
            spec = get_spec(opts["expert"])
        except KeyError as exc:
            raise CommandError(str(exc)) from exc
        expert = Expert.objects.filter(key=spec.key).select_related("current_version").first()
        current = expert.current_version if expert else None
        if current and current.nugen_model_id == opts["model"]:
            raise CommandError("Candidate is already the LIVE version.")
        if current and not current.metrics:
            raise CommandError(
                f"Current version has no stored metrics; run `run_benchmark {spec.key}` first."
            )

        report = services.run_benchmark(
            spec=spec,
            mode_names=[services.GATE_MODE],
            aligned_model_id=opts["model"],
            workers=opts["workers"],
        )
        stamp = timezone.now().strftime("%Y%m%dT%H%M%S")
        out = Path(settings.BASE_DIR) / "evals" / spec.key / f"{stamp}-candidate.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

        summary = report["modes"][services.GATE_MODE]["summary"]
        result = services.gate_decision(summary, current.metrics if current else None)
        if result.passed:
            version = expert_services.register_live_version(spec=spec, model_id=opts["model"])
            if current:
                current.status = ExpertVersion.Status.RETIRED
                current.save(update_fields=["status", "updated_at"])
            version.metrics, version.gate_reason = summary, f"gate passed: {result.reason}"
            version.save(update_fields=["metrics", "gate_reason", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"PROMOTED v{version.semver}: {result.reason}"))
        else:
            version = ExpertVersion.objects.create(
                expert=expert,
                semver=f"0.{expert.versions.count() + 1}.0",
                nugen_model_id=opts["model"],
                base_model=spec.base_model,
                status=ExpertVersion.Status.GATED_OUT,
                metrics=summary,
                gate_reason=result.reason[:256],
            )
            self.stdout.write(self.style.WARNING(f"GATED OUT v{version.semver}: {result.reason}"))
        self.stdout.write(f"Report: {out}")
