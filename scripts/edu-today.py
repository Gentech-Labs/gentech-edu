#!/usr/bin/env python3
"""edu-today.py — "what am I supposed to do today?" in one screen. READ-ONLY by construction.

WHAT JORDAN ASKED FOR
  *"as we talk through the lesson plan, like I could get like refreshed on today's lesson"* (2026-10-27)

WHAT "TODAY'S LESSON" MEANS HERE — the decision, stated so nobody expects the other one
  The engine has no calendar. It serves **the next UNMET milestone**, in pack order. So:

      today's lesson  =  the milestone the engine is serving RIGHT NOW

  NOT a dated study plan. A dated plan needs a pace decision (hours/week) that belongs to Jordan, and inventing
  dates would be a promise the engine cannot keep. What this adds on top is a **7-day recap**: what closed, what
  he wrote down. That is the "refreshed" part — recency, not scheduling.

SEPARATION
  This script reads engine output (via `fde-lesson.py`, so the sequence is never re-implemented here) and reads
  the notebook. It writes NOTHING: no state, no notes, no cache. If a future version caches, the cache goes
  beside the notebook, never into engine state.

USAGE
  edu-today.py [--track career] [--learner jordan] [--days 7] [--json]
"""
import argparse, datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.environ.get("EDU_VAULT", "/opt/data/.obsidian-vault")
NOTEBOOK_ROOT = os.path.join(VAULT, "EDU", "notebook")
ENGINE = os.path.join(HERE, "fde-lesson.py")
DATA = os.path.join(HERE, "..", "data")


def engine_serve(track):
    """Reuse the engine's own words. Never re-implement the sequence here."""
    try:
        out = subprocess.run([sys.executable, ENGINE, "--track", track],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip(), out.returncode
    except Exception as e:
        return f"engine unavailable: {e}", 1


def nearest_hard_date(track, within_days=400):
    try:
        pack = json.load(open(os.path.join(DATA, f"{track}-track.json"), encoding="utf-8"))
    except Exception:
        return None
    today = datetime.date.today()
    best = None
    for x in pack.get("hard_dates") or []:
        try:
            d = datetime.date.fromisoformat(x["date"])
        except Exception:
            continue
        days = (d - today).days
        if 0 <= days <= within_days and (best is None or days < best["days"]):
            best = {"date": x["date"], "days": days, "what": x.get("what", "")}
    return best


def recent_notes(learner, days):
    base = os.path.join(NOTEBOOK_ROOT, learner)
    if not os.path.isdir(base):
        return []
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    rows = []
    for f in sorted(os.listdir(base)):
        if not f.endswith(".md"):
            continue
        p = os.path.join(base, f)
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        if mt < cutoff:
            continue
        lines = [ln.rstrip("\n") for ln in open(p, encoding="utf-8", errors="replace")]
        body = [ln for ln in lines[1:] if ln.strip() and not ln.startswith("---")
                and not ln.split(":")[0].strip() in
                {"learner", "date", "track", "milestone", "tags", "kind", "evidence"}]
        rows.append({"file": f, "when": mt.strftime("%Y-%m-%d %H:%M"), "first_line": (body[0] if body else "")[:100]})
    return sorted(rows, key=lambda r: r["when"], reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="career")
    ap.add_argument("--learner", default="jordan")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    served, rc = engine_serve(a.track)
    hd = nearest_hard_date(a.track)
    notes = recent_notes(a.learner, a.days)

    if a.json:
        print(json.dumps({"track": a.track, "learner": a.learner, "engine_rc": rc,
                          "served": served, "nearest_hard_date": hd,
                          "notes_last_%dd" % a.days: notes}, indent=1))
        return 0 if rc == 0 else 2

    today = datetime.date.today().isoformat()
    print(f"EDU · today — {today}  ·  track: {a.track}  ·  learner: {a.learner}")
    print("-" * 78)
    if hd:
        print(f"HARD DATE   {hd['date']}  in {hd['days']}d — {hd['what'][:90]}")
        print()
    print("THE LESSON THE ENGINE IS SERVING (not a calendar day — the next unmet milestone):")
    for line in served.splitlines():
        print("  " + line)
    print()
    print(f"WHAT YOU WROTE IN THE LAST {a.days} DAYS ({len(notes)} note(s)):")
    if not notes:
        print("  — nothing yet. Notes are yours, they are not evidence, and they cannot close a milestone.")
    for n in notes:
        print(f"  {n['when']}  {n['first_line']}")
        print(f"      {os.path.join(NOTEBOOK_ROOT, a.learner, n['file'])}")
    print()
    print("A note never closes a milestone. Only evidence does: --done <ID> --evidence <commit|url|path|exam result>")
    return 0 if rc == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
