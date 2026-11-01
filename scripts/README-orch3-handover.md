# ORCH-3 — handover: how to run this without me

**Artifact:** `scripts/orch3-graph.py` · LangGraph **1.2.18** · Python 3.14
**Outputs:** `cache/orch3/{results.json, state-*.json, draft-*.md}`

---

## Run it

```bash
python3 -m venv orchvenv
./orchvenv/bin/pip install langgraph
./orchvenv/bin/python scripts/orch3-graph.py
```

**Runtime: under 1 second.** No GPU, no API key, no network. It reads a local EPUB.

**Exit code is the signal:** `0` = all checks passed, `1` = at least one failed. It prints a verdict table
either way, so a CI job or a cron can gate on it.

---

## The graph

```
plan ──┬──> research_A ──(retry? / join)──┐
       └──> research_B ──(retry? / join)──┴──> writer ──> guard ──> END
```

**Five nodes, and the reason each exists:**

| Node | Job | Why it is separate |
|---|---|---|
| `plan` | sets the branches and initialises state | one place decides scope; nodes never negotiate |
| `research_A` / `research_B` | keyword retrieval over the corpus | **run in the same superstep** — this is the "do not block each other" claim |
| `writer` | joins both, drafts, marks gaps | the join point; it must tolerate a missing branch |
| `guard` | hard iteration ceiling | an orchestration bug becomes a stopped run, not a bill |

**Termination condition:** `writer` → `guard` → `END`. `guard` aborts if the trace exceeds
`MAX_ITERATIONS = 12`. There is no path that loops without a counter.

---

## Three things that will bite you, and what I did about them

### 1. Two nodes cannot write the same plain key in one step
```
InvalidUpdateError: At key 'iterations': Can receive only one value per step.
```
A scalar written by both parallel researchers **raises**. Fixed by giving every shared key a reducer:
- `trace` → `operator.add` (append-only, so the step order is auditable after the run)
- `findings`, `attempts`, `errors` → a merge reducer, because both branches write into them
- `status`, `draft`, `gaps`, `branches` → explicit last-write-wins

**This is the first bug you will hit if you add a third branch.** It is not a warning; it is a hard error.

### 2. `status` is contended too, not just the counter
The first fix only reduced `iterations` and the same error immediately reappeared on `status`. **Reduce every
shared key, not the one that failed first** — the second failure is the same defect wearing a different name.

### 3. Retry needs a bounded counter in STATE, not in a local variable
`route_branch()` reads `attempts[branch]` from state on every pass. A counter in a closure would reset per
invocation and the graph would loop forever. **The ceiling must live in state so the router can see it.**

---

## How recovery is proved, not claimed

The script injects real faults (`FAULTS` dict) and asserts outcomes:

| Scenario | Injection | Expected | Measured |
|---|---|---|---|
| `happy_path` | none | both branches, complete | ✅ A+B, 0.15s |
| `transient_A` | A fails once | **retried**, then complete | ✅ A attempts=2, complete |
| `permanent_B` | B fails always | A unaffected, gap recorded, **terminates** | ✅ A present, gaps=['B'], 0.02s |

**The point of `permanent_B`:** a branch that cannot succeed must not stop the graph and must not be hidden.
The draft says so in line: `> INCOMPLETE — branches B failed after 2 attempt(s)`.

---

## Changing it

**Add a branch:** add the node, `g.add_edge("plan", "research_C")`, `add_conditional_edges(...)`. Nothing else
— the reducers already handle three writers. `plan` returns `branches: ["A","B","C"]`.

**Change the retry budget:** `MAX_ATTEMPTS`. It is one constant; the router reads it.

**Swap the writer for a model call:** replace `writer()`'s body. **Keep the gap-marking** — a model that is
handed a failed branch will happily invent its contents, which is the failure this graph exists to prevent.

**Change the corpus:** set `EPUB` to any EPUB. `corpus()` extracts text with stdlib only.

---

## What is NOT proven here

- **Concurrency is LangGraph's superstep, not threads I wrote.** I did not measure wall-clock savings from
  parallel branches — with a 0.15s runtime there is nothing to measure. **Do not cite this as a speed result.**
- **The researcher is keyword search, not a model.** It is deterministic on purpose: a non-deterministic
  branch would make a passing run unrepeatable, and orchestration is what is under test.
- **No checkpointing/persistence configured.** A crash mid-run loses state. `langgraph-checkpoint` is
  installed; wiring a SQLite saver is the next step and is **not done**.
- **No token/cost accounting.** With a real writer that becomes essential.
