# PolyMentor — The "Wow" Interaction

> **Design document, written before the build.** What shipped is described in the
> [README](../README.md) and measured in [EVALUATION.md](../EVALUATION.md). Main changes
> during the build: turns run synchronously in gunicorn thread workers (no Celery worker
> or Redis); the UI is Tailwind + vanilla JS streaming (no HTMX); experts' decisions are
> extracted from prose because 3B models ignored claim tags; re-alignment is done on the
> Nugen dashboard and promoted through the `promote_expert` eval gate; the router is
> keyword + corpus BM25 with an LLM fallback rather than a separately aligned model.

> A reviewer at Nugen will open the demo URL, click two things, and form an opinion in about 90 seconds. This doc defines the **one interaction** that has to carry the whole thesis — multi-model, aligned, aggregated, improving — and makes the architecture *visible* instead of merely present.

---

## 1. The thesis

The brief asks for a **router that delegates to a fleet of experts and brings their expertise together.** Most candidates will ship a chatbot that silently calls one model. We need the opposite: an interaction where you can **see the fleet working, see them disagree, and see one aligned expert win a sub-claim because its domain owns it.**

The wow moment, in one line:

> **"Design a URL shortener for 1B redirects/day. I have 2 weeks to ship."**
>
> → router decomposes into sub-questions, fans out to `expert.sysdes` (architecture), `expert.dsa` (hash function + capacity math), `expert.behav` (scoping + stakeholder framing), and `expert.mock` (grading rubric). Aggregator reconciles a **genuine disagreement** between `sysdes` and `dsa` on hash length vs collision probability, and the UI shows:
>
> - Who said what
> - Which expert "owned" each sub-claim
> - Where they disagreed and how the aggregator resolved it
> - A confidence score per section
> - A "see the raw expert outputs" drawer with the two conflicting answers side-by-side

That single screen demonstrates: routing, decomposition, parallel fan-out, lane-specific alignment, aggregator reconciliation, and transparency. In 90 seconds.

---

## 2. Why disagreement, specifically

Fluent agreement is cheap. Any orchestration of LLMs can produce a *coherent-looking* joint answer. What's hard — and what Nugen's product thesis is actually about — is **letting a domain-aligned specialist win a claim because the generic model is wrong**. Showing that explicitly:

- Proves the experts are actually different models with different priors (not one model with 5 system prompts).
- Proves the aggregator is not just concatenating.
- Proves alignment did something measurable.
- Mirrors how a real multi-expert workflow handles contradictions in enterprise settings (which is Nugen's commercial pitch).

If every expert agrees, we show a lower-signal "consensus" badge. If they disagree, we show the receipt.

---

## 3. The reconciliation rubric (how the aggregator decides)

The aggregator is a deterministic, auditable function — not another LLM call. Keeps it fast, free, and inspectable.

### 3.1 Inputs
Each expert returns a normalized `ExpertResponse`:
```json
{
  "expert_key": "sysdes",
  "expert_version": "v0.2.0",
  "sub_claims": [
    { "id": "arch.load_balancer", "text": "Use L7 LB with consistent hashing on short code",
      "confidence": 0.86, "citations": ["corpus:sysdes#2.3"] },
    { "id": "hash.length", "text": "7-char base62 covers 3.5T keys; safe for 1B/day for ~10 yrs",
      "confidence": 0.74, "citations": ["corpus:sysdes#2.5"] }
  ],
  "abstain": [],
  "caveats": ["assumes 10:1 cache hit ratio"]
}
```

Sub-claim IDs are a shared, dotted taxonomy per domain (e.g. `arch.*`, `storage.*`, `hash.*`, `rubric.*`). Experts emit claims against this taxonomy via a lightweight prompt contract.

### 3.2 Reconciliation rules (in order)

1. **Lane ownership.** Each sub-claim namespace has a *primary owner* lane (e.g. `arch.*` → sysdes, `hash.*` → dsa, `rubric.*` → mock). Primary owner's claim wins ties.
2. **Abstention is loud.** If the primary owner abstained on its own namespace, the aggregator surfaces the abstention — does NOT silently use a secondary expert's claim.
3. **Confidence threshold.** Non-owner claim can override owner only if `non_owner.confidence − owner.confidence ≥ 0.25` AND owner's confidence is below 0.5. (Rare, but keeps us honest if an aligned owner is weak.)
4. **Contradiction detection.** Two claims conflict iff same `id` and (a) opposite polarity (e.g. one says "use X", other says "do not use X") detected by a tiny deny-pair dictionary per lane, or (b) numerical disagreement beyond relative 20%.
5. **Resolution display.** For every resolved contradiction, the UI shows: both claims, both confidences, the owner, and the rule applied.

### 3.3 Final composition
Final answer = ordered sections by sub-claim namespace, each tagged with `source: expert.X v0.Y.Z`, confidence color-coded (green ≥ 0.8, amber 0.5–0.8, red < 0.5 or abstained).

---

## 4. The screen (what the reviewer sees)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PolyMentor                                              [arbaazpy / LinkedIn]
├──────────────────────────────────────────────────────────────────────────┤
│ Ask                                                                       │
│ > Design a URL shortener for 1B redirects/day. I have 2 weeks to ship.    │
│                                                                           │
│ ┌─ Router ────────────────────────────────────────────────────────────┐  │
│ │ Strategy: parallel  (confidence 0.93)                               │  │
│ │ → expert.sysdes · expert.dsa · expert.behav · expert.mock            │  │
│ │ [why these experts?]                                                │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ Architecture (sysdes v0.2.0, conf 0.86) ───────────────────────────┐  │
│ │ L7 load balancer → stateless app tier → KV store (redis-backed) ... │  │
│ │ 2 redis clusters, consistent hashing, 10:1 cache ratio ...          │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ Hash design (dsa v0.1.0, conf 0.81) ───────────────────────────────┐  │
│ │ ⚠ Reconciled: sysdes said 7 chars; dsa said 8 chars.                │  │
│ │ Resolution: dsa owns hash.* and asserts collision probability at    │  │
│ │ 1B/day crosses 1e-6 inside 3 years with 7 chars; recommends 8.      │  │
│ │ [see both raw outputs]                                              │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ Scoping for a 2-week ship (behav v0.1.0, conf 0.78) ───────────────┐  │
│ │ Carve shipping path: single region, no custom analytics, re-use ... │  │
│ │ Stakeholder script: ...                                             │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ ┌─ Interviewer rubric (mock v0.1.0, conf 0.82) ───────────────────────┐  │
│ │ If asked in a real round, graders care about: capacity math,        │  │
│ │ consistent hashing rationale, failure modes ...                     │  │
│ └──────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│ 👍  👎  [regenerate]  [see routing trace]  [see raw expert calls]         │
└──────────────────────────────────────────────────────────────────────────┘
```

Four details that matter:

1. **Router strategy + confidence banner** — reviewer *sees* decomposition happened.
2. **Reconciliation callout** — the ⚠ block showing a real disagreement being resolved by lane ownership is the money shot.
3. **"See raw expert calls" drawer** — reviewer can click into the untouched outputs of each expert, including the losing claim. This is the audit trail.
4. **Per-section source + confidence** — every claim is attributed to a versioned expert.

---

## 5. Secondary wow candidates (in case one fails)

Only one of these needs to work on demo day. If the sysdes-vs-dsa disagreement doesn't fire reliably, we have fallbacks:

### 5.1 Resume + behavioral cross-check
Prompt: *"Here's my resume (paste). I'm interviewing at Nugen as a senior backend engineer. Prep me."*
- `expert.resume` critiques bullets, flags missing metrics
- `expert.behav` generates STAR stories *from* the resume bullets
- Aggregator cross-checks: *"Resume claims '60% latency reduction' but no behavioral story exists for it — probable interview risk."*
- Shows how experts can *inform each other*, not just coexist.

### 5.2 Mock interview mid-turn grading
During a mock, candidate answers "design a rate limiter." Behind the scenes:
- `expert.mock` is the interviewer persona
- `expert.sysdes` silently grades the sub-claims
- `expert.behav` grades communication quality
- `expert.mock` uses the gaps to pick the next probing question
- UI shows a live rubric fill in and the "mock" expert visibly steering using the other experts' outputs.

### 5.3 Live re-align delta (admin only)
Admin page: *"Flip to v0.2 and ask the same question again."* Same prompt returns a materially better answer, and the diff highlights the new corpus sentences that drove the improvement. This is the "improves over time" claim made visible.

**Prioritization:** 4 (primary) → 5.2 (mock cross-grading) → 5.1 (resume+behav) → 5.3 (admin). Build 4 and 5.2 both; 5.1 and 5.3 are stretch.

---

## 6. Engineering requirements this imposes

The wow moment forces specific architecture choices. Important to list them so we don't accidentally cut them during the 96h:

| Requirement | Where it lives |
|---|---|
| Experts emit **structured sub-claims**, not free text | Prompt contract in `apps/experts/prompts.py`; parser in `services.py` |
| Shared **sub-claim ID taxonomy** per domain | `apps/experts/taxonomy.py` (constants) |
| Aggregator exposes **reconciliation events** on the response | `AggregatedAnswer.reconciliations: list[Reconciliation]` |
| UI shows reconciliation callouts, raw-expert drawer, confidence colors | `templates/_answer_blocks.html` + HTMX swaps |
| Routing trace is **always persisted** on `Turn.router_decision` | already in data model |
| Per-expert `confidence` returned by model (prompted to self-report) | prompt contract; we validate 0..1 |

Risk: self-reported confidence from an LLM is unreliable. Mitigation: we **cap** the model's self-reported value with a backing rule — e.g. if the model claims 0.95 but the answer contains an abstention phrase, we floor it. Documented transparently.

---

## 7. Failure modes of the wow moment

| Failure | Likelihood | Mitigation |
|---|---|---|
| Experts don't actually disagree on the showcase prompt | Medium | Hand-craft 3 showcase prompts that reliably produce reconciliation; publish them in the UI as "Try one of these" |
| Model doesn't follow structured sub-claim output | Medium-high | Robust parser with regex + JSON schema repair; fallback to free-text block tagged `unstructured` |
| Reconciliation triggers on noise (false positive) | Low-medium | Deny-pair dictionary curated manually; conservative numerical threshold |
| Reviewer thinks the disagreement is scripted / fake | Low | Raw-expert drawer shows real responses; the versioned model IDs + confidence are inspectable |
| Latency balloons from fan-out | Medium | Parallel SSE multiplexing; cache per `(lane, normalized_prompt)` |

---

## 8. The "Try these" prompt library (public, on the Ask page)

A small, hand-curated panel. Reviewer doesn't have to think of a good query.

1. **"Design a URL shortener for 1B/day. I have 2 weeks to ship."** → showcases reconciliation (primary wow)
2. **"Prep me for a Google backend SDE-2 loop next week"** → showcases parallel multi-expert
3. **"Here's a weak STAR story: '[example]'. Make it stronger."** → showcases single-expert depth
4. **"Grade this answer to 'design a rate limiter': [example]"** → showcases cross-expert grading
5. **"I confuse `l<r` vs `l<=r` in binary search."** → showcases focused single-expert and gold-phrase lock-in

Each has a "This showcases: …" tooltip linking to the relevant architecture section. Reviewer-friendly.

---

## 9. Decisions (locked)

1. ✅ **Primary showcase prompt:** URL shortener (sysdes vs dsa disagreement on hash length). Pinned by default on Ask page.
2. ✅ **Sub-claim output format:** tagged markdown — `[[claim id="hash.length" conf="0.74"]]...[[/claim]]`. Robust to small-model drift.
3. ✅ **Confidence source:** compute post-hoc from heuristics (hedge-word density, abstention phrases); self-reported kept as advisory only.
4. ✅ **Raw-expert drawer:** always public, one click away. Auditability is the thesis.
5. ✅ **"Try these" panel:** 5 fixed hand-curated prompts at launch; swap for top-rated past turns after real feedback accumulates (v1.1).
6. ✅ **Fallback wow:** build mock cross-grading (5.2) in parallel with the primary — reuses sub-claim infrastructure for free.