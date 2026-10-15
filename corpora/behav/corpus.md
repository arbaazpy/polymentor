# Behavioral Interview Expert Corpus — Stories, Signals & Rubrics

License: public knowledge synthesis, no copyrighted long-form, no private/organizational data.
Version: 0.1.0
Lane: behav

## 0. Scope (in / out)

IN scope: the STAR structure; the eight situational buckets interviewers draw
from (conflict, failure, leadership, ambiguity, influence without authority,
prioritization, feedback, ownership); the four-criterion story rubric
(specificity, ownership, quantification, lesson); red flags and green flags;
interviewer probing patterns; scoping and stakeholder framing for technical
projects; and how a candidate prepares a story bank.

OUT of scope: salary negotiation, offer evaluation, immigration or legal
questions, and company-specific value lists quoted verbatim. Technical content
is also out of scope: system design questions go to the sysdes lane, algorithm
and complexity questions go to the dsa lane, and resume bullet rewrites go to
the resume lane.

## 1. Core definitions

- **STAR** stands for Situation, Task, Action, Result. Situation and Task set
  context in one or two sentences each. Action and Result carry the signal:
  the interviewer is scoring what the candidate personally did and what changed
  because of it. A STAR answer should spend most of its time on Action and
  Result, not on background.
- A **behavioral question** asks about past behavior ("Tell me about a time
  you...") on the premise that past behavior predicts future behavior. A
  **hypothetical question** ("What would you do if...") is weaker evidence
  because it tests intentions, not actions.
- A **good behavioral story** is specific, first-person, and quantified where
  possible. Specific means one real event with names of roles, systems and
  dates, not a summary of habits. First-person means "I decided", "I wrote",
  "I proposed", not only "we". Quantified means the result has a number:
  latency, revenue, time saved, incidents reduced, people affected.
- **Ownership** is the candidate taking responsibility for the outcome,
  including the parts that went wrong, rather than attributing results to
  luck or blaming the team.
- A **red flag** is a signal that lowers the score: blaming teammates or
  managers, no clear personal action, no result, or a story that contradicts
  itself under probing. A **green flag** raises it: the candidate owns the
  outcome and names the lesson, and shows changed behavior afterwards.
- A **story bank** is a prepared set of six to ten stories, each tagged with
  the buckets it can answer, so one strong story can serve several questions.
- **Influence without authority** is getting people who do not report to you
  to change direction, using data, prototypes, and shared goals rather than
  rank.

## 2. Named frameworks (numbered lists)

### 2.1 The eight situational buckets (with trigger questions)

1. **Conflict**: "Tell me about a disagreement with a teammate or manager."
2. **Failure**: "Tell me about a time something you owned went wrong."
3. **Leadership**: "Tell me about a time you led a project or a team."
4. **Ambiguity**: "Tell me about a time requirements were unclear."
5. **Influence without authority**: "Tell me about convincing people who
   didn't report to you."
6. **Prioritization**: "Tell me about a time you had too much to do."
7. **Feedback**: "Tell me about feedback you received, or difficult feedback
   you gave."
8. **Ownership**: "Tell me about a time you went beyond your assigned scope."

### 2.2 The four-criterion story rubric

1. **Specificity**: one concrete event with real details, not a general
   description of how you usually work.
2. **Ownership**: first-person actions; the candidate's own decisions are
   clear and they own the outcome, including mistakes.
3. **Quantification**: the result is measured with a number or a clear
   before-and-after.
4. **Lesson**: the candidate names what they learned and what they now do
   differently.

Each criterion is scored 0 (absent), 1 (partial) or 2 (clear). A strong story
scores 7 or 8, a mid story 4 to 6, and a weak story 3 or below.

### 2.3 Interviewer probing patterns

1. **"What did you do?"** separates personal action from team action when a
   candidate says "we" throughout.
2. **"What would you do differently?"** tests the lesson and self-awareness.
3. **"How did you measure that?"** tests quantification and honesty.
4. **"What did the other person think?"** tests empathy in conflict stories.
5. **"What happened next?"** tests whether the result is real and lasting.

## 3. Decision rules (prefer X when ...)

| Situation | Prefer | Why |
|---|---|---|
| Asked for a failure | A real failure you owned, with the lesson | Fake failures ("I work too hard") are red flags |
| Conflict question | A disagreement about approach, resolved with data | Shows judgment without blaming people |
| Team project story | Your specific decisions inside the team effort | Interviewers score your actions, not the team's |
| No hard number available | A clear before-and-after or a proxy metric | Quantification can be relative ("from weekly to daily releases") |
| Story runs long | Cut Situation and Task to two sentences | Action and Result carry the signal |
| Unsure which bucket a question targets | Ask a brief clarifying question | Choosing the right story beats rambling |

- **Strong vs mid story**: a strong story is specific, first-person,
  quantified, and names a lesson (rubric 7 to 8). A mid story usually has a
  clear action but a vague result or no lesson (rubric 4 to 6).
- **Behavioral vs hypothetical**: when asked a hypothetical, answer briefly and
  then anchor it in a real past example; past behavior is stronger evidence.

## 4. Worked examples (annotated)

### 4.1 Strong: conflict about an approach

Situation: two engineers disagreed on whether to rewrite a slow reporting
service or optimize it. Task: I owned the decision as the tech lead. Action: I
proposed a one-week spike, profiled the service, and found 80% of the time was
in three queries; I shared the profile with both engineers and we agreed to
optimize first. Result: report time dropped from 40 seconds to 4 seconds, and
the rewrite was deferred, saving about a quarter of engineering time. Lesson:
I now settle design disagreements with a time-boxed experiment instead of a
debate. Rubric: specificity 2, ownership 2, quantification 2, lesson 2 = 8.

### 4.2 Weak: vague team story

"We had a bug in production and we fixed it and everyone was happy." There is
no specific event, no first-person action, no number, and no lesson. Rubric:
specificity 0, ownership 0, quantification 0, lesson 0 = 0. The interviewer
should probe with "What did you do?" and "How did you measure that?"

### 4.3 Mid: leadership without a result

The candidate describes organizing a migration, assigning tasks and running
standups (clear personal action), but ends with "it went well" and no number
or lesson. Rubric: specificity 2, ownership 2, quantification 0, lesson 0 = 4.
The fix is to add a measured result (for example, cutover with zero downtime,
two weeks ahead of plan) and a lesson.

### 4.4 Mid: failure with blame

The candidate describes a missed deadline, then attributes it to "the QA team
being slow". Rubric: specificity 2, ownership 0, quantification 1, lesson 1 =
4. Blaming the team is a red flag; the stronger version owns the planning
mistake and names the change made afterwards.

## 5. Failure modes (what goes wrong, how to recognize)

- **Vague story**: a summary of habits ("I always communicate well") instead of
  one event. Fix: pick a single incident with dates, roles and systems.
- **"We" only**: the candidate uses "we" throughout, so the interviewer cannot
  tell what they personally did. Probe: "What did you do?" Fix: rewrite the
  Action in the first person.
- **No result**: the story ends at the action. Fix: add a measured outcome or a
  clear before-and-after.
- **Blaming others**: the failure is attributed to teammates or managers. This
  is a red flag. Fix: own your part and name the lesson.
- **Over-rehearsed**: the answer sounds memorized and falls apart under
  follow-up questions. Fix: know the facts of the story well, not a script.
- **Too much setup**: two minutes of Situation and Task. Fix: keep context to
  two sentences; Action and Result carry the signal.
- **Fake failure**: "My weakness is that I work too hard." Fix: choose a real
  mistake with real consequences and a lesson.

## 6. Abstention and delegation rules

- If a question is about **system design** (architecture, scaling, caching),
  delegate to the sysdes lane.
- If a question is about **algorithms, data structures, or complexity**,
  delegate to the dsa lane.
- If a question is about **rewriting resume bullets or job-description fit**,
  delegate to the resume lane.
- If a question is about something **not covered here** (for example salary
  negotiation, offer evaluation, or visa questions), say the corpus does not
  cover it rather than inventing advice.
- Never invent a story on the candidate's behalf; coach the structure and ask
  for their real details.

## 7. Glossary

| Term | One-line meaning |
|---|---|
| STAR | Situation, Task, Action, Result |
| Signal | Evidence the interviewer can score, mostly in Action and Result |
| Story bank | Six to ten prepared stories tagged by bucket |
| Ownership | Taking responsibility for outcomes, including mistakes |
| Red flag | Blaming others, no personal action, no result |
| Green flag | Owns the outcome and names the lesson |
| Influence without authority | Changing direction without managerial power |
| Probe | Follow-up question that tests a story's depth |

## 8. Checklist (memorizable summary)

- Use STAR; Action and Result carry the signal.
- Make it specific, first-person, and quantified where possible.
- Score with the rubric: specificity, ownership, quantification, lesson.
- Prepare a story bank covering the eight buckets.
- Own failures and name the lesson; never blame the team.
- Delegate technical questions (sysdes, dsa) and resume edits (resume).
