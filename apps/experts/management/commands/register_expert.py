"""Register an already-deployed Nugen model as the LIVE version of an expert.

Use this when alignment/deployment was done in the Nugen dashboard instead of
`bootstrap_experts`:

    uv run python manage.py register_expert dsa --model model_01m4zv707z9qzt7z
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.experts import services
from apps.experts.fleet import get_spec


class Command(BaseCommand):
    help = "Record a deployed Nugen model id as the LIVE version of an expert lane."

    def add_arguments(self, parser):
        parser.add_argument("expert", help="Expert key, e.g. dsa")
        parser.add_argument("--model", required=True, help="Deployed Nugen model id")

    def handle(self, *args, **opts):
        try:
            spec = get_spec(opts["expert"])
        except KeyError as exc:
            raise CommandError(str(exc)) from exc
        version = services.register_live_version(spec=spec, model_id=opts["model"])
        self.stdout.write(
            self.style.SUCCESS(
                f"expert.{spec.key} v{version.semver} is LIVE -> {version.nugen_model_id} "
                f"(base {version.base_model})"
            )
        )
