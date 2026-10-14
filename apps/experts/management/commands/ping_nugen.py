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
        parser.add_argument("--debug", action="store_true", help="Dump raw wire format.")
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

        if opts["debug"]:
            self._debug_dump(client, model, messages, opts)
            return

        chars = 0
        try:
            if opts["no_stream"]:
                from apps.experts.nugen_client import extract_full_text

                resp = client.chat(
                    model=model,
                    messages=messages,
                    temperature=opts["temperature"],
                    max_tokens=opts["max_tokens"],
                )
                text = extract_full_text(resp)
                chars = len(text)
                self.stdout.write(text)
            else:
                for delta in client.chat_stream(
                    model=model,
                    messages=messages,
                    temperature=opts["temperature"],
                    max_tokens=opts["max_tokens"],
                ):
                    chars += len(delta)
                    self.stdout.write(delta, ending="")
                    self.stdout.flush()
                self.stdout.write("")
        except NugenError as exc:
            raise CommandError(f"{exc}\nHint: {exc.hint}\nBody: {exc.body}") from exc

        self.stdout.write("-" * 60)
        if chars == 0:
            raise CommandError(
                "HTTP succeeded but the model returned EMPTY content.\n"
                "Most likely the model is not actively deployed (aligned models "
                "can be spun down after inactivity), or the response shape differs.\n"
                "Run `python manage.py nugen_models` to check deployment status, "
                "and `ping_nugen --debug` to inspect the raw wire format."
            )
        self.stdout.write(self.style.SUCCESS(f"Nugen round-trip OK ({chars} chars)."))

    def _debug_dump(self, client, model, messages, opts):
        """Print the raw non-streaming JSON and raw streaming lines so we can
        see the exact response shape Nugen returns."""
        import json

        from apps.experts.nugen_client import DEFAULT_TIMEOUT

        payload_base = {
            "model": model,
            "messages": [m.as_dict() for m in messages],
            "temperature": opts["temperature"],
            "max_tokens": opts["max_tokens"],
        }

        self.stdout.write(self.style.WARNING("\n=== RAW NON-STREAM JSON ==="))
        resp = client._session.post(
            client._url(client.EP_CHAT),
            headers=client._headers(),
            json={**payload_base, "stream": False},
            timeout=DEFAULT_TIMEOUT,
        )
        self.stdout.write(f"HTTP {resp.status_code}")
        self.stdout.write(json.dumps(resp.json(), indent=2)[:3000])

        self.stdout.write(self.style.WARNING("\n=== RAW STREAM LINES (repr) ==="))
        resp = client._session.post(
            client._url(client.EP_CHAT),
            headers=client._headers(),
            json={**payload_base, "stream": True},
            stream=True,
            timeout=DEFAULT_TIMEOUT,
        )
        self.stdout.write(f"HTTP {resp.status_code}  content-type={resp.headers.get('content-type')}")
        count = 0
        for line in resp.iter_lines(decode_unicode=True):
            self.stdout.write(repr(line))
            count += 1
            if count >= 15:
                self.stdout.write("... (truncated)")
                break
