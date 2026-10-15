# PolyMentor

> An AI tech-interview coach built on [Nugen](https://nugen.in). A **router (mother) model** delegates each question to a fleet of **domain-aligned expert models** (DSA, system design, behavioral, resume, interviewer), an **aggregator** reconciles their answers — including when experts disagree — and the system **improves over time** from candidate feedback via eval-gated re-alignment.

Built by [Arbaaz Ali](https://www.linkedin.com/in/arbaaz02/) · [GitHub](https://github.com/arbaazpy/polymentor)

---

## Why this exists

Generic LLMs answer interview-prep questions fluently but often wrongly, with no
evaluation loop. PolyMentor treats each domain as a separately **aligned** model
with its own corpus and gold benchmark, routes intelligently between them, and
shows its work: which expert answered, how confident, and how disagreements were
resolved.

See [`docs/`](docs/) for the full design:
[architecture](docs/ARCHITECTURE.md) ·
[corpus & benchmarks](docs/CORPUS_DESIGN.md) ·
[learning loop](docs/LEARNING_LOOP.md) ·
[the "wow" interaction](docs/WOW_MOMENT.md) ·
[UX walkthrough](docs/UX_WALKTHROUGH.md) ·
[plan](docs/PLAN.md)

---

## Stack

Django 5/6 + Django REST Framework · Celery + Redis · Postgres (prod) / SQLite (dev) ·
HTMX + Tailwind · `uv` for env management. No Docker required.

---

## Quickstart

```bash
# 1. Install deps (uv manages the venv)
uv sync

# 2. Configure environment
cp .env.example .env
#   → set NUGEN_API_KEY=...  (get one from the Nugen platform)
#   → optionally set NUGEN_DEFAULT_MODEL=<a deployed model id> for smoke tests

# 3. Migrate and run
uv run python manage.py migrate
uv run python manage.py runserver

# 4. Health check
curl http://127.0.0.1:8000/healthz
# {"ok": true, "version": "<git sha>", "experts_live": 0}
```

### Verify Nugen connectivity

```bash
uv run python manage.py ping_nugen --model <deployed_model_id> --prompt "Say hi in 5 words"
```

### Register an expert and benchmark it

```bash
# Record a model aligned + deployed in the Nugen dashboard as the LIVE dsa expert
uv run python manage.py register_expert dsa --model <deployed_model_id>

# Score base / aligned / grounded configurations on the gold benchmark
uv run python manage.py run_benchmark dsa
```

Results and methodology: [`EVALUATION.md`](EVALUATION.md).

---

## API (early)

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/healthz`        | Liveness + live expert count |
| POST | `/v1/ask`         | Grounded expert ask; returns answer, confidence, cited sections |
| POST | `/v1/ask/stream`  | Same, as SSE events (`meta`, `delta`, `confidence`, `done`) |

More endpoints (sessions, mock interview, feedback, experts registry, admin)
land as the build progresses — see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Development

```bash
uv run pytest        # tests (no network required; Nugen is mocked)
uv run ruff check .  # lint
```

---

## License

Code: MIT (see below). Corpora under `corpora/` are public-knowledge synthesis,
no copyrighted long-form text and no private/organizational data.
