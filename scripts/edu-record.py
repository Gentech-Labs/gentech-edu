#!/usr/bin/env python3
"""edu-record.py — record what the learner actually did. THE MISSING WRITE.

MEASURED 2026-10-18: `life-lesson-engine.py` READS mastery (`mastery()`, `build_lesson()` sorts weak
first) but **nothing anywhere writes an attempt back**. So the drill loop — the one thing this system
exists to do — could never close: every lesson would show every phrase as NEW, forever. The engine was
half a loop, and no selftest caught it because every test hand-built the `seen` dict instead of
producing one the way a learner would.

This is the other half: one attempt in, the same record shape out.

    python3 edu-record.py --learner jordan --dialect ne-NP --key "ne-NP:धन्यवाद" --correct
    python3 edu-record.py --learner jordan --dialect ne-NP --key "..." --miss
    python3 edu-record.py --learner jordan --show

RECORD SHAPE (must match what `mastery()` returns — `{key: {attempts, correct}}`):
    {"ne-NP:धन्यवाद": {"attempts": 3, "correct": 2, "last": "2026-10-18T21:04:00"}}

RULES IT ENFORCES
  - An unknown learner is an ERROR (same registry rule as the engine), never a new file invented.
  - A key must belong to THIS learner's dialect. Recording `th-TH:…` against a ne-NP session would key
    progress to a phrase that learner was never served.
  - A write is atomic (tmp + replace) so an interrupted save cannot truncate a learner's history.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
DATA = SKILL_DIR / "data"


def _seat() -> str:
    parts = pathlib.Path(__file__).resolve().parts
    if "profiles" in parts:
        i = parts.index("profiles")
        if i + 1 < len(parts):
            return parts[i + 1]
    return "gentech"


SEAT = _seat()
PROFILE = pathlib.Path("/opt/data/profiles") / SEAT


def state_path(learner: str) -> pathlib.Path:
    return PROFILE / "state" / "learners" / f"{learner}.json"


def load_registry() -> dict:
    f = DATA / "learners.json"
    try:
        return json.loads(f.read_text())
    except Exception as e:
        raise SystemExit(f"🔴 learner registry unreadable ({f}): {e}")


def known_learner(learner: str) -> dict:
    reg = load_registry()
    entry = (reg.get("learners") or {}).get(learner)
    if not entry:
        raise SystemExit(f"🔴 unknown learner '{learner}'. Registry: {DATA / 'learners.json'} — "
                         f"known: {', '.join((reg.get('learners') or {}).keys())}")
    return entry


def read_record(learner: str) -> dict:
    p = state_path(learner)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        # Damage is NOT "no history" — the same rule the engine's mastery() learned.
        raise SystemExit(f"🔴 progress record is DAMAGED ({p}): {e}\n   Refusing to overwrite it. "
                         f"Fix or move the file first; a learner's history is not disposable.")


def write_record(learner: str, rec: dict) -> pathlib.Path:
    p = state_path(learner)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True))
    tmp.replace(p)                      # atomic: never a half-written history
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learner", required=True)
    ap.add_argument("--dialect", default=None)
    ap.add_argument("--key", default=None, help="the phrase key exactly as served (dialect:phrase)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--correct", action="store_true")
    grp.add_argument("--miss", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()

    entry = known_learner(a.learner)

    if a.show or not a.key:
        rec = read_record(a.learner)
        if not rec:
            print(f"{a.learner}: NO observations recorded yet — UNMEASURED, not 0%.")
            return 0
        total = sum(v.get("attempts", 0) for v in rec.values())
        good = sum(v.get("correct", 0) for v in rec.values())
        print(f"{a.learner}: {len(rec)} phrase(s) observed · {good}/{total} correct")
        for k, v in sorted(rec.items(), key=lambda kv: -kv[1].get("attempts", 0))[:12]:
            acc = v.get("correct", 0) / max(v.get("attempts", 1), 1)
            flag = "🔁" if acc < 0.6 else "✅"
            print(f"  {flag} {k}  {v.get('correct',0)}/{v.get('attempts',0)}  last={v.get('last','?')}")
        return 0

    if not a.dialect:
        raise SystemExit("🔴 --dialect is required when recording (guards against cross-dialect keys)")
    if not a.key.startswith(f"{a.dialect}:"):
        raise SystemExit(f"🔴 key '{a.key}' does not belong to dialect {a.dialect}. "
                         f"A key is '{a.dialect}:<phrase as served>'.")
    if not (a.correct or a.miss):
        raise SystemExit("🔴 say what happened: --correct or --miss")

    rec = read_record(a.learner)
    row = rec.get(a.key) or {"attempts": 0, "correct": 0}
    row["attempts"] = int(row.get("attempts", 0)) + 1
    if a.correct:
        row["correct"] = int(row.get("correct", 0)) + 1
    row["last"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec[a.key] = row
    p = write_record(a.learner, rec)

    acc = row["correct"] / row["attempts"]
    print(f"{'✅' if a.correct else '❌'} {a.key}  →  {row['correct']}/{row['attempts']} "
          f"({acc:.0%}) · {'weak — will drill first' if acc < 0.6 else 'solid'}")
    print(f"   wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
