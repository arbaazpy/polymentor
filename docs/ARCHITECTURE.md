# PolyMentor — Architecture

> **Design document, written before the build.** What shipped is described in the
> [README](../README.md) and measured in [EVALUATION.md](../EVALUATION.md). Main changes
> during the build: turns run synchronously in gunicorn thread workers (no Celery worker
> or Redis); the UI is Tailwind + vanilla JS streaming (no HTMX); experts' decisions are
> extracted from prose because 3B models ignored claim tags; re-alignment is done on the
> Nugen dashboard and promoted through the `promote_expert` eval gate; the router is
> keyword + corpus BM25 with an LLM fallback rather than a separately aligned model.

> AI tech-interview coach powered by a **router (mother) model** that delegates to a **fleet of domain-aligned expert models** on Nugen, aggregates their expertise, and **improves over time** from candidate feedback and benchmark drift.

---

## 1. Problem & product

**User pain.** Interview prep is fragmented: DSA on one platform, system design on YouTube, behavioral on blogs, resume feedback on paid reviewers, mocks on expensive humans. Generic LLMs answer all of these — fluently, often wrongly, and without an evaluation loop.

**Product.** A single conversational surface where a **router** figures out which specialist(s) a question needs, each specialist is a **Nugen-aligned expert** trained on a curated corpus for that lane, and an **aggregator** fuses expert outputs for compound tasks like full mock interviews.

**Why it fits the brief.**
- Mother/router → expert fleet ✅
- Aggregates fleet expertise ✅
- Improves over time via feedback → re-alignment ✅
- Meaningful real-world problem ✅
- Meta-relevant to Nugen's own hiring thesis ✅
- Scope realistic for 96 h + $50 credits ✅

---

## 2. Expert fleet

Five lanes. Each expert = one Nugen domain-aligned model on a small, high-quality public corpus + a gold benchmark.

| # | Expert           | Lane                                            | Corpus (public only)                                                                 | Base model                  |
|---|------------------|-------------------------------------------------|--------------------------------------------------------------------------------------|-----------------------------|
| 1 | `expert.dsa`     | Data structures & algorithms reasoning          | Curated notes on complexity, patterns (two-pointer, sliding window, DP, graphs)      | small `alignment_ready` reasoning model |
| 2 | `expert.sysdes`  | System design (scalability, consistency, caches)| Classic distributed systems notes, CAP, consistent hashing, queueing, caching        | small `alignment_ready` reasoning model |
| 3 | `expert.behav`   | Behavioral / STAR / leadership principles       | Structured STAR templates, situational frameworks, bias-free rubrics                 | small instruction model     |
| 4 | `expert.resume`  | Resume & JD-fit critique                        | Resume-writing style guides, bullet-impact patterns, keyword/JD-alignment heuristics | small instruction model     |
| 5 | `expert.mock`    | Interviewer persona (asks follow-ups, scores)   | Interview rubrics, probing patterns, scoring criteria                                | small instruction model     |

**Corpus hygiene:** `.md`/`.txt` only, public knowledge, no org/PII content, metadata (version, effective date), per the lessons from the first exercise.

**Benchmark per expert:** 15–25 gold Q&A pairs grounded in that lane's corpus. Used both to (a) create the alignment and (b) regression-test after every re-alignment.

---

## 3. High-level architecture (C4 container view)

```mermaid
flowchart LR
  subgraph Client
    UI[Web UI<br/>Next.js or Django templates]
    CLI[Optional CLI]
  end

  subgraph API["PolyMentor API (Django + DRF)"]
    GW[REST + SSE gateway]
    ROUTER[Router service<br/>intent + expert selection]
    AGG[Aggregator service<br/>fuse + reconcile]
    FB[Feedback service]
    EVAL[Eval harness]
    JOBS[(Celery workers<br/>+ Redis)]
  end

  subgraph Nugen["Nugen Platform"]
    MOTHER[Router Model<br/>aligned on routing corpus]
    E1[expert.dsa]
    E2[expert.sysdes]
    E3[expert.behav]
    E4[expert.resume]
    E5[expert.mock]
  end

  subgraph Data["Postgres + Object store"]
    SESS[(Sessions / turns)]
    FBS[(Feedback events)]
    CORP[(Corpora versions)]
    BENCH[(Benchmarks + eval runs)]
    METRICS[(Routing + answer metrics)]
  end

  UI --> GW
  CLI --> GW
  GW --> ROUTER
  ROUTER -->|classify| MOTHER
  ROUTER -->|dispatch 1..N| E1 & E2 & E3 & E4 & E5
  ROUTER --> AGG
  AGG --> GW
  GW --> FB --> FBS
  JOBS -->|nightly| EVAL --> BENCH
  JOBS -->|weekly| MOTHER
  JOBS -->|weekly| E1 & E2 & E3 & E4 & E5
  SESS <--> GW
  CORP <--> JOBS
  METRICS <--> ROUTER
```

**Why a Nugen-aligned router (not just an if/else).** A routing model aligned on labeled intents handles ambiguity ("prep me for a Google backend loop next week" → multi-expert) and lets the router *itself* get better from feedback — same alignment pipeline as experts. We keep a cheap **rules fast-path** for obvious queries to save credits.

---

## 4. Router (mother) design

### Responsibilities
1. **Intent classification** — one or more of `{dsa, sysdes, behav, resume, mock, meta}`.
2. **Decomposition** — split compound requests into sub-prompts per expert.
3. **Expert selection** — pick 1–N experts + a `strategy` (`single | parallel | pipeline | debate`).
4. **Budgeting** — cap tokens / parallel fan-out based on query class.
5. **Confidence** — emit a routing confidence; low confidence → ask clarifying question instead of hallucinating a route.

### Routing corpus (what the router is aligned on)
A JSONL dataset of `{query, labels[], strategy, rationale}` ~300–500 examples drawn from public interview questions, synthetic variations, and edge cases (ambiguous, out-of-scope, PII attempts, prompt-injection).

### Strategies
| Strategy | When | Flow |
|----------|------|------|
| `single`   | Pure lane query ("explain quicksort") | 1 expert → return |
| `parallel` | Independent sub-questions ("DSA tips + resume review") | fan-out → aggregator concatenates with headings |
| `pipeline` | Dependent steps ("design URL shortener, then grill me on it") | `sysdes` → `mock` consumes previous answer |
| `debate`   | High-stakes / low-confidence answers | 2 experts answer same prompt → aggregator reconciles with a rubric |

---

## 5. Aggregator design

Not a prompt-stuffing hack — a small, explicit reconciler:

1. **Normalize** each expert output to `{answer, citations[], confidence, caveats[]}`.
2. **Deduplicate** overlapping claims.
3. **Reconcile** contradictions via rubric: prefer the lane-owning expert for its sub-claim.
4. **Compose** a final response with per-section attribution: *"System design (expert.sysdes)…"*, *"Behavioral framing (expert.behav)…"*.
5. **Abstain-aware**: if any critical expert returned "insufficient evidence," the aggregator surfaces it instead of papering over.

Mock interview is the showcase: `mock` plays interviewer; after each candidate answer, the router silently calls the relevant lane expert for a model answer; aggregator produces per-turn **scored feedback** (clarity, correctness, depth) and an end-of-session rubric.

---

## 6. Improvement loop (how the system gets better over time)

```mermaid
flowchart TD
  U[User turn] --> R[Router → Experts → Aggregator]
  R --> A[Answer + per-expert attribution]
  A --> FB1[Explicit feedback<br/>👍/👎 + 1-5 + comment]
  A --> FB2[Implicit signals<br/>regenerate, copy, follow-up gap]
  FB1 & FB2 --> STORE[(Feedback store)]
  STORE --> MINER[Nightly feedback miner]
  MINER --> GAPS[Gap report per expert<br/>low-score topics, missed intents]
  GAPS --> CURATE[Human-in-loop curation<br/>me, during exercise]
  CURATE --> NEWCORP[Corpus delta + new gold Q&A]
  NEWCORP --> REALIGN[Weekly re-alignment job<br/>Celery → Nugen alignment API]
  REALIGN --> EVAL[Benchmark regression]
  EVAL -->|pass gates| PROMOTE[Promote new expert version]
  EVAL -->|fail| ROLLBACK[Keep previous version]
  PROMOTE --> R
```

**Gates before promotion (from the enterprise brief in the earlier exercise):**
- ≥85% rubric accuracy on that expert's gold set
- ≥90% correct abstention on insufficient-evidence items
- ≤5% critical hallucination
- No regression >3 pp on any peer expert's shared-topic items

**Router improvement:** feedback on *wrong routing* (user flags "this needed system design, not DSA") is a labeled example that feeds the router's own re-alignment set.

**Credit-aware fallback:** if Nugen credits are tight, "improvement" degrades gracefully to **in-context exemplar refresh** (new few-shots pulled from top-rated past turns) without re-alignment — same code path, just skips the training job.

---

## 7. Data model

```mermaid
erDiagram
  USER ||--o{ SESSION : has
  SESSION ||--o{ TURN : contains
  TURN ||--o{ EXPERT_CALL : fans_out
  TURN ||--o{ FEEDBACK : receives
  EXPERT ||--o{ EXPERT_CALL : handles
  EXPERT ||--o{ EXPERT_VERSION : versioned
  EXPERT_VERSION ||--o{ ALIGNMENT_RUN : produced_by
  CORPUS ||--o{ CORPUS_VERSION : versioned
  CORPUS_VERSION ||--o{ ALIGNMENT_RUN : used_in
  BENCHMARK ||--o{ EVAL_RUN : scored_in
  EVAL_RUN }o--|| EXPERT_VERSION : evaluates

  USER { uuid id string email string handle }
  SESSION { uuid id uuid user_id string title datetime created_at }
  TURN { uuid id uuid session_id string user_input jsonb router_decision jsonb aggregated_answer datetime created_at }
  EXPERT_CALL { uuid id uuid turn_id string expert_key string model_id jsonb request jsonb response float latency_ms int tokens_in int tokens_out }
  FEEDBACK { uuid id uuid turn_id string kind int rating string comment jsonb signals datetime created_at }
  EXPERT { string key string lane string description }
  EXPERT_VERSION { uuid id string expert_key string nugen_model_id string status datetime created_at jsonb metrics }
  CORPUS { string key string lane }
  CORPUS_VERSION { uuid id string corpus_key int version string storage_uri datetime created_at }
  ALIGNMENT_RUN { uuid id string nugen_alignment_id string base_model string status datetime started_at datetime finished_at }
  BENCHMARK { uuid id string lane int num_items string storage_uri }
  EVAL_RUN { uuid id uuid benchmark_id uuid expert_version_id jsonb per_item jsonb aggregates datetime created_at }
```

Everything about an answer is traceable back to the exact `expert_version` + `corpus_version` + `benchmark` scores — this is the "audit log" story from the enterprise brief, applied to our own product.

---

## 8. Key sequence diagrams

### 8.1 Single-expert query

```mermaid
sequenceDiagram
  participant U as User
  participant API as PolyMentor API
  participant R as Router
  participant M as Nugen router model
  participant E as expert.dsa
  participant DB as Postgres
  U->>API: POST /v1/ask {"q":"explain Kadane's algorithm"}
  API->>R: classify + plan
  R->>M: route(q)
  M-->>R: {labels:["dsa"], strategy:"single", conf:0.94}
  R->>E: infer(q, system=lane_prompt)
  E-->>R: answer + confidence
  R->>DB: persist turn + expert_call
  R-->>API: aggregated_answer
  API-->>U: SSE stream
```

### 8.2 Mock interview (pipeline + aggregator)

```mermaid
sequenceDiagram
  participant U as Candidate
  participant API as PolyMentor API
  participant R as Router
  participant Sd as expert.sysdes
  participant Mk as expert.mock
  participant Be as expert.behav
  participant Ag as Aggregator

  U->>API: start_mock("backend SDE-2, Google")
  API->>R: plan session
  R->>Mk: open with sysdes question
  Mk-->>U: "Design a URL shortener for 1B/day"
  U->>API: candidate answer
  R->>Sd: grade sub-claims
  R->>Be: grade communication (STAR)
  Sd-->>Ag: {score, gaps}
  Be-->>Ag: {score, gaps}
  Ag-->>Mk: next probing question using gaps
  Mk-->>U: follow-up
  Note over API: repeat N turns
  Ag-->>U: end-of-session rubric + per-lane scores
```

### 8.3 Feedback → re-alignment

```mermaid
sequenceDiagram
  participant U as User
  participant API as PolyMentor API
  participant W as Celery worker
  participant N as Nugen alignment API
  participant Ev as Eval harness
  U->>API: 👎 on turn T (comment)
  API->>DB: FEEDBACK insert
  Note over W: nightly cron
  W->>DB: mine low-score topics per expert
  W->>DB: build corpus_delta + new gold Qs
  W->>N: POST /documents + /alignment-projects/create
  N-->>W: alignment_id
  W->>N: poll until READY
  W->>N: deploy new expert_version
  W->>Ev: run benchmark on new version
  Ev-->>W: metrics
  alt gates pass
    W->>DB: promote expert_version
  else gates fail
    W->>DB: keep previous version + log
  end
```

---

## 9. API surface (DRF)

| Method | Path                              | Purpose |
|--------|-----------------------------------|---------|
| POST   | `/v1/sessions`                    | Create session |
| POST   | `/v1/sessions/{id}/ask`           | Single-turn ask (SSE stream) |
| POST   | `/v1/sessions/{id}/mock/start`    | Begin mock interview |
| POST   | `/v1/sessions/{id}/mock/answer`   | Submit candidate turn |
| POST   | `/v1/turns/{id}/feedback`         | 👍/👎 + rating + comment |
| GET    | `/v1/experts`                     | List experts + current versions + last metrics |
| GET    | `/v1/experts/{key}/versions`      | Version history + eval scores |
| POST   | `/v1/admin/realign/{expert_key}`  | Trigger re-alignment (admin, Celery) |
| GET    | `/v1/admin/eval/{run_id}`         | Eval run detail |

Auth: simple token for admin endpoints; session cookie or anon-session for user endpoints (showcase, not a real auth product).

---

## 10. Tech stack

Following project rules (Django-first, services layer, ORM, DRF, Celery/Redis, Postgres):

- **Backend:** Django 5 + Django REST Framework
- **Business logic:** `services.py` per app (`routing`, `experts`, `aggregation`, `feedback`, `alignment`)
- **DB:** Postgres (Supabase or Neon free tier)
- **Cache / queue:** Redis (Upstash free tier)
- **Workers:** Celery (one worker + beat for cron)
- **Frontend:** minimal — Django templates + HTMX + Tailwind (fast; no SPA cost). Fallback: Next.js if time.
- **Streaming:** SSE via DRF streaming response
- **Nugen client:** thin wrapper around `/documents`, `/benchmarks`, `/alignment-projects`, `/models/aligned`, `/models/{id}/deployment`, `/inference/chat/completions`
- **Deployment:** Render.com or Railway (free/cheap, HTTPS, env vars, Postgres+Redis add-ons). Public URL out of the box.
- **Observability:** structured JSON logs + a `/healthz` + a `/metrics` page showing routing distribution + per-expert scores (also serves as demo visualization).
- **Testing:** pytest-django for services + a smoke test that mocks Nugen client.

Django apps:
```
polymentor/
  apps/
    accounts/
    sessions/        # Session, Turn models + views
    routing/         # Router service, strategies
    experts/         # Expert, ExpertVersion, Nugen client
    aggregation/     # Aggregator service
    feedback/        # Feedback model + miner
    alignment/       # Alignment runs, eval harness, Celery tasks
    corpora/         # Corpus versions + upload utilities
  config/
  services.py per app
```

---

## 11. Non-goals (explicit cuts)

- Real user auth / billing
- Multi-tenant isolation
- Vector DB / embeddings-based RAG in v1 (we lean on train-time alignment; **optional add-on** if time permits for `expert.sysdes` where facts are large)
- Mobile app
- Fine-tuning our own models outside Nugen

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Alignment is weak on small corpora (we saw this in exercise 1) | Keep lanes narrow; add high-repetition definition blocks; evaluate with gold phrases; add RAG fallback for `sysdes` if needed |
| Credits run out | Rules-based routing fast-path; cache expert outputs by (lane, normalized_prompt); offer "demo mode" with cached responses |
| 96 h is tight | Day-by-day milestones (below); cut `debate` strategy if time |
| Re-alignment latency (5–15 min) | Done out-of-band in Celery; UI shows "new version candidate pending" badge |
| Prompt injection via mock interview user input | Strip control tokens, cap length, never pass raw user text as system prompt |
| Public URL abuse | Per-IP rate limit (Django ratelimit); global daily token cap |

---

## 13. 96-hour execution plan

| Window | Deliverable |
|--------|-------------|
| **H 0–8** | Repo scaffold, Django apps, Postgres, Redis, Celery, Nugen client wrapper, 1 expert end-to-end (`expert.dsa`) deployed and callable |
| **H 8–24** | Build remaining 4 corpora + benchmarks, kick off alignments in parallel, draft routing corpus, deploy mother router |
| **H 24–48** | Router + aggregator services, `single`/`parallel`/`pipeline` strategies, SSE streaming, basic UI (ask + mock) |
| **H 48–72** | Feedback capture, eval harness, nightly miner (Celery beat), re-alignment Celery task, admin metrics page |
| **H 72–88** | Polish UI, mock-interview rubric, caching + rate-limits, deploy to Render with Postgres/Redis add-ons, write README + loom demo |
| **H 88–96** | Buffer: fix the one thing that will break, record demo video, submit |

---

## 14. What a reviewer will see

1. **Public URL** → land on PolyMentor, pick "Ask" or "Mock interview."
2. Ask a question → see **router decision** ("sent to `expert.sysdes`, confidence 0.91") + streamed answer with per-expert attribution.
3. Start a mock → multi-turn session with per-turn scoring and end rubric.
4. 👎 any answer → feedback captured → `/admin/experts` shows pending re-alignment candidate.
5. `/admin/metrics` → routing distribution, per-expert accuracy over versions, benchmark trend chart.
6. **GitHub repo** → clean Django structure, services layer, tests, Mermaid diagrams in `ARCHITECTURE.md`, honest `EVALUATION.md` with what alignment did and did not lock in.

---

## 15. Open design questions to confirm before coding

1. **UI:** HTMX+Tailwind (fastest to ship) or Next.js (nicer demo)?
2. **Hosting:** Render vs Railway vs Fly — any preference / existing account?
3. **Routing fast-path:** okay to use keyword rules + fall back to Nugen router model for ambiguity? (Saves credits.)
4. **RAG:** okay to defer RAG to v1.1 and rely purely on train-time alignment, with a documented fallback path?
5. **Mock scope:** full 45-min flow, or 10–15 min "lightning mock" for the demo?
6. **Learning loop demo:** should the demo include a *scripted* re-alignment run (pre-recorded eval delta) so the reviewer can see improvement without waiting 15 min?
