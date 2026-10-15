# Resume Expert Corpus — Bullets, Fit & Red Flags

License: public knowledge synthesis, no copyrighted long-form, no private/organizational data.
Version: 0.1.0
Lane: resume

## 0. Scope (in / out)

IN scope: resume bullet impact, seniority signals, job-description (JD) fit,
resume red flags, structure and formatting, and honesty guardrails.

OUT of scope: cover letters, cold-outreach messages, salary negotiation, and
visa questions. Technical interview content goes to the dsa or sysdes lanes;
behavioral storytelling goes to the behav lane.

## 1. Core definitions

- A **strong bullet** = action verb + specific artifact + measurable impact.
  Example: "Cut checkout p95 latency from 900 ms to 250 ms by adding a
  read-through cache to the pricing service." The verb is "cut", the artifact
  is "the pricing service cache", and the impact is the latency change.
- A **weak bullet** describes duties instead of results: "Responsible for the
  payments service" or "Worked on backend APIs". It has no artifact detail and
  no impact.
- **JD fit** = overlap with the must-have skills in the job description plus
  evidence of impact at the claimed seniority. Keywords alone are not fit; each
  must-have skill should be backed by at least one bullet that shows it used.
- **Seniority signals** are scope (team, org, company), ambiguity handled,
  people influenced or mentored, and decisions owned, not years of experience.
- A **red flag** is anything that lowers trust: adjectives without artifacts
  ("passionate", "rockstar", "ninja") with no backing bullet, unexplained date
  gaps or overlaps, buzzword lists with no evidence, or metrics that cannot be
  true.

## 2. The bullet rewrite procedure

1. Find the artifact: which system, feature, or process did you build or
   change?
2. Pick a strong past-tense action verb: built, cut, designed, migrated, led,
   automated, reduced.
3. Add the measurable impact: latency, cost, revenue, error rate, time saved,
   users affected. If no exact number exists, use a clear before-and-after.
4. Add scope when it signals seniority: "across 4 teams", "for 2M users".
5. Keep it to one or two lines; put the impact first if it is the strongest
   part.

Example rewrite: "Worked on the payments service" becomes "Migrated the
payments service to idempotent retries, cutting duplicate charges from 0.4% to
0.01% of transactions."

## 3. JD-fit check

1. List the JD's must-have skills and nice-to-have skills separately.
2. For each must-have, find the bullet that proves it; if none exists, either
   add a truthful bullet or accept the gap.
3. Mirror the JD's terminology where it is accurate (for example "event-driven"
   if you built Kafka consumers), never where it is not.
4. Put the most relevant role and bullets first.
5. Score fit as the share of must-haves backed by evidence.

## 4. Red flags and fixes

- Adjectives without artifacts: replace "passionate backend engineer" with a
  bullet that shows the work.
- Duty bullets: rewrite each with verb + artifact + impact.
- Keyword soup: a skills list of 40 technologies reads as unfocused; keep the
  ones you can discuss in depth.
- Unbelievable metrics ("improved performance by 1000%") invite skepticism;
  use concrete before-and-after numbers.
- Long paragraphs: recruiters skim; use bullets of one or two lines.
- Inconsistent dates or titles: fix them; they are easy to verify.

## 5. Honesty guardrails

Never invent metrics, titles, or skills. If an exact number is unknown, use an
honest approximation the candidate can defend in an interview ("about 30%"),
or a qualitative before-and-after. Every bullet should survive the question
"tell me more about that".

## 6. Abstention and delegation rules

- Cover letters, outreach, salary and visa questions are not covered here; say
  so.
- System design questions go to sysdes; algorithm questions go to dsa;
  behavioral story coaching goes to behav; running a mock interview goes to
  mock.
- Do not rewrite a bullet with facts the candidate did not provide; ask for the
  artifact and the impact instead.

## 7. Checklist

- Every bullet: action verb + specific artifact + measurable impact.
- Every JD must-have backed by a bullet.
- Seniority shown through scope and decisions, not adjectives.
- No invented numbers; every bullet defensible in an interview.
