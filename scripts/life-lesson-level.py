#!/usr/bin/env python3
"""
life-lesson-level.py — GenTech EDU: "how good do I actually need to be?" (the LEVEL layer).

WHY THIS EXISTS
---------------
Jordan (2026-09-24): *"I want to get my Spanish to a better speaking level before I go to somewhere like
Santo Domingo or Santiago or any of the other Dominican cities."*

That is a DIFFERENT requirement from the trip he already has priced, and our build did not cover it:

  · The engine teaches the DOMINICAN DIALECT. It had no notion of a LEVEL.
  · Sosúa (his booked trip) is a tourist town where English works. Santo Domingo/Santiago are not —
    outside the hotel desk, English thins out fast.
  · So "better speaking level" needs a TARGET, and the target is a property of the PLACE, not of the
    language. `es-DO` is the same dialect in both; the required level is not.

This script answers three questions, in this order:
  1. What level does this trip actually require?    (PACK data — `data/level-targets.json`)
  2. Roughly where is he now?                        (from OBSERVED practice, or "unmeasured")
  3. What is the honest gap, in hours and calendar?  (CEFR ladder arithmetic)

HONESTY RULES (non-negotiable — this is a self-assessment tool and the easiest place in the fleet to lie)
--------------------------------------------------------------------------------------------------------
  · NEVER prints a CEFR level as a fact about him. Phrase-bank practice CANNOT certify a level.
    Anything derived from it is labelled ESTIMATE, and the basis is printed.
  · NO observed practice -> "unmeasured". Never a fabricated 0%, never a default "you're A1".
  · BANK COVERAGE IS NOT THE LEVEL. He can master 100% of a 19-phrase bank and still not be A1 —
    the bank is a starting set, not the level. These two numbers are reported SEPARATELY and the
    cap is stated out loud, because conflating them is how a language app lies to you.
  · Ladder hours are quoted as RANGES from cited sources, never averaged into one fake precise number.
  · An unmatched place yields NO target. Refusing to guess beats assigning a default.

USAGE
-----
  python3 life-lesson-level.py                     # all trips + the honest gap
  python3 life-lesson-level.py --place "Santiago"  # one place
  python3 life-lesson-level.py --selftest          # plant failures, prove RED
  python3 life-lesson-level.py --json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import date, datetime

def _seat() -> str:
    """The seat this copy is running on, derived from the script's OWN path.

    Cron has no script-args field, so path-derived identity is the only fleet-wide
    mechanism (same idiom as handoff-watcher.py). PROFILE was the literal string
    /opt/data/profiles/gentech on all four seats, so every seat read HQ's state and
    targets and would have written HQ's mastery record. Running the SHARED CORE copy is
    not a seat; it falls back to HQ, which owns the core.
    """
    parts = pathlib.Path(__file__).resolve().parts
    if "profiles" in parts:
        i = parts.index("profiles")
        if i + 1 < len(parts):
            return parts[i + 1]
    return "gentech"


SEAT = _seat()
PROFILE = pathlib.Path("/opt/data/profiles") / SEAT
SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]   # <seat>/skills/edu
SCRIPTS = SKILL_DIR / "scripts"                           # the engine lives here too
DATA = SKILL_DIR / "data"                                 # pack data — this seat's own
STATE = PROFILE / "state" / "life-lessons.json"
TARGETS = DATA / "level-targets.json"
VAULT = pathlib.Path("/opt/data/.obsidian-vault")              # the vault is shared by design
TRAVEL_DIR = VAULT / "00-HQ" / "01-Travel"
TRIPS = TRAVEL_DIR / "travel-jordan.json"   # repointed 2026-10-17; see life-lesson-engine.py for why

# ── The CEFR ladder, in cumulative guided-learning hours. ────────────────────────────────────────
# Cross-read 2026-09-24 across four independent CEFR/FSI-derived tables. Ranges are preserved
# rather than averaged: the spread IS the accuracy. A single number would be false precision.
CEFR_HOURS = {
    "A1": (90, 100),
    "A2": (180, 200),
    "B1": (350, 400),
    "B2": (500, 600),
    "C1": (700, 900),
    "C2": (1000, 1200),
}
CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
CEFR_MEANING = {
    "A1": "basic phrases, simple needs (order food, ask directions)",
    "A2": "daily interactions, directions, simple conversations",
    "B1": "travel situations handled independently; talk about experiences, simple opinions",
    "B2": "'fluent' to most people — spontaneous conversation without much strain",
    "C1": "nuanced, spontaneous, academic/professional",
    "C2": "near-native across any context",
}

# FSI puts Spanish (Cat I) at ~600-750 class hours to general professional proficiency (~B2/C1).
FSI_SPANISH_NOTE = "FSI: Spanish ≈ 600–750 class hours to professional proficiency (Category I)."


def load_pack() -> dict:
    if TARGETS.exists():
        try:
            return json.loads(TARGETS.read_text())
        except Exception as e:
            print(f"  ⚠️  level-targets.json unreadable: {e}", file=sys.stderr)
    return {"targets": [], "default": {"zone": "unknown", "target": None, "label": "No target resolved",
                                       "why": "pack file missing"}}


def resolve_target(place: str, pack: dict | None = None) -> dict:
    """Map a PLACE to the level it actually demands. Returns the pack default if nothing matches.

    Never guesses: an unmatched place gets `target: None` and says so.
    """
    pack = pack or load_pack()
    blob = re.sub(r"[-_/]+", " ", (place or "").lower())
    blob = re.sub(r"\s+", " ", blob)
    for t in pack.get("targets", []):
        for k in t.get("match", []):
            if k in blob:
                return dict(t, matched_on=k)
    return dict(pack.get("default", {"zone": "unknown", "target": None,
                                     "label": "No target resolved", "why": "no match"}))


def load_mastery() -> dict:
    """Observed practice records only. Absent file -> {}, which the caller MUST render as unmeasured."""
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def _norm(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def observed_recall(mastery: dict, bank_phrases: list[str]) -> dict | None:
    """Recall over ONLY the phrases we have actually observed. None if nothing observed.

    Deliberately excludes unobserved phrases from BOTH numerator and denominator: counting an
    unattempted phrase as a miss would manufacture a low score out of nothing.
    """
    if not mastery:
        return None
    want = {_norm(p) for p in bank_phrases}
    attempts = correct = touched = 0
    for k, v in mastery.items():
        phrase = k.split(":", 1)[1] if ":" in k else k
        if _norm(phrase) not in want:
            continue
        touched += 1
        attempts += int(v.get("attempts", 0) or 0)
        correct += int(v.get("correct", 0) or 0)
    if attempts == 0 or touched == 0:
        return None
    return {"attempts": attempts, "correct": correct, "phrases_touched": touched,
            "phrases_in_bank": len(want), "recall": correct / attempts}


def bank_coverage(mastery: dict, bank_phrases: list[str]) -> dict:
    """How much of the STARTING SET he is solid on. This is progress, NOT a level — see the cap note."""
    want = {_norm(p) for p in bank_phrases}
    solid = seen = 0
    for k, v in mastery.items():
        phrase = k.split(":", 1)[1] if ":" in k else k
        if _norm(phrase) not in want:
            continue
        seen += 1
        a, c = int(v.get("attempts", 0) or 0), int(v.get("correct", 0) or 0)
        if a > 0 and c / a >= 0.6:
            solid += 1
    return {"solid": solid, "seen": seen, "bank_size": len(want),
            "pct": round(100 * solid / len(want), 1) if want else 0.0}


def estimate(mastery: dict, bank_phrases: list[str]) -> dict:
    """An ESTIMATE of where he is, and the honest statement of what it is worth.

    The key honesty move: the phrase bank cannot certify a level. A learner who nails every phrase in
    a 19-item bank has mastered 19 phrases — that is A1 territory at best, and we say so instead of
    printing a level name he could repeat to a stranger as if it were a credential.
    """
    cov = bank_coverage(mastery, bank_phrases)
    rec = observed_recall(mastery, bank_phrases)
    if rec is None:
        return {"measured": False, "coverage": cov,
                "note": "UNMEASURED — no practice recorded yet. Not a 0%, just unknown.",
                "ceiling": None}
    return {
        "measured": True,
        "coverage": cov,
        "recall": round(rec["recall"], 3),
        "attempts": rec["attempts"],
        # The ceiling is the point: phrase-bank practice tops out well below a real level.
        "ceiling": "A1",
        "note": ("ESTIMATE ONLY. A phrase bank measures phrase recall, not a CEFR level. "
                 "100% of this bank is still a starting set — it cannot certify A2, let alone B1."),
    }


def ladder_gap(target: str | None, from_level: str | None = None) -> dict | None:
    """Ladder arithmetic: what the TARGET costs in guided hours. Not a measurement of him."""
    if not target or target not in CEFR_HOURS:
        return None
    lo, hi = CEFR_HOURS[target]
    # "from zero" is the honest default — we do not know he has A1, because we never measured it.
    return {"target": target, "from": "zero (unmeasured)", "hours_low": lo, "hours_high": hi,
            "meaning": CEFR_MEANING.get(target, ""),
            "at_1h_day_weeks": (round(lo / 7), round(hi / 7)),
            "at_2h_day_weeks": (round(lo / 14), round(hi / 14)),
            "note": "Guided-learning hours from the CEFR ladder, cumulative from zero. "
                    "Immersion and prior Spanish shorten this; nothing here is a promise."}


def render(trips: list[dict], mastery: dict, pack: dict) -> str:
    lines = ["🎯 EDU — LEVEL CHECK: how good do you actually need to be?", ""]
    for t in trips:
        place = t.get("place") or t.get("name", "")
        r = resolve_target(place, pack)
        lines.append(f"📍 {place}")
        if not r.get("target"):
            lines.append(f"   ⚠️  {r.get('label')} — {r.get('why')}")
            lines.append("")
            continue
        lines.append(f"   target: {r['target']} — {r.get('label')}")
        lines.append(f"   why: {r.get('why')}")
        g = ladder_gap(r["target"])
        if g:
            lines.append(f"   cost from zero: ~{g['hours_low']}–{g['hours_high']} guided hrs "
                         f"(≈ {g['at_1h_day_weeks'][0]}–{g['at_1h_day_weeks'][1]} wks at 1 h/day)")
        lines.append("")
    est = estimate(mastery, BANK_ALL)
    lines.append("📊 Where you are right now")
    lines.append(f"   {est['note']}")
    if est["measured"]:
        c = est["coverage"]
        lines.append(f"   bank coverage: {c['solid']}/{c['bank_size']} solid ({c['pct']}%), "
                     f"recall {est['recall']}")
    else:
        lines.append(f"   bank coverage: {est['coverage']['solid']}/{est['coverage']['bank_size']} "
                     "(nothing practised yet)")
    lines.append("")
    lines.append("⚠️  The bank is a STARTING SET, not the level. Mastering all of it does not make you B1.")
    lines.append(f"ℹ️  {FSI_SPANISH_NOTE}")
    return "\n".join(lines)


# ── Load the phrase bank from the engine, so the two can never drift apart. ──────────────────────
def _load_bank() -> list[str]:
    """Read the bank OUT of the engine rather than duplicating it.

    A copy of the phrase list here would silently drift the moment a phrase is added to the engine,
    and the level check would then measure against a bank that no longer exists. Import the engine.
    """
    sys.path.insert(0, str(SCRIPTS))
    try:
        import importlib
        eng = importlib.import_module("life-lesson-engine")
        out = []
        for dialect, sits in eng.PHRASES.items():
            for sit, rows in sits.items():
                for row in rows:
                    out.append(row[0])
        return out
    except Exception as e:
        print(f"  ⚠️  could not read the phrase bank from the engine: {e}", file=sys.stderr)
        return []


BANK_ALL = _load_bank()


def load_trips() -> list[dict]:
    out: list[dict] = []
    if TRIPS.exists():
        try:
            d = json.loads(TRIPS.read_text())
            t = d.get("trip") or {}
            if t:
                out.append({"name": t.get("name", "?"), "place": t.get("homeBase", "")})
        except Exception:
            pass
    for ph in sorted(TRAVEL_DIR.glob("*/price-history.md")):
        city = ph.parent.name
        if city == "fx":
            continue
        out.append({"name": f"{city} (tracked route)", "place": city.replace("-", " ")})
    return out


def selftest() -> int:
    print("SELFTEST — planting failures, expecting loud RED\n")
    ok = True
    pack = load_pack()

    # 1. NO practice recorded must read as UNMEASURED — not 0%, and not a default level.
    e = estimate({}, BANK_ALL)
    if not e["measured"] and "UNMEASURED" in e["note"]:
        print("  ✅ RED 1: no practice -> UNMEASURED (never a fabricated 0% or a default 'A1')")
    else:
        print("  ❌ FAIL 1: invented a measurement from no data"); ok = False

    # 2. THE CORE REQUIREMENT: the same dialect must yield DIFFERENT targets by place.
    sosua = resolve_target("Sosúa", pack)
    sdq = resolve_target("Santo Domingo", pack)
    if sosua.get("target") == "A1" and sdq.get("target") == "B1":
        print(f"  ✅ RED 2: place decides the target — Sosúa {sosua['target']} vs Santo Domingo {sdq['target']}")
    else:
        print(f"  ❌ FAIL 2: place did not change the target — {sosua.get('target')}/{sdq.get('target')}")
        ok = False

    # 3. Cibao cities resolve too (his own list: Santiago).
    sti = resolve_target("Santiago de los Caballeros", pack)
    if sti.get("target") == "B1":
        print("  ✅ RED 3: Santiago (Cibao) resolves to B1 — the cities he named are covered")
    else:
        print(f"  ❌ FAIL 3: Santiago unresolved — got {sti.get('target')}"); ok = False

    # 4. An unknown place must NOT get a guessed target.
    unk = resolve_target("Somewhere Unlisted", pack)
    if unk.get("target") is None:
        print("  ✅ RED 4: an unmatched place gets NO target (refuses to guess a default)")
    else:
        print(f"  ❌ FAIL 4: guessed a target for an unknown place — {unk.get('target')}"); ok = False

    # 5. THE LYING CASE. Full bank mastery must NOT be reported as a level above A1.
    fake = {}
    for p in BANK_ALL:
        fake[f"es-DO:{p}"] = {"attempts": 10, "correct": 10}
    e = estimate(fake, BANK_ALL)
    if e["measured"] and e["ceiling"] == "A1" and "cannot certify" in e["note"]:
        print("  ✅ RED 5: 100% bank mastery still caps at A1 — the bank is not the level")
    else:
        print(f"  ❌ FAIL 5: bank mastery inflated into a level — {e.get('ceiling')}"); ok = False

    # 6. Unattempted phrases must NOT count as misses (that manufactures a low score).
    half = {f"es-DO:{BANK_ALL[0]}": {"attempts": 4, "correct": 4}}
    r = observed_recall(half, BANK_ALL)
    if r and r["recall"] == 1.0:
        print("  ✅ RED 6: an unattempted phrase is excluded, not counted as a miss")
    else:
        print(f"  ❌ FAIL 6: unattempted phrases polluted recall — {r}"); ok = False

    # 7. Ladder hours must stay a RANGE (a single number would be false precision).
    g = ladder_gap("B1")
    if g and g["hours_low"] != g["hours_high"]:
        print(f"  ✅ RED 7: ladder quoted as a range ({g['hours_low']}–{g['hours_high']} h), not false precision")
    else:
        print("  ❌ FAIL 7: ladder collapsed to a single number"); ok = False

    # 8. INTEGRATION: the bank must come from the ENGINE, so the two cannot drift.
    if BANK_ALL and len(BANK_ALL) >= 15:
        print(f"  ✅ RED 8: phrase bank read from the engine itself ({len(BANK_ALL)} phrases) — no copy to drift")
    else:
        print(f"  ❌ FAIL 8: could not read the engine bank (got {len(BANK_ALL)})"); ok = False

    print("\n" + ("SELFTEST PASSED — all eight planted failures went RED"
                  if ok else "SELFTEST FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--place")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    pack = load_pack()
    mastery = load_mastery()
    trips = [{"name": a.place, "place": a.place}] if a.place else load_trips()

    if a.json:
        out = []
        for t in trips:
            place = t.get("place") or t.get("name", "")
            r = resolve_target(place, pack)
            out.append({"place": place, "target": r.get("target"), "zone": r.get("zone"),
                        "label": r.get("label"), "gap": ladder_gap(r.get("target"))})
        print(json.dumps({"trips": out, "estimate": estimate(mastery, BANK_ALL),
                          "generated": datetime.utcnow().isoformat(timespec="seconds")},
                         ensure_ascii=False, indent=2))
        return 0
    print(render(trips, mastery, pack))
    return 0


if __name__ == "__main__":
    sys.exit(main())
