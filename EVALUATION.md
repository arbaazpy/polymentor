# Evaluation

How much does each layer of a PolyMentor expert actually contribute? This file
answers that with measured numbers, not intuition.

Raw reports, with every answer, score, missing key, confidence and latency:
- dsa: [`evals/dsa/20261015T143420.json`](evals/dsa/20261015T143420.json)
- sysdes: [`evals/sysdes/20261015T142113.json`](evals/sysdes/20261015T142113.json)

Reproduce with `uv run python manage.py run_benchmark <expert>`.

## Setup

| | |
|---|---|
| Benchmarks | 20 gold Q&A per expert: [`dsa.json`](benchmarks/dsa.json), [`sysdes.json`](benchmarks/sysdes.json) (definition, distinction, procedure, failure-mode, abstention) |
| Grader | Deterministic keyword groups ([`dsa.keys.json`](benchmarks/dsa.keys.json), [`sysdes.keys.json`](benchmarks/sysdes.keys.json)); a forbidden phrase zeroes an abstention item. A test asserts every gold answer passes its own key. |
| Base model | `meta-llama/Llama-3.2-3B-Instruct` |
| Aligned models | dsa `model_01m4zv707z9qzt7z`, sysdes `model_01m4zyvrxn5f988a`: Nugen domain alignments of the base on `corpora/<expert>/` |
| Grounding | BM25 over corpus sections (chunked to ≤900 chars), top 3 plus pinned scope/abstention rules, injected as reference notes |
| Decoding | temperature 0, max 400 tokens, same lane system prompt in every mode |

The four modes differ only in the model and whether notes are injected, so each
row isolates one layer.

## Results

### expert.dsa

| mode | overall | pass rate (≥0.75) | abstention | definition | distinction | failure | procedure | Nugen conf (pass / fail) |
|---|---|---|---|---|---|---|---|---|
| `base` | 0.49 | 0.40 | 0.00 | 0.48 | 0.53 | 0.66 | 0.55 | - |
| `base_grounded` | 0.76 | 0.70 | 0.50 | 0.81 | 0.94 | 0.71 | 0.67 | - |
| `aligned` | 0.51 | 0.35 | 0.00 | 0.47 | 0.55 | 0.72 | 0.57 | 0.81 / 0.79 |
| **`aligned_grounded`** | **0.81** | **0.75** | 0.50 | 0.86 | 1.00 | 0.85 | 0.67 | 0.80 / 0.83 |

### expert.sysdes

| mode | overall | pass rate (≥0.75) | abstention | definition | distinction | failure | procedure | Nugen conf (pass / fail) |
|---|---|---|---|---|---|---|---|---|
| `base` | 0.32 | 0.15 | 0.25 | 0.38 | 0.30 | 0.38 | 0.29 | - |
| `base_grounded` | 0.82 | 0.85 | 0.75 | 0.88 | 0.84 | 0.94 | 0.69 | - |
| `aligned` | 0.29 | 0.10 | 0.25 | 0.31 | 0.24 | 0.31 | 0.32 | 0.75 / 0.74 |
| **`aligned_grounded`** | **0.82** | **0.80** | 0.75 | 0.88 | 0.94 | 0.88 | 0.68 | 0.76 / 0.79 |

## What this says

1. **Grounding is the lever: +0.30 (dsa) and +0.50 (sysdes) overall.**
   Retrieved notes turn generic textbook answers into answers that use the
   corpus's precise framing (monotone predicates, shrink-from-left, idempotency
   keys collapsing retries, hybrid fanout). The gain is larger for sysdes, whose
   facts (capacity numbers, named patterns) the base model doesn't know.
2. **Nugen alignment alone does not move these metrics.** On both experts the
   aligned model scores within noise of the base: dsa +0.02, sysdes −0.03.
   Asked bare (no lane prompt, no notes), the sysdes model defined
   back-pressure as fluid pressure against a valve. A 3B adapter trained on
   about 2.5k words does not reliably absorb domain terminology. With
   grounding, aligned and base models perform about the same. For dsa, the
   aligned model is ahead (0.81 against 0.76). For sysdes, the base model
   has a slightly higher pass rate (0.85 against 0.80), which is a single
   question. PolyMentor keeps the aligned models as the expert endpoints
   (they're the unit the learning loop re-aligns and gates). Grounding is
   what makes them good today.
3. **Delegation works once rules are in context.** Without notes, both base
   and aligned dsa models answered the rate-limiter question with a full
   Redis / token-bucket design. With notes, they reply `DELEGATE: sysdes` and
   stop. sysdes abstention goes from 0.25 to 0.75.
4. **Nugen confidence frames are not calibrated.** Only aligned models emit
   them. Mean confidence on failing answers is equal to or higher than on
   passing ones (dsa 0.83 vs 0.80; sysdes 0.79 vs 0.76). The wrong dsa Q20
   answer scored 0.86. They are logged and shown, but the aggregator does not
   trust them. Lane ownership and grounding coverage decide.

## Known failures (aligned_grounded)

The systematic failure is **lane boundaries**, in both directions:

| Expert | Q | Score | What happened | Planned fix |
|---|---|---|---|---|
| sysdes | 18 (Dijkstra complexity) | 0.00 | Answered `O(E + V log V)` instead of delegating to dsa | Router classifies lanes before dispatch, so a pure-algorithm question never reaches sysdes |
| dsa | 20 (Dinic's max-flow) | 0.00 | `DELEGATE: sysdes` for an in-domain topic the notes don't cover | Router honours a delegation only if it also scores the target lane; otherwise it becomes "not covered" |
| dsa | 13 (`l = mid` loop) | 0.40 | Correct fix, but no explanation of *why* (floor rounding means `l` never advances) | Exemplar refresh with a worked failure-mode answer |
| dsa | 9 (ship capacity) | 0.33 | Right pattern, omits `max(package)..sum(packages)` bounds | Add bounds to the worked example |
| dsa | 18 (union-find) | 0.60 | Omits path compression / union by rank | Expand the union-find corpus section |
| sysdes | 11, 12, 14 | 0.50–0.60 | Right design, missing one or two named mechanisms (atomic refill, dedupe by message id, async fanout) | Exemplar refresh; procedures are the weakest category for both experts |

The first two motivate the router's design (next milestone). The rest feed the
learning loop ([`docs/LEARNING_LOOP.md`](docs/LEARNING_LOOP.md)) as corpus
gaps.

## Caveats

- **Small benchmarks.** 20 items per expert, single run at temperature 0.
  Differences under ~0.05 are noise.
- **Keyword grading** rewards the corpus terminology and can under-score a
  correct paraphrase (dsa Q13). It is deterministic and auditable, and every
  missing key is in the raw report. Paraphrase alternatives were added to the
  sysdes keys once, before its first official run.
- **Prompt tuned once on dsa.** After the first dsa run I made two
  domain-generic prompt changes: "never delegate in-domain questions" and
  "answer every part of the question". So dsa numbers are slightly
  optimistic. sysdes was written afterwards and never tuned against, making
  it the cleaner held-out check. The results agree.
- **The same corpus is used for alignment, grounding and gold answers.**
  This measures faithfulness to curated material, not general ability.
