# System Design Expert Corpus — Interview Architecture & Distributed Systems

License: public knowledge synthesis, no copyrighted long-form, no private/organizational data.
Version: 0.1.0
Lane: sysdes

## 0. Scope (in / out)

IN scope: scalability axes (vertical and horizontal scaling); the CAP theorem and
PACELC; caching tiers and cache strategies (cache-aside, write-through,
write-back) and invalidation; the consistency ladder (linearizability, bounded
staleness, session guarantees such as read-your-writes, eventual consistency);
partitioning (hash, range, consistent hashing) and replication (leader-follower,
multi-leader, quorums); queueing patterns (work queue, pub/sub, transactional
outbox, saga); idempotency; back-pressure; rate limiting; API design and
pagination; capacity estimation; and the common interview building blocks: URL
shortener, newsfeed fanout, rate limiter, and chat delivery.

OUT of scope: vendor-specific product tutorials and pricing, consensus-algorithm
internals and proofs (Raft, Paxos), CRDT merge semantics, algorithm complexity
proofs, and behavioral interviewing. When a question is about algorithm
complexity, data-structure internals, or hash collision math, this expert
delegates to the dsa lane. When it is about behavioral stories, it delegates to
the behav lane.

## 1. Core definitions

- **Vertical scaling** (scale up) means giving one machine more CPU, memory, or
  disk. It is simple and keeps strong consistency, but it has a hard ceiling and
  a single point of failure.
- **Horizontal scaling** (scale out) means adding more machines and spreading
  load across them. It removes the ceiling but requires stateless services,
  partitioning, and replication.
- The **CAP theorem** says that during a network partition a distributed store
  must choose between consistency and availability. **PACELC** extends it: if
  there is a Partition choose Availability or Consistency, Else choose Latency or
  Consistency.
- **Consistent hashing** places nodes and keys on a hash ring; each key belongs
  to the next node clockwise. Consistent hashing minimizes key reshuffling when
  nodes join or leave: only about 1/N of keys move instead of nearly all of them.
  Virtual nodes smooth out uneven load.
- **Linearizability** (strong consistency) means every read sees the most recent
  completed write, as if there were a single copy of the data.
- **Read-your-writes** is a session-level guarantee weaker than linearizability:
  a client always sees its own writes, but other clients may still see stale
  data. It is usually implemented by routing a user's reads to the leader, or to
  a replica that has caught up to the user's last write, for a short window.
- **Eventual consistency** means replicas converge if writes stop, with no bound
  on how stale a read can be in the meantime.
- An **idempotency key** is a client-generated unique id sent with a write.
  Idempotency keys collapse retried writes to a single effect: the server stores
  the key with the first result and returns that same result for any retry.
- **Back-pressure** is a flow-control signal that propagates slowness from
  downstream to upstream. Back-pressure propagates slowness upstream to prevent
  queue blowup. Mechanisms: bounded queues with blocking or rejecting producers,
  demand signals (reactive streams, credit-based flow control), and HTTP 429 or
  503 with Retry-After.
- **Rate limiting** caps how many requests a client may make per time window.
  The **token bucket** algorithm refills tokens at a fixed rate up to a burst
  capacity; each request spends one token, and requests without a token are
  rejected with 429.
- **Fanout-on-write** (push) writes a new post into every follower's feed when it
  is created. **Fanout-on-read** (pull) assembles a feed at read time from the
  accounts a user follows.

## 2. Named frameworks (numbered lists)

### 2.1 The 8-step design procedure

1. **Clarify requirements**: functional requirements and non-functional
   requirements (scale, latency, availability, consistency).
2. **Capacity estimation**: requests per second, read:write ratio, storage
   growth, bandwidth, cache size.
3. **API design**: endpoints, request and response shapes, pagination,
   idempotency keys for writes.
4. **Data model**: entities, keys, access patterns, choice of SQL or NoSQL.
5. **High-level architecture**: clients, load balancer, stateless services,
   cache, database, queues.
6. **Deep dives**: the hardest components, such as key generation, hot keys, or
   fanout.
7. **Scaling and reliability**: partitioning, replication, caching, rate
   limiting, back-pressure.
8. **Trade-offs and failure handling**: what breaks first, how it degrades,
   and what you would change at 10x scale.

### 2.2 The consistency ladder (strongest to weakest)

1. Linearizability (strong consistency)
2. Bounded staleness
3. Session guarantees (read-your-writes, monotonic reads)
4. Eventual consistency

### 2.3 Caching tiers

1. Client cache (browser, mobile app)
2. CDN / edge cache
3. Application cache (Redis or Memcached in front of the database)
4. Database buffer cache

### 2.4 Queueing patterns

1. **Work queue**: each message is processed by exactly one consumer from a
   competing pool; used for background jobs.
2. **Pub/sub**: each message is delivered to every subscriber group; used to
   broadcast events to independent services.
3. **Transactional outbox**: write the business row and an outbox row in the
   same database transaction; a relay publishes outbox rows to the queue. It
   removes the dual-write problem.
4. **Saga**: a long-running transaction split into local steps, each with a
   compensating action that undoes it if a later step fails.

## 3. Decision rules (prefer X when ...)

| Situation | Prefer | Why |
|---|---|---|
| Read-heavy, tolerates slight staleness | Cache-aside with TTL | Cache only what is read; simple invalidation |
| Reads must see latest write immediately | Write-through | Cache updated in the same write path |
| Write-heavy, can tolerate loss window | Write-back | Batches writes; risk of loss on cache failure |
| Most users have few followers | Fanout-on-write | Cheap reads; precomputed feeds |
| Celebrity accounts with millions of followers | Fanout-on-read for them (hybrid) | Avoids millions of writes per post |
| Range scans by time or id | Range partitioning | Adjacent keys co-located |
| Even spread, point lookups | Hash partitioning / consistent hashing | Avoids hot ranges |
| Strong invariants (money, inventory) | Leader-based writes, linearizable reads | Correctness over latency |
| Spiky producer, slower consumer | Queue + back-pressure | Absorbs bursts without blowup |
| Retries possible on writes | Idempotency keys | Collapse retried writes to a single effect |

- **Cache-aside** (lazy loading): the application reads the cache, on a miss
  reads the database and populates the cache. **Write-through**: every write
  goes to the cache and the database synchronously, so the cache is never stale
  but writes are slower.
- **Work queue vs pub/sub**: use a work queue when a task should run once; use
  pub/sub when several independent consumers must each see every event.

## 4. Worked designs

### 4.1 URL shortener (1B redirects/day, 100:1 read:write)

1. Requirements: create a short link, redirect fast (p99 under 50 ms), links
   live for years, high availability for redirects.
2. Capacity estimation: 1B redirects/day is about 11,600 reads per second
   average and roughly 35,000 at peak. At 100:1, writes are 10M new URLs/day,
   about 116 per second. Over 10 years that is about 36.5B URLs; at ~500 bytes
   per row that is about 18 TB.
3. API: `POST /urls {long_url}` with an idempotency key returns `short_code`;
   `GET /{short_code}` returns a 301/302 redirect.
4. Data model: `short_code -> long_url, created_at, owner`; a key-value store
   partitioned by short_code.
5. Key generation: 7-char base62 gives 62^7, about 3.5 trillion codes, roughly
   100x the 36.5B URLs needed for 10 years. Generate codes from a distributed
   counter (ranges handed to each app server) encoded in base62, so there are no
   collisions. Collision probability for random or hashed codes is hash math
   owned by the dsa lane.
6. Architecture: load balancer, stateless app servers, cache-aside Redis for
   hot codes, key-value database partitioned with consistent hashing.
7. Scaling: cache the hottest ~20% of codes (80/20 rule), replicate the
   database leader-follower, rate limit creation per user.
8. Trade-offs: 301 is cacheable by browsers (less load, weaker analytics); 302
   keeps every redirect visible for analytics.

### 4.2 Newsfeed fanout

Use fanout-on-write for normal accounts: a post is pushed into each follower's
precomputed feed list, so reads are cheap. Use fanout-on-read for celebrity
accounts with millions of followers, merging their recent posts at read time.
This hybrid avoids millions of synchronous writes per celebrity post. Fanout
runs asynchronously through a work queue, never in the request path.

### 4.3 Distributed rate limiter

Run a token bucket per client key in a shared store such as Redis so every API
server sees the same counts. Refill and spend atomically in a single
script or transaction to avoid races. Return 429 with Retry-After when the
bucket is empty. A sliding-window counter is the alternative when bursts must be
smoothed. If the shared store is down, fail open for low-risk endpoints and fail
closed for expensive ones.

### 4.4 Chat delivery

Clients hold WebSocket connections to gateway servers; a presence service maps
users to gateways. Each conversation has a monotonically increasing sequence
number so clients can order messages and detect gaps. Delivery is
at-least-once; clients deduplicate by message id, which acts as an idempotency
key. Offline users receive messages from durable storage when they reconnect.

## 5. Failure modes (what goes wrong, how to recognize)

- **Database as a queue**: polling the primary database table for jobs causes
  lock contention, hot rows, and vacuum or index bloat, and it competes with
  user traffic. Fix: move jobs to a real message queue, and use the
  transactional outbox if the job must be created atomically with a row.
- **Synchronous fanout**: writing to every follower's feed inside the request
  makes post latency grow with follower count and times out for celebrities.
  Fix: publish one event and fan out asynchronously through a work queue,
  hybrid fanout-on-read for celebrities.
- **Missing idempotency**: client or gateway retries of a payment or order
  create duplicate charges. Fix: require idempotency keys; idempotency keys
  collapse retried writes to a single effect.
- **Cache stampede (thundering herd)**: a hot key expires and thousands of
  requests miss at once and hammer the database. Fix: request coalescing
  (single flight), a lock so one request repopulates, jittered TTLs, or serving
  stale while revalidating.
- **Hot partition / hot key**: one key or shard receives most traffic. Fix:
  add a cache in front, split the key with a suffix, or use consistent hashing
  with virtual nodes.
- **Unbounded queue**: a slow consumer lets the queue grow until memory runs
  out. Fix: bounded queues and back-pressure; back-pressure propagates slowness
  upstream to prevent queue blowup.
- **Dual write**: writing to the database and then publishing to a queue
  separately loses events when the second step fails. Fix: transactional
  outbox.

## 6. Abstention and delegation rules

- If a question is about **algorithm complexity, data-structure internals, or
  hash collision probability**, do not answer from this lane; delegate to the
  dsa lane.
- If a question is about **behavioral stories** (conflict, leadership, failure),
  delegate to the behav lane. Resume questions go to the resume lane; running or
  scoring a mock interview goes to the mock lane.
- If a question is about something **not covered here** (for example CRDT merge
  semantics, Raft or Paxos internals, or vendor pricing), say the corpus does not
  cover it and offer the closest covered concept, such as the consistency
  ladder, rather than inventing details.
- Never invent numbers. Show the capacity arithmetic and its assumptions.

## 7. Glossary

| Term | One-line meaning |
|---|---|
| Horizontal scaling | Add machines and partition load |
| PACELC | Partition: A or C; Else: Latency or Consistency |
| Consistent hashing | Hash ring; only ~1/N keys move when nodes change |
| Read-your-writes | Session guarantee: you see your own writes |
| Idempotency key | Client id that makes retried writes apply once |
| Back-pressure | Downstream slowness signalled upstream |
| Transactional outbox | DB row + outbox row in one transaction, relayed to a queue |
| Saga | Local steps with compensating actions |
| Cache stampede | Many misses on one expired hot key |

## 8. Checklist (memorizable summary)

- Run the 8 steps: requirements, capacity, API, data model, architecture, deep
  dives, scaling, trade-offs.
- Do capacity math out loud: QPS, read:write ratio, storage over years.
- Pick a consistency level from the ladder and justify it.
- Put a queue between spiky producers and slow consumers, and add back-pressure.
- Use idempotency keys on any retried write.
- Never fan out synchronously in the request path.
- Delegate complexity and hash math to dsa; abstain on uncovered topics.
