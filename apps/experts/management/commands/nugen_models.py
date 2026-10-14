"""List Nugen base and aligned models with their deployment status.

Use this to see what is actually available before building on it:

    uv run python manage.py nugen_models

Helps answer: "is my aligned model still deployed?" and "which base model can
I hit right now to validate streaming?"
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.experts.nugen_client import NugenClient, NugenError


class Command(BaseCommand):
    help = "List Nugen base + aligned models and deployment status."

    def add_arguments(self, parser):
        parser.add_argument("--raw", action="store_true", help="Dump raw JSON responses.")

    def handle(self, *args, **opts):
        if not settings.NUGEN_API_KEY:
            raise CommandError("NUGEN_API_KEY is not set in your environment/.env")
        client = NugenClient()

        self.stdout.write(self.style.NOTICE("=== BASE MODELS ==="))
        try:
            base = client.list_base_models()
        except NugenError as exc:
            self.stdout.write(self.style.ERROR(f"base models failed: {exc} ({exc.hint})"))
            base = None
        if base is not None:
            if opts["raw"]:
                self.stdout.write(json.dumps(base, indent=2)[:4000])
            else:
                self._print_models(base)

        self.stdout.write(self.style.NOTICE("\n=== ALIGNED MODELS ==="))
        try:
            aligned = client.list_aligned_models()
        except NugenError as exc:
            self.stdout.write(self.style.ERROR(f"aligned models failed: {exc} ({exc.hint})"))
            aligned = None
        if aligned is not None:
            if opts["raw"]:
                self.stdout.write(json.dumps(aligned, indent=2)[:4000])
            else:
                self._print_models(aligned)

    def _print_models(self, payload):
        """Best-effort pretty print across possible response shapes."""
        items = payload
        if isinstance(payload, dict):
            for key in ("data", "models", "results", "items"):
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
        if not isinstance(items, list):
            self.stdout.write(json.dumps(payload, indent=2)[:2000])
            return
        if not items:
            self.stdout.write("  (none)")
            return
        for m in items:
            if not isinstance(m, dict):
                self.stdout.write(f"  {m}")
                continue
            mid = m.get("model_id") or m.get("id") or m.get("name") or "?"
            status = m.get("status") or m.get("deployment_status") or ""
            ready = m.get("alignment_ready")
            extra = []
            if status:
                extra.append(f"status={status}")
            if ready is not None:
                extra.append(f"alignment_ready={ready}")
            self.stdout.write(f"  {mid}  {' '.join(extra)}")
