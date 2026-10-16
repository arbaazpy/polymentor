# PolyMentor

> An AI tech-interview coach built on [Nugen](https://nugen.in). A **router (mother) model** splits each request across a fleet of **domain-aligned expert models** (DSA, system design, behavioral, resume, interviewer), an **aggregator** reconciles their answers when they disagree, and the system **improves over time** from candidate feedback through an eval-gated learning loop.

Built by [Arbaaz Ali](https://www.linkedin.com/in/arbaaz02/) · [GitHub](https://github.com/arbaazpy/polymentor)

---

## What it does

Ask *"Design a URL shortener for 1B redirects/day. I have 2 weeks to ship."* and:

1. **The router** sees three lanes in one request (system design, hashing math, deadline framing) and fans out to three experts in parallel. Each expert only answers its part.
2. **Each expert** is a Llama-3.2-3B model aligned on its own corpus on Nugen, grounded with BM25 retrieval over that corpus, and shows its sources and confidence.
3. **The aggregator** extracts concrete decisions from each answer (code length, datastore, QPS, storage, cache strategy). When two experts disagree, the lane that **owns** that decision wins. For example, `storage.*` belongs to system design and `hash.*` belongs to DSA. Every ruling is shown, never hidden.
4. **A coordinator model** streams one combined plan that follows the rulings and credits each step to its expert.
5. **Thumbs up/down and corrections** become learned exemplars. After an admin approves them, they are retrieved for future answers immediately and exported to re-align the expert. A new expert version only goes live if it passes the benchmark gate.

Single-domain questions go to one expert. If that expert tries to hand the question off ("DELEGATE: …"), the router **arbitrates**: it honours the handoff only when the request carries signal for the target lane. Otherwise it vetoes the handoff and the expert abstains honestly instead of bouncing the user around.

## Architecture

```
request ─► router (keyword hints + per-lane corpus BM25, LLM fallback)
             │ one lane                     │ several lanes
             ▼                              ▼
        expert (strict lane prompt)    experts in parallel (collaborative prompt)
             │ DELEGATE?                    │
             ▼                              ▼
        router arbitration             decision extraction ─► reconcile by lane ownership
             │                              │
             ▼                              ▼
        answer / honest abstain        coordinator synthesis (streamed)
                         └──────► Turn saved (permalink) ◄──────┘
                                       │ feedback
                                       ▼
            learned exemplars ─► admin approval ─► retrieval now, re-align later ─► eval gate
```

| App | Responsibility |
|---|---|
| `apps/experts` | Fleet manifest (`fleet.py`), Nugen client (SSE, confidence frames, retries), grounding (BM25), lane prompts, expert versions |
| `apps/routing` | Lane scoring, multi-lane split, delegation arbitration |
| `apps/aggregation` | Turn orchestration, decision extraction, reconciliation, synthesis, SSE endpoint, rate limits |
| `apps/alignment` | Benchmark runner, grader, promotion gate |
| `apps/feedback` | Feedback, exemplar mining, lane health, re-alignment export |
| `apps/sessions` | Persisted turns (shareable `/t/<id>` permalinks) |

### The expert fleet

| Expert | Lane | Model on Nugen | Status |
|---|---|---|---|
| `dsa` | Algorithms & data structures | `model_01m4zv707z9qzt7z` | aligned + grounded, benchmarked |
| `sysdes` | System design | `model_01m4zyvrxn5f988a` | aligned + grounded, benchmarked |
| `behav` | Behavioral / STAR | `model_01m50db0jrcphjrw` | aligned + grounded, benchmarked |
| `resume` | Resume & role fit | Llama-3.2-3B base | grounded only (by design, see below) |
| `mock` | Interviewer / rubric | Llama-3.2-3B base | grounded only (by design, see below) |

Alignment budget went to the three lanes with gold benchmarks. The evaluation showed that grounding, not alignment, drives the score (see below), so `resume` and `mock` run grounded on the base model. Re-aligning them later is one `register_expert` call.

## Evaluation (summary)

Each expert lane has 20 gold questions, including deliberate out-of-lane and out-of-corpus questions that should be abstained or delegated. Each benchmark is run in four modes:

| Mode | dsa | sysdes |
|---|---|---|
| base | 0.49 | 0.32 |
| base + grounding | 0.76 | 0.82 |
| aligned | 0.51 | 0.29 |
| **aligned + grounding** | **0.81** | **0.82** |

The router sends **59 of 60** benchmark questions to the right expert, including every planted cross-lane question. Those questions were exactly the failures the isolated experts made: the system-design expert answering Dijkstra itself, and the DSA expert delegating Dinic's algorithm away. Full methodology, the behavioral results, and the per-question failure analysis are in [`EVALUATION.md`](EVALUATION.md).

## Quickstart

```bash
uv sync
cp .env.example .env              # set NUGEN_API_KEY
uv run python manage.py migrate
uv run python manage.py sync_experts   # registers the fleet's models + latest eval metrics
uv run python manage.py runserver      # http://127.0.0.1:8000
```

Tests need no network (Nugen is mocked): `uv run pytest` · lint: `uv run ruff check .`

## Operating the learning loop

```bash
# Benchmark an expert in all four modes (writes evals/<lane>/<ts>.json)
uv run python manage.py run_benchmark dsa

# Turn feedback into PENDING exemplars; approve them in /admin
uv run python manage.py mine_feedback
# Export approved exemplars as a re-alignment document (corpora/<lane>/learned.md)
uv run python manage.py mine_feedback --export dsa

# After re-aligning on Nugen: benchmark the candidate and promote it only if it
# does not regress on overall score or abstention (otherwise recorded as GATED_OUT)
uv run python manage.py promote_expert dsa --model <new_model_id>
```

`/experts` shows every expert's live version, its version history, its latest benchmark scores, and feedback health. A lane is flagged "re-align recommended" when it has at least 5 downvotes and a downvote rate of 30% or more.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` · `/t/<id>` · `/experts` | Ask page, saved turn, fleet & history |
| POST | `/v1/turns/stream` | Run a turn; SSE events `route`, `expert_start`, `expert`, `delegation`, `reconciliation`, `delta`, `done` |
| POST | `/v1/turns/<id>/feedback` | `{expert, rating: 1 \| -1, correction?}` |
| POST | `/v1/admin/mine` | Mine feedback (Bearer `ADMIN_BEARER_TOKEN`) |
| POST | `/v1/ask`, `/v1/ask/stream` | Single grounded expert, no routing (dev only; `ENABLE_RAW_ASK`) |
| GET | `/healthz` | Liveness, git sha, live expert count |

Abuse controls: requests per IP are rate-limited (IPs are stored only as salted hashes), there is a global daily turn cap, and prompt length is capped. All of these are configurable in `config/settings.py`.

## Deploy (Render)

`render.yaml` defines a free web service plus a free Postgres database. `build.sh` installs dependencies with uv, then runs collectstatic, migrate and `sync_experts`. To deploy:

1. In Render, create a **Blueprint** from this repo.
2. Set `NUGEN_API_KEY`. Optionally set `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` to create an admin user for approving exemplars.
3. If the service name differs from `polymentor`, update `DJANGO_CSRF_TRUSTED_ORIGINS` to match.

## Stack

Django 6 · Django REST Framework · Postgres (prod) / SQLite (dev) · gunicorn (gthread, for streaming) · whitenoise · Tailwind + vanilla JS (streaming via fetch) · `uv`. No Docker.

## License

Code: MIT. Corpora under `corpora/` are public-knowledge syntheses, with no copyrighted long-form text and no private or organizational data.
