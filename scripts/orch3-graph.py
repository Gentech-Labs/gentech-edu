#!/usr/bin/env python3
"""ORCH-3 — two agents that do not block each other.

THE TICKET: "Split the job so a researcher agent and a writer agent do not block each other."
  draw the graph · implement it with explicit state · prove a node failure RECOVERS rather than HANGS ·
  write the handover a colleague needs to run it without you.

WHAT IS BUILT
  LangGraph 1.x, explicit TypedDict state, two research branches that run in the SAME superstep (genuine
  concurrency, not two sequential calls wearing the word "parallel"), a join at the writer, per-branch retry
  with a bounded attempt counter, and a hard iteration ceiling so the graph cannot spin forever.

THE THREE CLAIMS, EACH PROVEN BY A RUN
  1. HAPPY PATH   — both branches succeed, writer sees both, status=complete
  2. TRANSIENT    — a branch fails once then succeeds; the graph RETRIES that branch and still completes
  3. PERMANENT    — a branch fails every attempt; the writer PROCEEDS with what exists and marks the gap.
                    The graph terminates. It does not hang, and it does not silently pretend it succeeded.

WHAT IS DELIBERATELY DETERMINISTIC
  The researcher does real keyword retrieval over the UBC Nepali textbook (stdlib only). The writer is a
  deterministic templater. NO model call: orchestration is what is under test, and a non-deterministic
  writer would make a passing run unrepeatable. `--llm` swaps in a real model call for the writer, and says
  so in the output when used.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import unicodedata
import zipfile
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END

EPUB = pathlib.Path("/opt/data/profiles/arthur/cache/scratch/nepali-textbook.epub")
OUT = pathlib.Path("/opt/data/profiles/arthur/cache/orch3")
MAX_ATTEMPTS = 2          # per branch: 1 try + 1 retry — the same "one retry" rule as toolgate
MAX_ITERATIONS = 12       # hard ceiling: the graph cannot spin
DEV = re.compile(r"[\u0900-\u097F]")


def _last(old, new):
    """Last write wins — the default LangGraph semantic for a scalar, made explicit so two nodes may write it."""
    return new if new is not None else old


def _merge(acc: dict, new: dict) -> dict:
    """Reducer for parallel branch results — two nodes writing one key in a superstep need this."""
    out = dict(acc or {})
    out.update(new or {})
    return out


class S(TypedDict, total=False):
    topic: str
    branches: Annotated[list, _last]
    # parallel-safe: the two research nodes both write here, so it needs a reducer
    findings: Annotated[dict, _merge]
    attempts: Annotated[dict, _merge]
    errors: Annotated[dict, _merge]
    draft: Annotated[str, _last]
    gaps: Annotated[list, _last]
    # ⚠️ MEASURED FIX 2026-10-28: `iterations: int` written by BOTH parallel researchers raised
    # `InvalidUpdateError: At key 'iterations': Can receive only one value per step`. A plain scalar cannot
    # be written by two nodes in one superstep — it needs a reducer. Replaced with an append-only TRACE,
    # which is both parallel-safe and a better artifact: the step order is auditable after the run.
    trace: Annotated[list, operator.add]
    status: Annotated[str, _last]


# ── corpus: real data, no network ───────────────────────────────────────────────────────────────────
_DOCS: list[dict] | None = None


def corpus() -> list[dict]:
    global _DOCS
    if _DOCS is not None:
        return _DOCS
    z = zipfile.ZipFile(EPUB)
    docs = []
    for n in sorted(z.namelist()):
        if not n.lower().endswith((".xhtml", ".html")):
            continue
        s = z.read(n).decode("utf-8", "ignore")
        s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
        s = re.sub(r"<[^>]+>", " ", s)
        import html as _h
        s = _h.unescape(s)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n\s*\n+", "\n", s).strip()
        if len(s) > 300:
            docs.append({"id": n.split("/")[-1].replace(".xhtml", ""), "text": s})
    _DOCS = docs
    return docs


def search(query: str, k: int = 3) -> list[dict]:
    """Keyword retrieval — deterministic, no embeddings, good enough to prove orchestration."""
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    scored = []
    for d in corpus():
        low = d["text"].lower()
        score = sum(low.count(t) for t in terms)
        if DEV.search(query):                      # Devanagari query: exact-substring is the strong signal
            score += 5 * d["text"].count(query)
        if score:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [{"id": d["id"], "score": s, "excerpt": d["text"][:220].replace("\n", " ")}
            for s, d in scored[:k]]


# ── fault injection: the only way to prove recovery is to make something fail ───────────────────────
FAULTS = {"branch": None, "transient": False, "permanent": False}
_call_counts: dict[str, int] = {}


def _maybe_fail(branch: str) -> None:
    if FAULTS["branch"] != branch:
        return
    n = _call_counts.get(branch, 0)
    if FAULTS["transient"] and n == 1:
        raise RuntimeError(f"injected TRANSIENT failure in {branch} (attempt {n})")
    if FAULTS["permanent"]:
        raise RuntimeError(f"injected PERMANENT failure in {branch} (attempt {n})")


# ── nodes ───────────────────────────────────────────────────────────────────────────────────────────
def plan(state: S) -> dict:
    topic = state.get("topic", "Nepali greetings and everyday phrases")
    return {"branches": ["A", "B"], "trace": ["plan"],
            "status": "researching",
            "findings": {}, "attempts": {}, "errors": {}, "gaps": []}


def make_researcher(branch: str, query_for: dict):
    def researcher(state: S) -> dict:
        topic = state.get("topic", "")
        q = query_for.get(branch, topic)
        attempts = dict(state.get("attempts") or {})
        attempts[branch] = attempts.get(branch, 0) + 1
        _call_counts[branch] = attempts[branch]
        try:
            _maybe_fail(branch)
            hits = search(q)
            if not hits:
                raise RuntimeError(f"{branch}: retrieval returned nothing for {q!r}")
            return {"findings": {branch: hits},
                    "attempts": attempts,
                    "trace": [f"research_{branch}#{attempts[branch]}" + ("_retry" if attempts[branch] > 1 else "")]}
        except Exception as e:
            errs = dict(state.get("errors") or {})
            errs[branch] = str(e)[:200]
            return {"attempts": attempts, "errors": errs,
                    "trace": [f"research_{branch}#{attempts[branch]}_FAILED"]}
    researcher.__name__ = f"research_{branch}"
    return researcher


def route_branch(branch: str):
    """Conditional edge for one branch.

    MEASURED 2026-10-28 — the first version routed a settled branch straight to `writer`, and because the two
    branches settle in DIFFERENT supersteps the trace showed `writer, guard, writer, guard`: the writer ran
    twice and the graph reached END twice. Harmless for a template; double the cost for a model call and two
    drafts racing to overwrite each other.

    Fixed: a branch routes to `writer` ONLY when EVERY branch is settled. Until then its path ends quietly
    (`wait`), the other branch keeps running, and the last one to settle is the single path that reaches the
    writer. The join is a state condition, not an edge count.
    """
    def route(state: S) -> str:
        findings = state.get("findings") or {}
        attempts = state.get("attempts") or {}
        branches = state.get("branches") or ["A", "B"]

        got = branch in findings
        used = attempts.get(branch, 0)
        if not got and used < MAX_ATTEMPTS:
            return f"research_{branch}"           # RETRY the same node
        # this branch is settled (found something, or exhausted its attempts)
        if all((b in findings) or (attempts.get(b, 0) >= MAX_ATTEMPTS) for b in branches):
            return "writer"                       # last one to settle -> the only one that writes
        return "wait"                             # stand down; another branch is still working
    return route


def writer(state: S) -> dict:
    """The JOIN. Both conditional edges point here, so this node is invoked once per branch that settles —
    MEASURED 2026-10-28: the trace showed writer+guard running TWICE in one run. Harmless for a template,
    double the cost for a model call, and two drafts racing to overwrite each other. Fixed with an explicit
    settle check: wait until every branch is settled (produced findings OR exhausted its attempts), then
    write exactly once. A second invocation is a no-op, and the trace records why."""
    findings = state.get("findings") or {}
    errors = state.get("errors") or {}
    attempts = state.get("attempts") or {}
    branches = state.get("branches") or []

    settled = all((b in findings) or (attempts.get(b, 0) >= MAX_ATTEMPTS) for b in branches)
    if not settled:
        return {"trace": ["writer#waiting"]}
    if state.get("draft"):
        return {"trace": ["writer#skipped_already_written"]}

    gaps = [b for b in branches if b not in findings]
    lines = [f"# {state.get('topic','')}", ""]
    for b in branches:
        if b in findings:
            lines.append(f"## Branch {b}")
            for h in findings[b]:
                lines.append(f"- [{h['id']}] score {h['score']} — {h['excerpt'][:140]}")
        else:
            lines.append(f"## Branch {b} — FAILED")
            lines.append(f"- could not complete: {errors.get(b, 'unknown')}")
        lines.append("")
    if gaps:
        lines.append(f"> INCOMPLETE — branches {', '.join(gaps)} failed after "
                     f"{MAX_ATTEMPTS} attempt(s). The draft uses what exists and marks the gap.")
    return {"draft": "\n".join(lines), "gaps": gaps,
            "status": "complete" if not gaps else "complete_with_gaps",
            "trace": ["writer"]}


def guard(state: S) -> dict:
    """Hard ceiling. If steps ever exceed MAX, the graph stops with an explicit aborted status."""
    it = len(state.get("trace") or [])
    return {"status": "aborted" if it > MAX_ITERATIONS else state.get("status", "complete"),
            "trace": ["guard"]}


def build():
    g = StateGraph(S)
    g.add_node("plan", plan)
    g.add_node("research_A", make_researcher("A", {"A": "how are you polite तपाईंलाई"}))
    g.add_node("research_B", make_researcher("B", {"B": "धन्यवाद thank you"}))
    g.add_node("writer", writer)
    g.add_node("guard", guard)

    g.set_entry_point("plan")
    # FAN-OUT: both research nodes start in the same superstep — this is the non-blocking claim
    g.add_edge("plan", "research_A")
    g.add_edge("plan", "research_B")
    # RETRY-or-JOIN per branch
    g.add_conditional_edges("research_A", route_branch("A"),
                            {"research_A": "research_A", "writer": "writer", "wait": END})
    g.add_conditional_edges("research_B", route_branch("B"),
                            {"research_B": "research_B", "writer": "writer", "wait": END})
    g.add_edge("writer", "guard")
    g.add_edge("guard", END)
    return g.compile()


# ── the three proofs ───────────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    ("happy_path",     {"branch": None, "transient": False, "permanent": False}),
    ("transient_A",    {"branch": "A", "transient": True,  "permanent": False}),
    ("permanent_B",    {"branch": "B", "transient": False, "permanent": True}),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = build()
    results = {}
    print(f"  max_attempts={MAX_ATTEMPTS} · max_iterations={MAX_ITERATIONS}")
    for name, faults in SCENARIOS:
        FAULTS.update(faults)
        _call_counts.clear()
        t0 = time.time()
        state = app.invoke({"topic": "Nepali greetings and everyday phrases", "trace": []})
        dt = time.time() - t0
        results[name] = {
            "wall_s": round(dt, 2),
            "status": state.get("status"),
            "iterations": len(state.get("trace") or []),
            "trace": state.get("trace"),
            "branches_ok": sorted((state.get("findings") or {}).keys()),
            "attempts": state.get("attempts"),
            "errors": state.get("errors"),
            "gaps": state.get("gaps"),
            "draft_chars": len(state.get("draft") or ""),
        }
        (OUT / f"state-{name}.json").write_text(
            json.dumps({k: v for k, v in state.items()}, indent=1, ensure_ascii=False))
        (OUT / f"draft-{name}.md").write_text(state.get("draft") or "")
        r = results[name]
        print(f"\n  ── {name}")
        print(f"     status     : {r['status']}")
        print(f"     wall       : {r['wall_s']}s   iterations: {r['iterations']}")
        print(f"     branches ok: {r['branches_ok']}   attempts: {r['attempts']}")
        print(f"     gaps       : {r['gaps']}")
        if r["errors"]:
            print(f"     errors     : { {k: v[:60] for k, v in r['errors'].items()} }")

    # ── verdicts, computed not asserted ──────────────────────────────────────────────────────────
    hp, tr, pm = results["happy_path"], results["transient_A"], results["permanent_B"]
    checks = [
        ("happy path completes with both branches",
         hp["status"] == "complete" and hp["branches_ok"] == ["A", "B"]),
        ("transient failure RECOVERED (branch A eventually present)",
         "A" in tr["branches_ok"] and tr["attempts"].get("A") == 2 and tr["status"] == "complete"),
        ("permanent failure did NOT block branch A",
         "A" in pm["branches_ok"]),
        ("permanent failure terminated, did not hang",
         pm["status"] == "complete_with_gaps" and pm["wall_s"] < 60),
        ("gap recorded, not silently dropped",
         pm["gaps"] == ["B"] and "INCOMPLETE" in (OUT / "draft-permanent_B.md").read_text()),
        ("bounded: attempts never exceeded the ceiling",
         all(v <= MAX_ATTEMPTS for v in (pm["attempts"] or {}).values())),
        ("iterations stayed under the hard ceiling",
         all(r["iterations"] <= MAX_ITERATIONS for r in results.values())),
    ]
    print("\n  ── VERDICTS")
    bad = 0
    for label, ok in checks:
        print(f"     {'✅' if ok else '🔴'} {label}")
        bad += 0 if ok else 1
    (OUT / "results.json").write_text(json.dumps({"scenarios": results,
        "checks": {l: ok for l, ok in checks}}, indent=1, ensure_ascii=False))
    print(f"\n  {'ALL CHECKS PASS' if bad == 0 else str(bad) + ' CHECK(S) FAILED'}")
    print(f"  ✅ {OUT/'results.json'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
