"""Live smoke test against the Nugen API.

Run locally with your own key in .env:

    uv run python manage.py ping_nugen --model <model_id> --prompt "Say hi in 5 words"

If --model is omitted, uses NUGEN_DEFAULT_MODEL. Streams the response so you can
confirm the client, auth, and endpoint path all work end-to-end.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.experts.nugen_client import ChatMessage, NugenClient, NugenError


class Command(BaseCommand):
    help = "Send a test inference request to the Nugen API."

    def add_arguments(self, parser):
        parser.add_argument("--model", default=settings.NUGEN_DEFAULT_MODEL or "")
        parser.add_argument("--prompt", default="Say hello in exactly five words.")
        parser.add_argument("--no-stream", action="store_true")
        parser.add_argument("--max-tokens", type=int, default=128)
        parser.add_argument("--temperature", type=float, default=0.2)

    def handle(self, *args, **opts):
        if not settings.NUGEN_API_KEY:
            raise CommandError("NUGEN_API_KEY is not set in your environment/.env")
        model = opts["model"]
        if not model:
            raise CommandError("No model given and NUGEN_DEFAULT_MODEL is unset. Pass --model.")

        client = NugenClient()
        messages = [
            ChatMessage(role="system", content="You are a concise assistant."),
            ChatMessage(role="user", content=opts["prompt"]),
        ]
        self.stdout.write(self.style.NOTICE(f"Model: {model}"))
        self.stdout.write(self.style.NOTICE(f"Prompt: {opts['prompt']}"))
        self.stdout.write("-" * 60)

        try:
            if opts["no_stream"]:
                from apps.experts.nugen_client import extract_full_text

                resp = client.chat(
                    model=model,
                    messages=messages,
                    temperature=opts["temperature"],
                    max_tokens=opts["max_tokens"],
                )
                self.stdout.write(extract_full_text(resp))
            else:
                for delta in client.chat_stream(
                    model=model,
                    messages=messages,
                    temperature=opts["temperature"],
                    max_tokens=opts["max_tokens"],
                ):
                    self.stdout.write(delta, ending="")
                    self.stdout.flush()
                self.stdout.write("")
        except NugenError as exc:
            raise CommandError(f"{exc}\nHint: {exc.hint}\nBody: {exc.body}") from exc

        self.stdout.write("-" * 60)
        self.stdout.write(self.style.SUCCESS("Nugen round-trip OK."))
