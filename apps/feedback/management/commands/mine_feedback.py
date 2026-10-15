"""Turn new feedback into PENDING exemplars and print lane health.

uv run python manage.py mine_feedback
uv run python manage.py mine_feedback --export dsa   # write corpora/dsa/learned.md
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.experts.fleet import FLEET
from apps.feedback import services


class Command(BaseCommand):
    help = "Mine feedback into exemplars; optionally export a re-alignment corpus."

    def add_arguments(self, parser):
        parser.add_argument("--export", metavar="EXPERT", help="Export approved exemplars")

    def handle(self, *args, **opts):
        counts = services.mine_feedback()
        self.stdout.write(f"mined: {counts['created']} exemplars, {counts['skipped']} skipped")
        for row in services.lane_health():
            flag = "  <- re-align recommended" if row["realign_recommended"] else ""
            self.stdout.write(
                f"  {row['lane']:<7} up={row['up']} down={row['down']} "
                f"approved={row['approved_exemplars']} pending={row['pending_exemplars']}{flag}"
            )
        if opts["export"]:
            if opts["export"] not in FLEET:
                raise CommandError(f"Unknown expert {opts['export']}")
            path, words = services.export_realign_set(opts["export"])
            note = "" if words >= 500 else " (under Nugen's 500-word minimum; collect more)"
            self.stdout.write(self.style.SUCCESS(f"wrote {path} ({words} words){note}"))
