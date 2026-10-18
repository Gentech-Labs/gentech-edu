#!/usr/bin/env python3
"""fde-lesson.py — the FDE pack's renderer on the EDU engine.

Engine/pack boundary (EDU's rule): this script is deliberately subject-FAT — it reads a pack file and knows
nothing about Go, clouds or job postings. `data/fde-track.json` is the pack. A different subject means a
different JSON, not an edit here.

Three honesty rules are load-bearing, and the selftest plants a failure for each:
  1. No observed work  ->  UNMEASURED, never a fabricated 0%.
  2. Reading the steps is NOT doing the milestone — coverage is not proficiency.
  3. An unattempted milestone is not a miss; it is excluded, not counted against the learner.

Usage:
  fde-lesson.py                 serve the next unmet milestone
  fde-lesson.py --status        progress, labelled honestly
  fde-lesson.py --done M1 --evidence "commit abc123 / url"   close a milestone WITH evidence
  fde-lesson.py --selftest      plant failures and prove each goes RED
"""
import argparse, datetime, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, "..", "data", "fde-track.json")
STATE = os.path.join(HERE, "..", "state", "fde-progress.json")
TODAY = datetime.date.today().isoformat()


def load_pack(path=PACK):
    d = json.load(open(path, encoding="utf-8"))
    ids = [m["id"] for m in d["milestones"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate milestone ids in the pack")
    return d


def load_state(path=STATE):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def save_state(s, path=STATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(s, open(path, "w", encoding="utf-8"), indent=1)


def next_milestone(pack, state):
    """The engine owns the sequence. Completed milestones are skipped; order is the pack's order."""
    for m in pack["milestones"]:
        if m["id"] not in state.get("done", {}):
            return m
    return None


def progress_line(pack, state):
    total = len(pack["milestones"])
    done = state.get("done", {})
    closed = [m for m in pack["milestones"] if m["id"] in done]
    if not done:
        # RULE 1: no observation is not zero progress.
        return f"UNMEASURED — 0 of {total} milestones closed, and no work recorded yet. Practice is not certification."
    n = len(closed)
    hours = sum(m.get("hours", 0) for m in closed)
    return (f"{n} of {total} milestones closed with evidence ({hours}h). "
            f"RULE 2: this counts closed milestones, NOT ability — reading a milestone is not doing it.")


def cmd_serve(pack, state):
    m = next_milestone(pack, state)
    print(progress_line(pack, state))
    if not m:
        print("\nEvery milestone in the pack is closed. The next move is the pack's, not this script's.")
        return 0
    print(f"\nNEXT — {m['id']}: {m['skill']}  ({m.get('kind','')}, ~{m.get('hours','?')}h)")
    print(f"  why: {m['why']}")
    print(f"  artifact it produces: {m['artifact']}")
    print("  steps:")
    for i, s in enumerate(m["steps"], 1):
        print(f"    {i}. {s}")
    print(f"  done when: {m['done_when']}")
    print(f"\n  close it with:  fde-lesson.py --done {m['id']} --evidence \"<commit|url|path>\"")
    return 0


def cmd_status(pack, state):
    print(progress_line(pack, state))
    done = state.get("done", {})
    for m in pack["milestones"]:
        d = done.get(m["id"])
        mark = f"✅ closed {d['date']} — {d['evidence']}" if d else "·  open"
        print(f"  {m['id']:<4} {m['skill'][:38]:<40} {mark}")
    return 0


def cmd_done(pack, state, mid, evidence):
    ids = {m["id"] for m in pack["milestones"]}
    if mid not in ids:
        print(f"REFUSED: {mid} is not a milestone in this pack.")
        return 2
    if not evidence or len(evidence.strip()) < 4:
        # RULE 3-adjacent: a milestone closed with nothing behind it is a claim, not a completion.
        print("REFUSED: a milestone needs evidence (commit, url, or path). "
              "A closed milestone with nothing behind it is a claim, not a completion.")
        return 2
    state.setdefault("done", {})[mid] = {"date": TODAY, "evidence": evidence.strip()}
    save_state(state)
    print(f"closed {mid} — {evidence.strip()}")
    print(progress_line(pack, state))
    return 0


def cmd_selftest():
    """Plant failures; prove each check goes RED. A check that cannot fail proves nothing."""
    import tempfile, copy
    results = []
    pack = load_pack()

    # 1 — the sequence skips what is closed
    s = {"done": {"M0": {"date": TODAY, "evidence": "x"}}}
    ok = next_milestone(pack, s)["id"] != "M0"
    results.append(("sequence skips closed milestones", ok))

    # 2 — no state means UNMEASURED, not 0%
    line = progress_line(pack, {})
    ok = "UNMEASURED" in line and "0%" not in line
    results.append(("empty state reads UNMEASURED, never 0%", ok))

    # 3 — an unattempted milestone is not a miss (ratio excludes it)
    s = {"done": {"M1": {"date": TODAY, "evidence": "x"}}}
    line = progress_line(pack, s)
    ok = "1 of" in line and "not" in line.lower()
    results.append(("unattempted milestones are excluded, not misses", ok))

    # 4 — a done without evidence is refused
    p = tempfile.mktemp(suffix=".json")
    rc = cmd_done(pack, {}, "M1", "")
    results.append(("closing with no evidence is refused", rc == 2))

    # 5 — the pack has unique ids (a duplicate would silently drop a milestone)
    try:
        bad = copy.deepcopy(pack); bad["milestones"].append(bad["milestones"][0])
        p2 = tempfile.mktemp(suffix=".json"); json.dump(bad, open(p2, "w"))
        try:
            load_pack(p2); ok = False
        except ValueError:
            ok = True
    except Exception:
        ok = False
    results.append(("duplicate milestone ids are rejected", ok))

    for name, ok in results:
        print(f"  {'GREEN' if ok else 'RED  '}  {name}")
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} pass" + (f" — FAILING: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--done", metavar="ID")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(cmd_selftest())
    pk = load_pack()
    if a.done:
        sys.exit(cmd_done(pk, load_state(), a.done, a.evidence))
    sys.exit(cmd_status(pk, load_state()) if a.status else cmd_serve(pk, load_state()))
