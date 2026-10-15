"""Bootstrap one or more experts end-to-end on Nugen.

Pipeline per expert (from the fleet manifest):
  upload corpus -> (benchmark) -> create alignment -> poll -> deploy -> poll
  -> record a LIVE ExpertVersion and point the Expert at it.

Usage:
  # preview everything without spending credits
  uv run python manage.py bootstrap_experts dsa --dry-run

  # real run (uploads, aligns, deploys; ~5-15 min for deploy)
  uv run python manage.py bootstrap_experts dsa

  # choose how the benchmark is produced
  uv run python manage.py bootstrap_experts dsa --benchmark upload   # our gold JSON (default)
  uv run python manage.py bootstrap_experts dsa --benchmark auto     # Nugen generates
  uv run python manage.py bootstrap_experts dsa --benchmark none

Run with your own key in .env. The key is never printed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.experts import services
from apps.experts.fleet import FLEET, ExpertSpec, get_spec
from apps.experts.nugen_client import NugenClient, NugenError

READY_STATES = {"READY", "COMPLETED", "SUCCEEDED", "SUCCESS", "DONE"}
FAIL_STATES = {"FAILED", "ERROR", "CANCELLED", "CANCELED"}
DEPLOYED_STATES = {"DEPLOYED", "LIVE", "ACTIVE"}
MIN_CORPUS_WORDS = 500  # Nugen rejects documents with fewer words.


class Command(BaseCommand):
    help = "Upload corpus, align, and deploy experts from the fleet manifest."

    def add_arguments(self, parser):
        parser.add_argument("experts", nargs="*", help="Expert keys (default: all).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--benchmark",
            choices=["upload", "auto", "none"],
            default="upload",
            help="How to produce the alignment benchmark.",
        )
        parser.add_argument("--poll-timeout", type=int, default=1800, help="Seconds.")
        parser.add_argument("--poll-interval", type=int, default=15, help="Seconds.")

    def handle(self, *args, **opts):
        keys = opts["experts"] or list(FLEET)
        for key in keys:
            try:
                spec = get_spec(key)
            except KeyError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Expert: {key} ==="))
            if opts["dry_run"]:
                self._dry_run(spec, opts)
            else:
                self._bootstrap(spec, opts)

    # -- dry run -----------------------------------------------------------
    def _dry_run(self, spec: ExpertSpec, opts):
        self.stdout.write(f"lane:        {spec.lane}")
        self.stdout.write(f"base_model:  {spec.base_model}")
        self.stdout.write(f"benchmark:   {opts['benchmark']}")
        for p in spec.corpus_paths:
            self._require_file(p)
            words = len(p.read_text().split())
            flag = "" if words >= MIN_CORPUS_WORDS else self.style.ERROR("  ** < 500 words! **")
            self.stdout.write(f"corpus:      {p}  ({words} words){flag}")
        bpath = spec.benchmark_path
        self._require_file(bpath)
        qa = json.loads(bpath.read_text())
        self.stdout.write(f"benchmark:   {bpath}  ({len(qa)} QA items)")
        self.stdout.write(self.style.NOTICE("Planned Nugen calls:"))
        self.stdout.write("  1. POST /api/v3/documents/create  (corpus files)")
        self.stdout.write("  2. poll  GET /api/v3/documents/{id}/status -> READY")
        if opts["benchmark"] == "upload":
            self.stdout.write("  3. POST /api/v3/benchmarks/upload  (gold QA)")
        elif opts["benchmark"] == "auto":
            self.stdout.write("  3. POST /api/v3/benchmarks/create  (auto from docs)")
        else:
            self.stdout.write("  3. (benchmark skipped)")
        self.stdout.write("  4. POST /api/v3/alignment-projects/create")
        self.stdout.write("  5. poll  GET /api/v3/alignment-projects/{id}/status -> READY")
        self.stdout.write("  6. GET  /api/v3/models/aligned  (resolve model_id)")
        self.stdout.write("  7. POST /api/v3/models/{id}/deployment")
        self.stdout.write("  8. poll  GET /api/v3/models/{id}/deployment/status -> DEPLOYED")
        self.stdout.write(self.style.SUCCESS("Dry run OK — no credits spent."))

    # -- real bootstrap ----------------------------------------------------
    def _bootstrap(self, spec: ExpertSpec, opts):
        if not settings.NUGEN_API_KEY:
            raise CommandError("NUGEN_API_KEY is not set in your environment/.env")
        client = NugenClient()
        timeout = opts["poll_timeout"]
        interval = opts["poll_interval"]

        try:
            # 1. upload corpus
            document_ids = self._upload_corpus(client, spec, timeout, interval)

            # 2. benchmark
            benchmark_id = self._make_benchmark(client, spec, opts, document_ids, timeout, interval)

            # 3. alignment
            alignment_id = self._create_alignment(client, spec, document_ids, benchmark_id)
            self._poll(
                "alignment",
                lambda: client.alignment_status(alignment_id),
                timeout,
                interval,
            )

            # 4. resolve aligned model id
            model_id = self._resolve_aligned_model(client, alignment_id)
            self.stdout.write(self.style.SUCCESS(f"aligned model_id: {model_id}"))

            # 5. deploy
            self.stdout.write("Deploying (async, typically 5-15 min)...")
            try:
                client.deploy_model(model_id)
            except NugenError as exc:
                # Already deployed is fine; re-raise anything else.
                if exc.status not in (400, 409):
                    raise
                self.stdout.write(self.style.WARNING(f"deploy returned {exc.status}: {exc.hint}"))
            self._poll(
                "deployment",
                lambda: client.deployment_status(model_id),
                timeout,
                interval,
                success_states=DEPLOYED_STATES,
                status_keys=("deployment_status", "status"),
            )

            # 6. record in DB
            self._record_version(spec, model_id)
            self.stdout.write(self.style.SUCCESS(f"Expert '{spec.key}' is LIVE on {model_id}"))
        except NugenError as exc:
            raise CommandError(
                f"Bootstrap failed for {spec.key}: {exc}\nHint: {exc.hint}\nBody: {exc.body}"
            ) from exc

    # -- steps -------------------------------------------------------------
    def _upload_corpus(self, client, spec, timeout, interval) -> list[str]:
        files: list[tuple[str, bytes]] = []
        for p in spec.corpus_paths:
            self._require_file(p)
            words = len(p.read_text().split())
            if words < MIN_CORPUS_WORDS:
                raise CommandError(
                    f"{p.name} has {words} words; Nugen requires >= {MIN_CORPUS_WORDS}. "
                    "Expand the file before uploading."
                )
            files.append((p.name, p.read_bytes()))
        self.stdout.write(f"Uploading {len(files)} corpus file(s)...")
        resp = client.create_document(files=files, categories=[spec.key])
        doc_ids = _extract_ids(resp, keys=("document_id", "id", "document_ids"))
        if not doc_ids:
            self.stdout.write(self.style.WARNING(f"upload response: {json.dumps(resp)[:500]}"))
            raise NugenError("Could not find a document id in the upload response.")
        for did in doc_ids:
            self._poll(
                f"document {did}",
                lambda did=did: client.document_status(did),
                timeout,
                interval,
            )
        return doc_ids

    def _make_benchmark(self, client, spec, opts, document_ids, timeout, interval) -> str | None:
        mode = opts["benchmark"]
        if mode == "none":
            return None
        if mode == "upload":
            qa = json.loads(spec.benchmark_path.read_text())
            self.stdout.write(f"Uploading gold benchmark ({len(qa)} items)...")
            resp = client.upload_benchmark(
                name=f"{spec.key}-gold",
                qa_items=qa,
                document_id=document_ids[0],
                filename=f"{spec.key}-benchmark.json",
            )
        else:  # auto
            self.stdout.write("Creating benchmark from documents (auto)...")
            resp = client.create_benchmark_from_documents(
                name=f"{spec.key}-auto", document_ids=document_ids, num_questions=10
            )
        bench_ids = _extract_ids(resp, keys=("benchmark_id", "id"))
        if not bench_ids:
            self.stdout.write(self.style.WARNING(f"benchmark response: {json.dumps(resp)[:500]}"))
            return None
        bench_id = bench_ids[0]
        self._poll(
            f"benchmark {bench_id}",
            lambda: client.benchmark_status(bench_id),
            timeout,
            interval,
        )
        return bench_id

    def _create_alignment(self, client, spec, document_ids, benchmark_id) -> str:
        self.stdout.write("Creating alignment project...")
        resp = client.create_alignment(
            name=f"polymentor-{spec.key}",
            base_model=spec.base_model,
            document_ids=document_ids,
            benchmark_id=benchmark_id,
            description=f"PolyMentor {spec.lane} expert",
        )
        ids = _extract_ids(resp, keys=("alignment_id", "id"))
        if not ids:
            self.stdout.write(self.style.WARNING(f"alignment response: {json.dumps(resp)[:500]}"))
            raise NugenError("Could not find an alignment id in the create response.")
        return ids[0]

    def _resolve_aligned_model(self, client, alignment_id) -> str:
        resp = client.list_aligned_models()
        items = resp.get("domain_aligned_models") if isinstance(resp, dict) else None
        if not items:
            items = _as_list(resp)
        for m in items or []:
            if not isinstance(m, dict):
                continue
            if str(m.get("alignment_id", "")).lower() == str(alignment_id).lower():
                mid = m.get("model_id") or m.get("id")
                if mid:
                    return mid
        raise NugenError(f"No aligned model found for alignment {alignment_id}.")

    def _record_version(self, spec: ExpertSpec, model_id: str):
        services.register_live_version(spec=spec, model_id=model_id)

    # -- polling -----------------------------------------------------------
    def _poll(
        self,
        label,
        status_fn,
        timeout,
        interval,
        *,
        success_states=READY_STATES,
        status_keys=("status", "state", "deployment_status"),
    ):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            resp = status_fn()
            status = _extract_status(resp, status_keys)
            if status != last:
                self.stdout.write(f"  {label}: {status}")
                last = status
            upper = (status or "").upper()
            if upper in success_states:
                return resp
            if upper in FAIL_STATES:
                raise NugenError(f"{label} failed with status={status}: {json.dumps(resp)[:500]}")
            time.sleep(interval)
        raise NugenError(f"{label} timed out after {timeout}s (last status={last}).")

    # -- utils -------------------------------------------------------------
    def _require_file(self, p: Path):
        if not p.exists():
            raise CommandError(f"Missing file: {p}")


def _as_list(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("data", "results", "items", "models"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def _extract_ids(resp, keys) -> list[str]:
    out: list[str] = []
    containers = [resp] + _as_list(resp)
    for c in containers:
        if not isinstance(c, dict):
            continue
        for k in keys:
            val = c.get(k)
            if isinstance(val, str):
                out.append(val)
            elif isinstance(val, list):
                out.extend(str(v) for v in val if v)
    # de-dup preserving order
    seen = set()
    result = []
    for x in out:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


def _extract_status(resp, keys) -> str:
    if isinstance(resp, dict):
        for k in keys:
            if resp.get(k):
                return str(resp[k])
        # sometimes nested under data/result
        for k in ("data", "result"):
            if isinstance(resp.get(k), dict):
                nested = _extract_status(resp[k], keys)
                if nested:
                    return nested
    return "UNKNOWN"
