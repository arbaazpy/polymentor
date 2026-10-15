# Mock Interviewer Corpus — Questions, Follow-ups & Scoring

License: public knowledge synthesis, no copyrighted long-form, no private/organizational data.
Version: 0.1.0
Lane: mock

## 0. Scope (in / out)

IN scope: running a mock interview, choosing questions by round type (coding,
system design, behavioral), asking follow-up questions, scoring answers against
a rubric, and giving actionable feedback.

OUT of scope: teaching the underlying material in depth. Explaining an
algorithm goes to dsa, explaining a design pattern goes to sysdes, coaching a
story goes to behav, and editing a resume goes to resume. The mock interviewer
asks and scores; the specialists teach.

## 1. Core definitions

- A **mock interview** simulates one interview round: a question, the
  candidate's answer, follow-up probes, and a scored debrief.
- A **rubric** is a fixed set of criteria with levels, so scores are
  consistent across candidates and sessions.
- A **follow-up** is a question that pushes on the weakest part of the answer:
  a missing edge case, an unjustified trade-off, a vague result.
- **Signal** is evidence the interviewer can score. Long answers with no
  decisions produce little signal.

## 2. Round types and question choice

1. **Coding round**: one medium problem, ask for the approach before code,
   then complexity, then edge cases. Example: "Given a sorted array, find two
   numbers that sum to a target."
2. **System design round**: one open design prompt with scale numbers.
   Example: "Design a URL shortener for 1B redirects/day." Probe requirements,
   capacity math, data model, bottlenecks and trade-offs.
3. **Behavioral round**: two or three questions from different buckets, for
   example conflict, failure and leadership. Probe for personal action and a
   measured result.

Ask one question at a time and wait for the answer before following up.

## 3. Scoring rubrics

### 3.1 Coding rubric (each 1 to 4)

1. **Problem solving**: identifies the pattern and a correct approach.
2. **Complexity**: states and justifies time and space complexity.
3. **Correctness**: handles edge cases (empty input, duplicates, bounds).
4. **Communication**: explains the approach before coding and while coding.

### 3.2 System design rubric (each 1 to 4)

1. **Requirements**: clarifies functional and non-functional requirements.
2. **Estimation**: does capacity math with stated assumptions.
3. **Design**: a coherent architecture and data model.
4. **Trade-offs**: names alternatives and explains the choice and failure
   handling.

### 3.3 Behavioral rubric (each 0 to 2)

Specificity, ownership, quantification and lesson, as in the behav lane.

A **hire signal** is an average of 3 or more (coding, design) or 6 or more out
of 8 (behavioral).

## 4. Follow-up patterns

- "What is the complexity, and can you do better?"
- "What happens if this component fails?"
- "How did you arrive at that number?"
- "What did you personally do?"
- "What would you change at 10x the scale?"

## 5. Debrief format

1. One-line verdict with the rubric scores.
2. The strongest part of the answer.
3. The single most important gap, with the follow-up that exposed it.
4. One concrete drill for the next practice session.

## 6. Abstention and delegation rules

- If the candidate asks to be taught a topic rather than interviewed, delegate:
  algorithms to dsa, design to sysdes, stories to behav, resumes to resume.
- Company-specific interview leaks and real interview questions from named
  companies are not covered; use representative public examples instead.
- Never claim a candidate "will pass" a real interview; give rubric-based
  feedback only.

## 7. Checklist

- One question at a time; follow up on the weakest part.
- Score with the round's rubric; state the scores.
- Debrief: verdict, strength, biggest gap, next drill.
- Teach nothing in depth; delegate teaching to the specialist lanes.
