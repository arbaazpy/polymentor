"""Score an expert's gold benchmark across base / aligned / grounded modes.

    uv run python manage.py run_benchmark dsa
    uv run python manage.py run_benchmark dsa --modes aligned,aligned_grounded --limit 5

Writes the full report (answers included) to evals/<expert>/<timestamp>.json
and prints a markdown summary table for EVALUATION.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.alignment import services
from apps.experts.fleet import get_spec
from apps.experts.models import Expert


class Command(BaseCommand):
    help = "Run an expert's benchmark across model/grounding modes and write a report."

    def add_arguments(self, parser):
        parser.add_argument("expert", help="Expert key, e.g. dsa")
        parser.add_argument(
            "--modes",
            default=",".join(services.MODES),
            help=f"Comma-separated subset of: {', '.join(services.MODES)}",
        )
        parser.add_argument("--model", help="Aligned model id (default: the expert's LIVE version)")
        parser.add_argument("--limit", type=int, help="Only the first N questions")
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--max-tokens", type=int, default=400)
        parser.add_argument("--out", help="Output JSON path (default: evals/<expert>/<ts>.json)")

    def handle(self, *args, **opts):
        try:
            spec = get_spec(opts["expert"])
        except KeyError as exc:
            raise CommandError(str(exc)) from exc

        mode_names = [m.strip() for m in opts["modes"].split(",") if m.strip()]
        unknown = [m for m in mode_names if m not in services.MODES]
        if unknown:
            raise CommandError(f"Unknown modes: {', '.join(unknown)}")

        aligned_model_id = opts["model"] or self._live_model(spec.key)

        def progress(mode: str, result: services.ItemResult) -> None:
            mark = "ERR" if result.error else f"{result.score:.2f}"
            self.stdout.write(f"  [{mode}] Q{result.question_num:<2} {mark}")

        try:
            report = services.run_benchmark(
                spec=spec,
                mode_names=mode_names,
                aligned_model_id=aligned_model_id,
                limit=opts["limit"],
                workers=opts["workers"],
                max_tokens=opts["max_tokens"],
                on_item=progress,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        out = Path(opts["out"]) if opts["out"] else self._default_out(spec.key, report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        services.save_version_metrics(report)

        self.stdout.write("")
        self.stdout.write(services.render_markdown(report))
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Report written to {out}"))

    @staticmethod
    def _live_model(expert_key: str) -> str | None:
        expert = Expert.objects.filter(key=expert_key).select_related("current_version").first()
        if expert and expert.current_version:
            return expert.current_version.nugen_model_id or None
        return None

    @staticmethod
    def _default_out(expert_key: str, report: dict) -> Path:
        stamp = report["created_at"].replace(":", "").replace("-", "")[:15]
        return Path(settings.BASE_DIR) / "evals" / expert_key / f"{stamp}.json"
