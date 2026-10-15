# DSA Expert Corpus — Interview Algorithms & Data Structures

License: public knowledge synthesis, no copyrighted long-form, no private/organizational data.
Version: 0.1.0
Lane: dsa

## 0. Scope (in / out)

IN scope: time and space complexity analysis; the core algorithmic patterns used
in coding interviews (two-pointer, sliding window, prefix sums, binary search on
the answer, breadth-first and depth-first search, Dijkstra, dynamic programming
via memoization and tabulation, union-find); data-structure trade-offs (array,
hash map, heap, stack, queue, trie, segment tree, union-find); recognizing which
pattern a problem needs; and common implementation bugs.

Hashing and collision math (for example how long a hashed short code must be)
is in scope and owned by this lane.

OUT of scope: language-specific syntax, web frameworks, machine-learning
algorithms, competitive-math number theory, and system design. When a question
is about system design or interviewer behavior, this expert defers to the
sysdes or mock lanes rather than answering.

## 1. Core definitions

- **Time complexity** is how the number of basic operations grows as input size
  n grows, expressed with Big-O as an asymptotic upper bound. O(1) is constant,
  O(log n) logarithmic, O(n) linear, O(n log n) linearithmic, O(n^2) quadratic,
  O(2^n) exponential.
- **Space complexity** is how auxiliary memory grows with n, measured the same
  asymptotic way, excluding the input itself unless stated.
- **Amortized complexity** is the average cost per operation across a worst-case
  sequence of operations. A dynamic array append is amortized O(1) even though a
  single append that triggers a resize is O(n).
- The **two-pointer pattern** uses two indices moving over a sorted or monotonic
  input, each advancing based on a comparison. It reduces an O(n^2) brute force
  to O(n) when the predicate is monotone.
- The **sliding window pattern** maintains a contiguous range [left, right] and
  expands or contracts it to satisfy a constraint. Sliding window reduces O(n^2)
  to O(n) when the subarray constraint is monotone, so shrinking from the left is
  always safe once the window is invalid.
- **Binary search on the answer** defines a monotone predicate over the answer
  space and binary-searches for the boundary where the predicate flips. It applies
  when you can check "is a candidate answer feasible?" in less time than solving
  directly, and feasibility is monotone in the candidate.
- **Union-find (disjoint set union)** tracks a partition of elements into disjoint
  sets with near-constant operations. With path compression and union by rank its
  operations are amortized alpha(n), effectively constant.

## 2. Named patterns (numbered, with trigger conditions)

1. **Two-pointer** — trigger: sorted array, pair/triplet sums, or comparing from
   both ends. Example uses: two-sum on a sorted array, container-with-most-water,
   removing duplicates in place.
2. **Sliding window** — trigger: longest/shortest contiguous subarray or substring
   meeting a constraint (sum, distinct characters, at-most-k). Grow the window on
   the right; shrink from the left when the window violates the constraint.
3. **Prefix sums** — trigger: many range-sum queries, or counting subarrays with a
   target sum. Precompute cumulative sums so each range query is O(1); combine with
   a hash map of prefix counts for "subarrays summing to k".
4. **Binary search on the answer** — trigger: "minimum/maximum X such that a
   feasibility check passes", where feasibility is monotone. Example: minimum ship
   capacity to deliver within D days; minimum eating speed.
5. **BFS / DFS on graphs** — trigger: shortest path in an unweighted graph (BFS),
   connectivity, cycle detection, topological order (DFS or Kahn's algorithm), or
   flood fill. BFS uses a queue and finds fewest-edges paths; DFS uses recursion or
   a stack and explores deeply.
6. **Dynamic programming** — trigger: optimal substructure plus overlapping
   subproblems; count-the-ways or optimize-a-value problems. Define the state, the
   transition, and the base case; implement top-down with memoization or bottom-up
   with tabulation.

## 3. Data-structure cheat sheet (decision table)

| Need | Structure | Key operations and cost |
|---|---|---|
| Fast membership / counting | Hash map / hash set | average O(1) insert, lookup |
| Order by priority, repeated min/max | Binary heap | O(log n) push/pop, O(1) peek |
| LIFO (undo, matching brackets, DFS) | Stack | O(1) push/pop |
| FIFO (BFS, scheduling) | Queue | O(1) enqueue/dequeue |
| Prefix/word lookups | Trie | O(L) per word of length L |
| Range sum/min with updates | Segment tree / Fenwick | O(log n) query and update |
| Dynamic connectivity | Union-find | amortized alpha(n) per op |
| Index/random access | Array / dynamic array | O(1) index, amortized O(1) append |

## 4. Decision rules (symptom to pattern)

- Sorted input and you need a pair/triplet by value: reach for **two-pointer**.
- Longest/shortest contiguous run under a constraint: reach for **sliding window**.
- Many range-sum queries or "count subarrays summing to k": reach for **prefix sums**.
- "Minimum/maximum value such that something is feasible" with monotone
  feasibility: reach for **binary search on the answer**.
- Shortest path in an unweighted graph or level-order traversal: reach for **BFS**.
- Shortest path with non-negative weights: reach for **Dijkstra** (a heap-based
  greedy over BFS).
- Optimal substructure with overlapping subproblems: reach for **dynamic
  programming**.
- Grouping/merging elements and querying connectivity: reach for **union-find**.

## 5. Worked examples

### 5.1 Kadane's algorithm (maximum subarray sum)
Maintain best_ending_here = max(x, best_ending_here + x) as you scan, and track
the global best. Each element either extends the previous subarray or starts a new
one. Runs in O(n) time and O(1) space. Intuition: a prefix with negative running
sum can never help a future subarray, so discard it.

### 5.2 Two-sum on a sorted array (two-pointer)
Place left at the start and right at the end. If the pair sum is too small, move
left rightward to increase it; if too large, move right leftward to decrease it;
if equal, you found the answer. O(n) time, O(1) space, because each pointer moves
monotonically.

### 5.3 Word ladder (BFS)
Treat each word as a node and connect words that differ by one letter. BFS from the
start word gives the fewest-transformations path because BFS explores by increasing
distance. Mark words visited as you enqueue them to avoid revisiting.

### 5.4 Longest increasing subsequence via binary search
Keep a "tails" array where tails[i] is the smallest possible tail of an increasing
subsequence of length i+1. For each number, binary-search its insertion point in
tails; replace or append. The length of tails is the LIS length. O(n log n) time.

### 5.5 Short-code length and hash collisions (birthday bound)
Capacity is not collision safety. With N possible codes and n random or hashed
codes, the expected number of collisions is about n^2 / (2N) (the birthday
bound). For a URL shortener storing 36.5B URLs: 7-char base62 gives N = 62^7,
about 3.5 trillion, enough by count, but random 7-char codes would produce
about 190 million collisions. 8-char base62 (N = 62^8, about 218 trillion)
still yields about 3 million. Rule: use counter-based ids encoded in base62
(zero collisions), or if codes are hashed or random, use at least 8 characters
and check uniqueness with a retry on insert.

## 6. Failure modes (what goes wrong, how to recognize)

- **Binary search infinite loop**: writing `while l < r` with `l = mid` (instead of
  `l = mid + 1`) loops forever when the midpoint rounds down and never advances.
  Fix: advance past mid on the branch that excludes it, or use `l = mid + 1` /
  `r = mid`.
- **Off-by-one in bounds**: confusing `l <= r` (search closed interval, return when
  crossing) with `l < r` (converge to a single index). Pick one convention and keep
  the loop body consistent with it.
- **Sliding window that never shrinks**: forgetting to move left when the window is
  invalid turns it back into O(n^2). The window must shrink from the left as soon as
  the constraint breaks.
- **Wrong DP state**: choosing a state that does not capture enough history, so the
  transition is impossible or double counts. Fix by writing the recurrence in words
  first, then naming exactly the variables it depends on.
- **Using recursion without memoization**: exponential blowup on overlapping
  subproblems. Add memoization or convert to tabulation.
- **Heap misuse**: using a max-heap where a min-heap is needed (or forgetting most
  languages provide only a min-heap, so push negatives for a max-heap).

## 7. Abstention and delegation rules

- If a question is about **system design** (scaling, caching, consistency), do not
  answer from this lane; delegate to the sysdes lane.
- If a question is about **interviewer behavior, scoring, or how to run a mock**,
  delegate to the mock lane.
- If a question concerns an algorithm **not covered here** (for example, max-flow
  algorithms such as Dinic's), say the corpus does not cover it and offer the closest
  covered concept rather than inventing details.
- Never fabricate a complexity bound. If unsure, state the reasoning and the known
  bound for the closest standard algorithm.

## 8. Glossary

| Term | One-line meaning |
|---|---|
| Big-O | Asymptotic upper bound on growth |
| Amortized | Average cost per op over a worst-case sequence |
| Monotone predicate | A condition that, once true, stays true as the parameter increases |
| Memoization | Caching subproblem results in top-down recursion |
| Tabulation | Filling a DP table bottom-up |
| Topological order | Linear order of a DAG respecting edge direction |
| alpha(n) | Inverse Ackermann, effectively constant in practice |

## 9. Checklist (memorizable summary)

- Name the pattern before coding: two-pointer, sliding window, prefix sums, binary
  search on the answer, BFS/DFS, DP, union-find.
- State the complexity target out loud and justify it.
- For binary search, advance past mid to avoid infinite loops.
- For sliding window, always allow the window to shrink from the left.
- For DP, write the recurrence in words, then define the state, transition, base case.
- When out of scope, delegate (sysdes, mock) or abstain rather than inventing.
