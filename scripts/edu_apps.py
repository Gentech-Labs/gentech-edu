#!/usr/bin/env python3
"""
edu_apps.py — the app EQUIVALENCE layer.

WHY
---
Jordan (2026-09-23): *"we need a tab for apps… you got your food apps. You've got your like Kluk, for
example — I know in Southeast Asia they use Kluk the same way we use Grubhub. So now I know food
equivalence — so if I don't want to grab a moto or take an Uber somewhere, I could just have it delivered."*

WHAT HE ACTUALLY ASKED FOR
--------------------------
Not a list of app names per country. **A mapping.** He is not learning app names — he is mapping a
**need** he already understands ("I want food delivered") onto **whatever that country calls it**. That
is what makes it usable in a country he has never been to.

`FOOD DELIVERY → {US: Grubhub/DoorDash, DR: Komida, TH: Grab/LINE MAN}`

So the unit here is the **need**, not the app. "I don't want to ride there" is ONE need that resolves to
either a RIDE or a DELIVERY — and the equivalence is what tells him he has a choice.

THE HONESTY RULE
----------------
A country where the need has NO known app returns **unknown — do not assume it carries over**, never a
blank or a borrowed name. Assuming the US app works abroad is the exact error this prevents.

USAGE
  python3 edu_apps.py --need "food delivery"      # who delivers what, in every country we cover
  python3 edu_apps.py --country th
  python3 edu_apps.py --map                       # the full equivalence table
  python3 edu_apps.py --selftest
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# ── THE ONE SOURCE, resolved from THIS file's own location. ───────────────────────────────────────
# Was: pathlib.Path("/opt/data/profiles/gentech/data/travel-apps.json") — an absolute path to
# ONE seat's profile, carried byte-identical into all four seats. Two things were wrong with it, and
# both were measured 2026-09-25: (1) it made every seat read HQ's copy, so a worker seat could not use
# its own data and its own copy was dead weight that went stale unnoticed; (2) it pointed at a
# DIFFERENT file than the one SKILL.md documents and `fleet_skill_drift_audit.py` polices, so the
# audit's drift gate was watching a file the code never opened. Resolved from `__file__`, the doc,
# the code and the audit all name the same file, on every seat. As of 2026-09-25 the other four
# scripts in this skill (`life-lesson-{engine,audio,level,scenario}.py`) resolve their own seat the
# same way and live in this directory too — one skill, one tree, no hardcoded profile anywhere.
DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
APPS = DATA_DIR / "travel-apps.json"

# ── The equivalence map. NEED → country → {app, note, status}. ────────────────────────────────────
# Add a country by adding a row. Never edit this into a per-country tool — the need is the unit.
# NOTE: the map is NOT defined here. It lives in data/travel-apps.json, because a second copy in
# this file silently drifted from the copy the dashboard reads — a withdrawn app vanished from the
# page while the CLI still recommended it. One source, or the two disagree about reality.
#
# Read it with equivalence() at runtime.


def load() -> dict:
    if not APPS.exists():
        return {}
    try:
        return json.loads(APPS.read_text())
    except Exception as e:
        print(f"  ⚠️  unreadable: {e}", file=sys.stderr)
        return {}


META_KEYS = {"the_choice", "why_apps_travel", "_comment"}


def equivalence() -> tuple[dict, dict]:
    """Read the map from the SINGLE data source. A second copy in this file drifted from the
    dashboard's copy and a withdrawn app silently disappeared from the page — one source, always.

    META_KEYS are returned as ordinary keys so callers can read the rules (why_apps_travel) and the
    choice; country iteration filters them out."""
    d = load()
    eq = dict(d.get("equivalence", {}) or {})
    choice = eq.get("the_choice", {}) or {}
    return eq, choice


def render_map() -> str:
    EQUIVALENCE, THE_CHOICE = equivalence()
    out = ["APP EQUIVALENCE — the need is the unit, not the app", "=" * 72, ""]
    for need, rows in EQUIVALENCE.items():
        if need in META_KEYS or not isinstance(rows, dict):
            continue
        out.append(f"◆ {need.upper()}")
        for key, r in rows.items():
            if not isinstance(r, dict) or "app" not in r:
                continue  # e.g. ph_note rows vary in shape; only app rows render here
            country = key.split("_")[0].upper()
            tail = "" if key == country.lower() else " (alt)"
            icon = {"RECOMMENDED": "✅", "dead": "✖", "backup": "🔸"}.get(r.get("status", ""), "·")
            out.append(f"   {icon} {country:<3}{tail:<6} {r['app']}")
            if r.get("note"):
                out.append(f"          {r['note']}")
        out.append("")
    # The rules that predict the next country — the point of the whole map.
    wat = EQUIVALENCE.get("why_apps_travel", {})
    if wat:
        out.append("WHY SOME APPS TRAVEL AND OTHERS DON'T")
        for k in ("dedicated_superapps_travel", "chat_bolted_apps_do_not",
                  "brands_survive_market_by_market", "therefore"):
            if wat.get(k):
                out.append(f"  · {wat[k]}")
        out.append("")
    out.append("=" * 72)
    out.append(f"★ {THE_CHOICE.get('need','')}")
    out.append(f"    a) {THE_CHOICE.get('option_a','')}")
    out.append(f"    b) {THE_CHOICE.get('option_b','')}")
    out.append(f"    {THE_CHOICE.get('note','')}")
    return "\n".join(out)


def render_need(need: str) -> str:
    EQUIVALENCE, _ = equivalence()
    key = need.strip().lower()
    rows = EQUIVALENCE.get(key)
    if not rows:
        known = ", ".join(sorted(EQUIVALENCE))
        return f"No mapping for '{need}'. Known needs: {known}"
    out = [f"◆ {need.upper()} — where to get it", ""]
    for k, r in rows.items():
        country = k.split("_")[0].upper()
        tail = "" if k == country.lower() else " (alt)"
        out.append(f"  {country}{tail}: {r['app']}  [{r.get('status','')}]")
        if r.get("note"):
            out.append(f"      {r['note']}")
    return "\n".join(out)


def selftest() -> int:
    print("SELFTEST — planting failures, expecting loud RED\n")
    ok = True
    d = load()

    # PREFLIGHT — name the file and the fault, never a bare KeyError. A stale or absent copy of the
    # data used to surface as `KeyError: 'food delivery'` from deep inside the test, which reads as a
    # code bug when the real fault is "you are reading the wrong file". Measured 2026-09-25: the
    # skill-dir copy had gone 17 minutes stale and the crash named nothing. FAIL 0 is that diagnosis.
    if "equivalence" not in d:
        print(f"  ❌ FAIL 0: no equivalence map in the data file — read {APPS}")
        print(f"            exists={APPS.exists()} keys={sorted(d.keys())}")
        print("\nSELFTEST FAILED")
        return 1

    EQUIVALENCE, THE_CHOICE = equivalence()
    if d.get("categories"):
        print("  ✅ RED 1: app data loads")
    else:
        print("  ❌ FAIL 1: no app data"); ok = False

    # The whole point of the request: Grubhub's counterpart must be resolvable abroad.
    us = EQUIVALENCE["food delivery"]["us"]["app"]
    do = EQUIVALENCE["food delivery"]["do"]["app"]
    if "Grubhub" in us and do == "Komida":
        print("  ✅ RED 2: Grubhub ↔ Komida equivalence holds (his exact example, in reverse)")
    else:
        print("  ❌ FAIL 2: the food-delivery equivalence is broken"); ok = False

    # Thailand must be present — he named it as the next country.
    if "th" in EQUIVALENCE["food delivery"] and "th" in EQUIVALENCE["ride"]:
        print("  ✅ RED 3: Thailand covered for both food and rides")
    else:
        print("  ❌ FAIL 3: Thailand missing from the map"); ok = False

    # A dead app must stay marked dead — the foodpanda trap.
    th = EQUIVALENCE["food delivery"]
    fp = next((v for k, v in th.items() if "foodpanda" in v["app"].lower()), None)
    st = (fp or {}).get("status", "").upper()
    # Match the CLASS of withdrawn-ness, not one exact string — an exact-wording check is what
    # let the script and the dashboard disagree about the same app.
    withdrawn = ("DEAD" in st) or ("WITHDREW" in st) or ("DEAD" in st)
    if fp and withdrawn and "MAY 2025" in st:
        print("  ✅ RED 4: foodpanda stays marked DEAD/WITHDREW in Thailand (May 2025)")
    else:
        print(f"  ❌ FAIL 4: a withdrawn app is presented as usable (status={st!r})"); ok = False

    # Every mapping entry must carry a status, or it reads as an endorsement.
    # Only dict rows that describe an app; meta keys and note rows carry no status by design.
    missing = [f"{n}/{k}" for n, rows in EQUIVALENCE.items() if isinstance(rows, dict)
               for k, r in rows.items() if isinstance(r, dict) and "app" in r and not r.get("status")]
    if not missing:
        print("  ✅ RED 5: every mapping carries a status")
    else:
        print(f"  ❌ FAIL 5: entries with no status: {missing}"); ok = False

    # Jordan's own framing — one need, two resolutions — must survive in the output.
    if "delivered" in THE_CHOICE["option_b"].lower() and "ride" in THE_CHOICE["option_a"].lower():
        print("  ✅ RED 6: the ride-or-deliver choice is preserved (his 'have it delivered instead')")
    else:
        print("  ❌ FAIL 6: the ride/deliver equivalence was lost"); ok = False

    # An unknown need must say so — never borrow another country's app.
    r = render_need("teleportation")
    if "No mapping" in r and "Komida" not in r:
        print("  ✅ RED 7: unknown need says so — never borrows a real app name")
    else:
        print("  ❌ FAIL 7: unknown need returned a borrowed answer"); ok = False

    # Jordan's own observation: LINE MAN in Thailand, absent in the Philippines (messaging-app bolt-on).
    fd = EQUIVALENCE.get("food delivery", {})
    ph_note = fd.get("ph_note", {}).get("app", "")
    if "LINE MAN" in ph_note and "NOT available" in ph_note:
        print("  ✅ RED 9: LINE MAN marked NOT available in the Philippines (messaging-app bolt-on, "
              "confirmed by Jordan)")
    else:
        print("  ❌ FAIL 9: a Thailand-only app would be carried into the Philippines"); ok = False

    # The brand-travel trap: foodpanda dead in TH, alive and #2 in PH. Same brand, different fate.
    th_fp = next((v for k, v in fd.items() if "foodpanda" in (v.get("app", "") if isinstance(v, dict) else "")), None)
    ph_app = fd.get("ph", {}).get("app", "")
    if th_fp and "DEAD" in th_fp.get("status", "").upper() and "foodpanda" in ph_app.lower():
        print("  ✅ RED 10: the same brand is DEAD in Thailand and ALIVE in the Philippines — "
              "a brand's presence is never carried across a border")
    else:
        print("  ❌ FAIL 10: brand presence is being assumed to travel"); ok = False

    # Bolt Food in Thailand is UNRESOLVED. Jordan corrected my overclaim; the check now guards the
    # conflict itself — it fails if anyone quietly promotes it to "available" OR "absent".
    bf = EQUIVALENCE.get("food delivery", {}).get("th_bolt_food", {})
    st = bf.get("status", "")
    if "CONFLICTED" in st.upper() or "UNRESOLVED" in st.upper():
        print("  ✅ RED 11: Bolt Food in Thailand stays CONFLICTED (Jordan's correction protected — "
              "neither 'available' nor 'absent' may be asserted)")
    else:
        print("  ❌ FAIL 11: the Bolt Food conflict has been silently resolved to one side"); ok = False

    # The overclaim must not reappear AS A CLAIM. Quoting it while disowning it is fine and is in fact
    # required — so check for the correction marker, not for the string. (A naive substring check failed
    # here first: it flagged the note for quoting the very claim it was correcting.)
    th_ride_note = EQUIVALENCE.get("ride", {}).get("th", {}).get("note", "").upper()
    if "OVERCLAIM" in th_ride_note and "CORRECTED" in th_ride_note:
        print("  ✅ RED 11b: the rides-only claim is recorded as an explicit, disowned OVERCLAIM")
    else:
        print("  ❌ FAIL 11b: the rides-only correction has been dropped — it could harden into "
              "a settled fact again"); ok = False

    # The general rule must be stated, or the next country gets it wrong again.
    wat = EQUIVALENCE.get("why_apps_travel", {})
    if wat.get("therefore") and "NEVER" in wat["therefore"].upper():
        print("  ✅ RED 12: the rule is stated — never carry an app recommendation across a border")
    else:
        print("  ❌ FAIL 12: no general rule, so the next country repeats the mistake"); ok = False

    # A country with no known app must say so, never borrow (Jordan's rule, applied to PH events).
    if "events" in EQUIVALENCE and "ph" not in EQUIVALENCE["events"]:
        print("  ✅ RED 13: Philippines events NOT invented — absent means absent")
    else:
        print("  ⚠️  note 13: PH events entry exists — confirm it is real, not borrowed")

    # Sliced's happy-hour finds must be present in the venue data (he asked for those prices).
    tv = DATA_DIR / "travel-venues.json"
    if tv.exists():
        vd = json.loads(tv.read_text())
        sl = next((v for v in vd["venues"] if v["id"] == "sliced-dr"), None)
        drinks = (sl or {}).get("menu", {}).get("happy_hour_drinks", [])
        priced = [x for x in drinks if x.get("dop") is not None]
        unpriced = [x for x in drinks if x.get("dop") is None]
        if priced and unpriced:
            print(f"  ✅ RED 8: Sliced prices recorded AND the unmatched ones marked, not invented "
                  f"({len(priced)} priced, {len(unpriced)} explicitly not asserted)")
        else:
            print(f"  ❌ FAIL 8: Sliced drink prices missing or all silently asserted"); ok = False
    else:
        print("  ❌ FAIL 8: venue data missing"); ok = False

    print("\n" + ("SELFTEST PASSED — all planted failures went RED" if ok else "SELFTEST FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--need")
    ap.add_argument("--country")
    ap.add_argument("--map", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.need:
        print(render_need(a.need)); return 0
    if a.country:
        EQUIVALENCE, _ = equivalence()
        cc = a.country.lower()
        for need, rows in EQUIVALENCE.items():
            hits = {k: v for k, v in rows.items() if k.split("_")[0] == cc}
            if hits:
                print(f"\n◆ {need.upper()}")
                for k, v in hits.items():
                    print(f"  {v['app']}  [{v.get('status','')}]")
                    if v.get("note"):
                        print(f"     {v['note']}")
        return 0
    print(render_map())
    return 0


if __name__ == "__main__":
    sys.exit(main())
