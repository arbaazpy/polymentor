# Evaluation

How much does each layer of a PolyMentor expert actually contribute? This file
answers that with measured numbers for the DSA expert, not intuition.

Raw report (every answer, score, missing key, confidence, latency):
[`evals/dsa/20261015T133223.json`](evals/dsa/20261015T133223.json).
Reproduce with `uv run python manage.py run_benchmark dsa`.

## Setup

| | |
|---|---|
| Benchmark | [`benchmarks/dsa.json`](benchmarks/dsa.json): 20 gold Q&A (definition, distinction, procedure, failure-mode, abstention) |
| Grader | [`benchmarks/dsa.keys.json`](benchmarks/dsa.keys.json): deterministic keyword groups; forbidden phrases zero an abstention item |
| Base model | `meta-llama/Llama-3.2-3B-Instruct` |
| Aligned model | `model_01m4zv707z9qzt7z` (Nugen domain alignment of the base on `corpora/dsa/`) |
| Grounding | BM25 over corpus sections, top 3 + pinned scope/abstention rules, injected as reference notes |
| Decoding | temperature 0, max 400 tokens, same lane system prompt in every mode |

The four modes differ only in the model and whether notes are injected, so each
row isolates one layer.

> **Retrieval update.** After this run, long sections are chunked (≤900 chars)
> and metadata headers are dropped. A re-check of `aligned_grounded` scored
> 0.81 overall with a 0.75 pass rate, within noise of the row below. The
> full table is refreshed with the sysdes run.

## Results

| mode | overall | pass rate (≥0.75) | abstention | definition | distinction | failure | procedure | Nugen conf (pass) | Nugen conf (fail) |
|---|---|---|---|---|---|---|---|---|---|
| `base` | 0.49 | 0.40 | 0.00 | 0.48 | 0.53 | 0.66 | 0.55 | - | - |
| `base_grounded` | 0.79 | 0.70 | 0.50 | 0.85 | 0.94 | 0.84 | 0.67 | - | - |
| `aligned` | 0.51 | 0.35 | 0.00 | 0.47 | 0.55 | 0.72 | 0.57 | 0.81 | 0.79 |
| **`aligned_grounded`** | **0.79** | **0.80** | 0.50 | 0.86 | 0.89 | 0.72 | 0.81 | 0.82 | 0.81 |

## What this says

1. **Grounding is the largest lever (+0.28 to +0.30 overall).** Retrieved notes
   turn generic textbook answers into answers that use the corpus's precise
   framing (monotone predicates, shrink-from-left, lane delegation).
2. **Alignment alone is roughly neutral on this benchmark (+0.02).** A 3B
   adapter trained on ~2k words of corpus does not reliably recall specific
   phrasing. Combined with grounding it gives the best pass rate (0.80 vs
   0.70): the aligned model follows the notes and the answer format more
   consistently. That is why production uses `aligned_grounded`.
3. **Delegation works once rules are in context.** Without notes, both base
   and aligned models answered the rate-limiter question (Q19) with a full
   Redis / token-bucket design, despite the delegation rule in the system
   prompt. With notes, both reply `DELEGATE: sysdes` and stop.
4. **Nugen confidence frames are only weakly calibrated.** Only aligned models
   emit them. Mean confidence on passing answers is 0.82 against 0.81 on failing
   ones, and the wrong Q20 answer scored 0.84. They are logged and shown in
   the UI, but the aggregator does not trust them alone. They are one signal
   next to lane ownership and grounding coverage.

## Known failures (aligned_grounded)

| Q | Score | What happened | Planned fix |
|---|---|---|---|
| 20 (Dinic's max-flow) | 0.00 | Emitted `DELEGATE: sysdes` for an in-domain topic the notes don't cover, despite an explicit rule | Router-side check: a delegation is only honoured if the router also scores the target lane highly; otherwise it becomes "not covered" |
| 13 (`l = mid` loop) | 0.40 | Correct fix (`l = mid + 1`) but doesn't explain *why* (floor rounding means `l` never advances) | Exemplar refresh in the learning loop with a worked failure-mode answer |
| 9 (ship capacity) | 0.50 | Right pattern, but omits the `max(package)..sum(packages)` search bounds | Same; add bounds to the retrieved worked example |
| 18 (union-find) | 0.60 | Omits path compression / union by rank | Corpus section on union-find is thin; expand corpus, re-align |

These feed directly into the learning loop
([`docs/LEARNING_LOOP.md`](docs/LEARNING_LOOP.md)): each one is either a
corpus gap (re-align) or a routing gap (router re-align).

## Caveats

- **Small benchmark.** 20 items, single run at temperature 0. Differences under
  ~0.05 are noise.
- **Keyword grading** rewards using the corpus terminology. It can under-score a
  correct paraphrase, as on Q13. It is deterministic and auditable, and every
  missing key is recorded in the raw report.
- **Prompt tuned once on this set.** After a first run I made two
  domain-generic prompt changes: "never delegate in-domain questions" and
  "answer every part of the question". Both were motivated by benchmark
  failures, so the numbers are optimistic for unseen questions. A held-out
  set, built from mined user prompts, is part of the learning loop's gate.
- **The same corpus is used for alignment, grounding and the gold answers**,
  so this measures faithfulness to the curated material, not general DSA
  ability.
