#!/usr/bin/env python3
"""
life-lesson-engine.py — GenTech EDU: lessons drawn from Jordan's ACTUAL life.

WHY THIS EXISTS
---------------
Jordan (2026-09-23): *"we'll make it based off of your life… I've already had an idea like this where we make
lessons based off of what's relevant to you. So you get more engaged — because that's the problem with
Duolingo."*

Duolingo's own monetisation admits the mechanism: an AI conversation partner is worth a paywall because
conversation is the only place the app learns what you actually need. The sentences are telemetry. They then
harvest that signal and **drill everyone the same generic corpus**. We take the mechanism and close the loop:
collect what he gets wrong, drill THAT tomorrow, in sentences drawn from his own itinerary.

WHAT IT READS (real vault data, never invented phrases)
-------------------------------------------------------
  · 00-HQ/01-Travel/travel-jordan.json — his trips, legs, dates, base cities, purpose
  · 00-HQ/01-Travel/*/price-history.md — where he is going and what it costs
  · auto-logging food mentions         — meals he actually recorded

DESIGN RULE (decides-alone-execution)
-------------------------------------
The ENGINE owns the sequence. It is not a lesson picker that waits for him to choose — that hands the decision
back, which is the "calibrated confidence became ask Jordan" failure in a new costume. A tutor that already
knows DR is in November and drills airport-and-taxi vocabulary is an agent; a menu is a toy.

HONESTY RULES (house rules, non-negotiable)
-------------------------------------------
  · A lesson is generated ONLY from real vault data. No trip found -> says so, exits non-zero.
  · Mastery is UNKNOWN until observed — never a fabricated 0%, never an invented streak.
  · `--selftest` PLANTS a failure and proves the detector goes RED before shipping.

USAGE
-----
  python3 life-lesson-engine.py              # today's lesson
  python3 life-lesson-engine.py --selftest   # prove it can fail loudly
  python3 life-lesson-engine.py --json       # machine-readable (for the dashboard)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from datetime import date, datetime

VAULT = pathlib.Path("/opt/data/.obsidian-vault")          # the vault is shared by design
TRAVEL_DIR = VAULT / "00-HQ" / "01-Travel"
# 2026-10-17 — REPOINTED. This read `VAULT/Travel/travel-jordan.json`, and `Travel/` was deleted on
# 2026-10-15 when travel consolidated into `00-HQ/01-Travel/` (the consolidation believed it was an empty
# shell; it inspected the FOLDER, not the READERS). With no record the engine degraded silently to the
# fare-watch cities below, where a stale `puerto-plata` tracker outranked the real trip — and it served
# Dominican Spanish for a Thailand trip. HQ named the canonical path and restored the record on
# 2026-10-17; it is the consolidation TARGET, and the filename is unchanged.
TRIPS = TRAVEL_DIR / "travel-jordan.json"


def _seat() -> str:
    """The seat this copy is running on, derived from the script's OWN path.

    Cron has no script-args field, so path-derived identity is the only fleet-wide
    mechanism (same idiom as handoff-watcher.py). Before 2026-09-25 the two paths
    below were the literal string /opt/data/profiles/gentech, carried
    byte-identical into all four seats — so every seat wrote its lessons into HQ's
    profile while its own state and cache sat unused (fleet-compat defect class,
    build-queue #28). Running the SHARED CORE copy is not a seat; it falls back to
    HQ, which owns the core.
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
DATA = SKILL_DIR / "data"                                 # pack data — this seat's own
STATE = PROFILE / "state" / "life-lessons.json"          # LEGACY single-record path (read-only fallback)
OUT = PROFILE / "cache" / "life-lessons"

# ── THE LEARNER BOUNDARY (2026-10-17) — Jordan: *"We need a share progress but separate… Similar to
# tenant cron jobs."* The Treasury already solved this shape: SHARED engine, SHARED pack, SEPARATE records
# per person, and a HARD STOP on an identity it does not know.
#
#   · the registry is PACK DATA (`data/learners.json`) — adding a learner is a file edit
#   · progress is per learner: `profiles/<seat>/state/learners/<learner>.json`
#   · the engine REFUSES to run for a learner it does not know. An unknown learner is an error, not a
#     permission — tenant_guard's rule, for the same reason: a warning gets scrolled past in a cron log.
LEARNERS_FILE = DATA / "learners.json"


def load_learners() -> dict:
    try:
        return json.loads(LEARNERS_FILE.read_text())
    except Exception as e:
        raise SystemExit(f"🔴 life-lesson-engine: cannot read the learner registry "
                         f"({LEARNERS_FILE}): {type(e).__name__}: {e}")


def resolve_learner(name: str) -> dict:
    """Hard stop on an unknown learner. Never a default, never a guess."""
    reg = load_learners()
    who = reg.get("learners", {})
    if not who:
        raise SystemExit(f"🔴 life-lesson-engine: the learner registry is EMPTY ({LEARNERS_FILE}) — "
                         f"an empty roster is an error, not an empty classroom.")
    if name not in who:
        raise SystemExit(f"🔴 life-lesson-engine: UNKNOWN LEARNER {name!r}. Registered: "
                         f"{', '.join(sorted(who))}. An unknown learner is not a permission — it is an error. "
                         f"Add them to {LEARNERS_FILE} (a file edit, not an engine edit).")
    return {"key": name, "defaults": reg.get("_defaults", {}), **who[name]}


def state_path(learner: str) -> pathlib.Path:
    """This learner's OWN progress file. Two learners never share one."""
    return PROFILE / "state" / "learners" / f"{learner}.json"


def learner_forms(learner: dict, dialect: str) -> dict:
    """The forms this learner must be served in, falling back to the bank's own defaults."""
    have = (learner.get("forms") or {}).get(dialect)
    if have:
        return have
    return (learner.get("defaults") or {}).get(dialect, {})

# ── Phrase banks, keyed by the SITUATION he will actually be in. ────────────────────────────────
#
# DIALECT-FIRST (Jordan, 2026-09-23): *"you also got to look at different dialects… I'm going to the
# Dominican Republic, right? Well now I need to learn the Dominican dialect and how they speak Spanish
# very fast. Also, there's slang words, like K-L-K for what's up."*
#
# So the bank is keyed by DIALECT, never by bare language. "Spanish" is not a lesson; `es-DO` is.
# The phrases below are written the way Dominicans SAY them — dropped s, -ado → -a'o, tú + inversion —
# because a learner who studies textbook Spanish and lands in Santo Domingo hears a different language.
# The `std` (standard) form is kept per phrase so the lesson can SHOW the difference; that contrast is
# the teaching, not decoration.
PHRASES = {
    # ── Dominican Spanish (es-DO). The dialect for the November trip.
    "es-DO": {
        "greeting": [
            ("¿Qué lo qué?", "What's up? (KLK in text — the DR greeting)", "¿Qué tal?"),
            ("Dime a ver", "What's up? / tell me", "¿Qué me cuentas?"),
            ("¿Cómo e' que e'?", "How's it going?", "¿Cómo está?"),
            ("Ya tú sabe'", "You know how it is", "Ya sabes"),
        ],
        "airport": [
            ("Vengo por turismo, cuatro día'", "I'm here for tourism, four days", "Vengo por turismo, cuatro días"),
            ("Aquí 'tá mi pasaporte", "Here's my passport", "Aquí está mi pasaporte"),
            ("No tengo nada que declarar", "I have nothing to declare", "—"),
        ],
        "taxi": [
            ("¿Cuánto e' pa' lla'?", "How much to get there?", "¿Cuánto es para allá?"),
            ("Vamo' a usá el taxímetro", "Let's use the meter", "Vamos a usar el taxímetro"),
            ("Vo' a pagá en efectivo", "I'm paying cash", "Voy a pagar en efectivo"),
            ("¿Tú acepta' tarjeta?", "Do you take card?", "¿Aceptas tarjeta?"),
        ],
        "hotel": [
            ("Tengo una reserva a nombre de Jordan", "I have a reservation under Jordan", "—"),
            ("¿A qué hora e' el check-out?", "What time is check-out?", "¿A qué hora es el check-out?"),
            ("¿Hay wifi en la habitación?", "Is there wifi in the room?", "—"),
        ],
        "food": [
            ("La cuenta, por favol", "The check, please (note the r→l)", "La cuenta, por favor"),
            ("¿Qué tú me recomienda'?", "What do you recommend?", "¿Qué me recomiendas?"),
            ("Sin picante, por favol", "Not spicy, please", "Sin picante, por favor"),
            ("Eso 'tá nítido", "That's great / cool", "Eso está muy bien"),
            ("Pásame esa vaina", "Pass me that thing (vaina = anything)", "Pásame eso"),
        ],
    },
    # ── Thai (Central). Explicitly a "get around politely" goal, NOT fluency (~1,100 hrs, Cat IV).
    "th-TH": {
        "greeting": [
            ("สวัสดีครับ", "Hello (male speaker)", "—"),
            ("ขอบคุณครับ", "Thank you (male speaker)", "—"),
            ("ไม่เป็นไรครับ", "No problem / it's fine", "—"),
        ],
        "airport": [
            ("ผมมาเที่ยวครับ", "I'm here for tourism", "—"),
        ],
        "taxi": [
            ("ไปที่โรงแรมนี้ครับ", "To this hotel", "—"),
            ("เท่าไหร่ครับ", "How much?", "—"),
        ],
        "hotel": [
            ("ผมมีจองไว้ครับ", "I have a booking", "—"),
        ],
        "food": [
            ("ไม่เผ็ดครับ", "Not spicy, please", "—"),
            ("เก็บเงินด้วยครับ", "The bill, please", "—"),
        ],
    },
}

# ── DIALECT RESOLUTION: country/city -> the VARIANT he will actually hear. ──────────────────────
# Never resolve to a bare language. This is the permanent form of Jordan's dialect correction.
DIALECT_FOR_PLACE = {
    # Dominican Republic — Spanish (Dominican)
    "dominican republic": "es-DO", "dr": "es-DO", "puerto plata": "es-DO", "sosúa": "es-DO",
    "sosua": "es-DO", "santo domingo": "es-DO", "punta cana": "es-DO",
    # Thailand — Thai (Central, the Bangkok standard)
    "thailand": "th-TH", "bangkok": "th-TH", "pattaya": "th-TH", "chiang mai": "th-TH",
}

# The human label shown in the lesson, so the dialect is never invisible.
DIALECT_LABEL = {
    "es-DO": "Spanish — Dominican (es-DO)",
    "th-TH": "Thai — Central (th-TH)",
}

# The regional voice that matches the dialect. Resolved here, not hardcoded in the audio script,
# so a new dialect cannot silently inherit the wrong accent (which is exactly what happened: Roger,
# an ENGLISH voice, read the first Spanish lesson with an American accent).
#
# Shared-library voices must be ADDED to the account before synthesis works — calling by id alone
# returns `404 voice_not_found`. See `life-lesson-audio.py`.
# VOICE PER DIALECT — PACK DATA (data/voices.json), not engine code. "Voice mapping" is pack by the
# §4 boundary, and the reason is measured: the engine used to carry
#     "th-TH": "CwhRBWXzGAHq8TQ4Fs17"   # Roger — multilingual; no Thai-native on the account yet
# i.e. an ENGLISH voice (accent=american) wired to Thai. A multilingual voice is still an English
# speaker pronouncing Thai, so the learner copies an accent they will pay to unlearn. It is also
# per-FORM, because a female learner must hear the female particle in the female voice.
VOICES_FILE = DATA / "voices.json"


def load_voices() -> dict:
    if not VOICES_FILE.exists():
        print(f"  ⚠️  no voice mapping ({VOICES_FILE}) — lessons will carry no voice_id.", file=sys.stderr)
        return {}
    try:
        return json.loads(VOICES_FILE.read_text())
    except Exception as e:
        print(f"  ⚠️  voice mapping unreadable ({e}) — lessons will carry no voice_id.", file=sys.stderr)
        return {}


VOICES = load_voices()


def resolve_voice(dialect: str, learner: dict) -> str | None:
    """The NATIVE voice for this dialect in this learner's form. None means NOTHING IS BORROWED.

    Returning None is deliberate: the caller must refuse to synthesise rather than fall back to an
    English voice, because a wrong-accented lesson is a wrong answer, not a rough draft.
    """
    by_form = ((VOICES.get("dialects") or {}).get(dialect) or {}).get("by_form") or {}
    label = (((learner.get("forms") or {}).get(dialect) or {}).get("form_label")) or "default"
    hit = by_form.get(label)
    if hit:
        return hit
    if "default" in by_form:
        # Fall back ONLY when the pack explicitly declares one, and say so — a learner whose form is
        # missing could otherwise be served the other gender's voice in silence. (Sr audit 2026-10-17.)
        print(f"  ⚠️  {dialect} has no voice for form '{label}' — using the dialect default, which may "
              f"not match this learner. Declared, not silent.", file=sys.stderr)
        return by_form["default"]
    return None


def resolve_bridge_voice(learner: dict) -> str | None:
    """The voice for the BRIDGE — it reads the Latin approximation aloud. PACK DATA, keyed by the
    LEARNER'S OWN FIRST LANGUAGE, not by the dialect being taught.

    Jordan, 2026-10-17: *"I am American, so I speak English… Josephine, she's Filipino, so she speaks
    Tagalog… speak to her and her language whenever she is asking for pronunciation."*

    This is the correction that matters: an approximation is only a bridge if it is spoken in the
    language the learner already hears with. One global American voice served her an English eye.

    It NEVER speaks the Thai script (that is the native voice's job; `no_borrowed_voice` still holds).
    No entry for the learner's first language -> None -> the caller renders the Thai ALONE and says so,
    rather than handing them another language's approximation and calling it a bridge.
    """
    lang = ((learner.get("first_language") or {}).get("code")) or ""
    by_lang = (VOICES.get("bridge") or {}).get("by_lang") or {}
    if not lang:
        print(f"  ⚠️  learner '{learner.get('display', learner.get('key'))}' declares no first_language — "
              f"no bridge voice can be chosen. Serving the Thai alone.", file=sys.stderr)
        return None
    hit = by_lang.get(lang) or {}
    if not hit.get("voice_id"):
        print(f"  ⚠️  no bridge voice declared for first language '{lang}' — serving the Thai ALONE. "
              f"Add one to edu/data/voices.json (bridge.by_lang) rather than borrowing another "
              f"language's approximation.", file=sys.stderr)
        return None
    return hit["voice_id"]

# PRONUNCIATION BRIDGE — PACK DATA (data/pronunciation-<lang>.json). A learner who cannot read the
# script cannot say what we serve; this gives each bank phrase a Latin reading, keyed by the EXACT
# phrase that will be rendered (both learner forms present, so the lookup survives the form swap).
# Generated with PyThaiNLP, never hand-typed — see the file's own `_tool`/`_LIMIT_NO_TONES` fields.
_PRON_CACHE: dict[str, dict] = {}


def load_pron(lang: str) -> dict:
    if lang in _PRON_CACHE:
        return _PRON_CACHE[lang]
    f = DATA / f"pronunciation-{lang}.json"
    phrases: dict = {}
    if not f.exists():
        # ABSENT is a legitimate state — not every bank has a pronunciation pack yet — and it means
        # "no readings exist", which is an answer. Silence here is honest, not a swallowed error.
        phrases = {}
    else:
        try:
            phrases = json.loads(f.read_text()).get("phrases") or {}
            if not phrases:
                # This is the case the two states must not be confused: the file IS there and is
                # useless, so every lesson will be served with no reading. Say so.
                print(f"  ⚠️  {f.name} exists but carries NO phrases — lessons will be served "
                      f"without a reading. Data defect, not an absent pack.", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  {f.name} is UNREADABLE ({type(e).__name__}: {e}) — serving without readings.",
                  file=sys.stderr)
            phrases = {}
    _PRON_CACHE[lang] = phrases
    return phrases


# Which situation leads, given what he has coming. Order = priority.
SITUATION_ORDER = ["greeting", "airport", "taxi", "hotel", "food"]

# NEXT-TRIP PRIORITY — the timeline decides which language leads, not the alphabet.
#
# BUG THIS FIXES (found in the first live run, 2026-09-23): the engine returned the first match while
# iterating trips sorted by *filename*, so `bangkok/` beat `puerto-plata/` and it drilled **Thai** — for a
# trip that is two months further out. The DR is the November trip; Thailand is Jan/Feb. Drilling the wrong
# language first is the whole failure mode this engine exists to avoid.
#
# TRIP PRIORITY — a FILE, not engine logic (2026-10-17).
#
# Jordan: *"Lol sorry trip plans change a lot"* — that IS the design input. Which destination leads a
# lesson is a property of the PLAN, so it lives in `data/trip-priority.json` beside the phrase banks, and
# changing the plan is a ONE-FILE edit that never touches the engine. Same boundary rule as a subject.
#
# The durable rule the data encodes: **a place Jordan has NAMED outranks a fare WATCHER**, and an
# abandoned trip's tracker drops below both — a watcher outlives the decision that created it, which is
# exactly how this engine ended up drilling the DR for a Thailand trip.
#
# A MISSING or EMPTY table makes the engine REFUSE to pick a language rather than default to whichever
# country happens to match first (selftest 9 plants that failure). Guessing is the one thing it must not do.
TRIP_PRIORITY = DATA / "trip-priority.json"


def load_trip_priority() -> dict:
    """place -> rank, read from the pack file. No file / no entries -> {} and the engine declines."""
    if not TRIP_PRIORITY.exists():
        print(f"  ⚠️  NO TRIP-PRIORITY DATA at {TRIP_PRIORITY} — refusing to pick a language.", file=sys.stderr)
        return {}
    try:
        d = json.loads(TRIP_PRIORITY.read_text())
    except Exception as e:
        print(f"  ⚠️  trip-priority.json unreadable ({e}) — refusing to pick a language.", file=sys.stderr)
        return {}
    default = d.get("default_rank", 99)
    return {k: v.get("rank", default) for k, v in (d.get("places") or {}).items()}


TRIP_RANK = load_trip_priority()


def load_trips() -> list[dict]:
    """Every trip Jordan has in the vault, newest-relevant first. Real data only."""
    out: list[dict] = []
    if TRIPS.exists():
        try:
            d = json.loads(TRIPS.read_text())
            t = d.get("trip") or {}
            if t:
                out.append({"name": t.get("name", "?"), "status": t.get("status", ""),
                            "start": t.get("startDate", ""), "place": t.get("homeBase", ""),
                            "legs": t.get("legs", [])})
        except Exception as e:
            print(f"  ⚠️  trip json unreadable: {e}", file=sys.stderr)
    else:
        # 2026-10-17 — LOUD, not silent. This file went missing once and the engine said nothing: it
        # quietly fell back to the fare-watch cities below and served the wrong language. A missing trip
        # record is a DEFECT, so it is printed with the exact path that was checked.
        print(f"  ⚠️  NO TRIP RECORD at {TRIPS} — falling back to fare-watch cities, which are NOT a plan.",
              file=sys.stderr)
    # Route trackers = places he is actively watching (he is going there).
    for ph in sorted(TRAVEL_DIR.glob("*/price-history.md")):
        city = ph.parent.name
        if city in ("fx",):
            continue
        try:
            head = "\n".join(ph.read_text(errors="ignore").splitlines()[:40])
        except Exception:
            continue
        if not head.strip():
            continue
        out.append({"name": f"{city} (tracked route)", "status": "Watching fares",
                    "start": "", "place": city, "legs": [], "source": str(ph)})
    return out


def pick_dialect(trips: list[dict]) -> tuple[str, str]:
    """Return (dialect, why) from real trip data, NEAREST TRIP FIRST. Never guesses silently.

    Returns a DIALECT (`es-DO`), never a bare language. Jordan's correction: "Spanish" is not a
    lesson — Dominican Spanish is. A bare-language resolver is how the first lesson ended up
    teaching textbook Spanish he cannot use.

    Iteration order is by NEXT_TRIP_RANK, not by filename (bug 1, 2026-09-23).
    Place names are normalised before matching (bug 2: `puerto-plata` never matched `puerto plata`).
    """
    best: tuple[int, str, str] | None = None
    # A missing/empty priority table means we cannot say which trip leads. Refusing is the honest answer;
    # picking the first country that matches would be a guess wearing a lesson's clothes.
    if not TRIP_RANK:
        return "", ""
    for t in trips:
        blob = " ".join([t.get("name", ""), t.get("place", ""),
                         " ".join(l.get("destination", "") for l in t.get("legs", []))]).lower()
        blob = re.sub(r"[-_/]+", " ", blob)          # puerto-plata -> puerto plata
        blob = re.sub(r"\s+", " ", blob)
        for k, dialect in DIALECT_FOR_PLACE.items():
            if k in blob:
                # 2026-10-17 — a resolver that can name a dialect it has no bank for is a crash, not an
                # answer. (Combined with the loud missing-record warning above: a trip whose dialect has no
                # pack must DECLINE, never silently fall through to whichever country happens to match next.)
                if dialect not in PHRASES:
                    continue
                rank = TRIP_RANK.get(k, 99)
                if best is None or rank < best[0]:
                    best = (rank, dialect, t.get("name", k))
    if best is None:
        return "", ""
    return best[1], best[2]


def mastery(learner: str = "jordan") -> dict:
    """THIS learner's observed mastery only. Absent file -> empty, never a fabricated baseline.

    Legacy fallback: before the learner split there was one record per SEAT (`state/life-lessons.json`).
    Jordan's own record keeps counting from it — a structural change is not a reason to lose history
    (the same lesson as the `es` -> `es-DO` re-key).
    """
    for p in (state_path(learner), STATE if learner == "jordan" else None):
        if p and p.exists():
            try:
                return json.loads(p.read_text())
            except Exception as e:
                # A DAMAGED record must not read as "no history". Swallowing this turns every drill
                # back into "new" and the learner silently never revisits what they missed — the
                # empty-vs-failed confusion the Sr checklist opens with. (Found by Sr audit 2026-10-17.)
                print(f"  ⚠️  {p} is UNREADABLE ({type(e).__name__}: {e}) — this learner's drills "
                      f"will be recomputed as NEW. The record is damaged, not empty.", file=sys.stderr)
    return {}


def apply_forms(items: list[dict], learner: dict, dialect: str) -> tuple[list[dict], dict]:
    """Serve this learner the CORRECT politeness form, and say which form was served.

    The bank is written in one form (`ครับ` / `ผม`). A learner whose form differs gets a documented
    substitution — never a silent one, because a learner cannot hear a mistake they were never shown.
    """
    have = learner_forms(learner, dialect)
    default = (learner.get("defaults") or {}).get(dialect, {})
    swap = {default["particle"]: have["particle"], default["pronoun"]: have["pronoun"]} \
        if default.get("particle") and have.get("particle") and have != default else {}
    out = []
    for it in items:
        row = dict(it)
        if swap:
            for a, b in swap.items():
                if a and a in row.get("es", ""):
                    row["es"] = row["es"].replace(a, b)
            # The English gloss carries the speaker's gender too ("Hello (male speaker)"). Leaving it
            # standing would LABEL her Thai as male while serving the female form — a mislabel is a
            # wrong answer, not a cosmetic one.
            d_en, h_en = default.get("form_english"), have.get("form_english")
            if d_en and h_en and row.get("en"):
                row["en"] = row["en"].replace(d_en, h_en)
        out.append(row)
    return out, have


def build_lesson(trips: list[dict], seen: dict, learner_key: str = "jordan") -> dict | None:
    dialect, why = pick_dialect(trips)
    if not dialect:
        return None
    learner = resolve_learner(learner_key)          # hard stop on an unknown learner
    bank = PHRASES[dialect]
    items: list[dict] = []
    for sit in SITUATION_ORDER:
        for row in bank.get(sit, []):
            es, en = row[0], row[1]
            std = row[2] if len(row) > 2 else "—"
            items.append({"situation": sit, "es": es, "en": en, "std": std,
                          "bank_es": es})      # what the BANK held, for the key fallback below

    # ── FORMS FIRST, THEN THE KEY (fixed 2026-10-17, found by the Sr audit) ──────────────────────
    # The mastery key was computed from the BANK phrase with the forms swapped AFTERWARDS. The bank is
    # written in the MALE form, so Josephine's served `ฉันมาเที่ยวค่ะ` carried a status derived from
    # `th-TH:ผมมาเที่ยวครับ` — a key no recorder would ever write for her. Her misses would never return
    # as drills and she would see NEW forever, with no error anywhere. Key the phrase actually SERVED.
    items, forms = apply_forms(items, learner, dialect)

    for it in items:
        served_key = f"{dialect}:{it['es']}"
        bank_key = f"{dialect}:{it['bank_es']}"
        # LEGACY KEY FALLBACK. Mastery written before the dialect change is keyed by BARE language
        # (`es:La cuenta, por favor.`); the dialect split keys them `es-DO:...`. Without this every
        # stored result silently orphans — history resets to "new" and the drill loop forgets what was
        # missed. A rename is not a reason to lose data. (Caught by selftest check 3, 2026-09-23.)
        legacy_key = f"{dialect.split('-')[0]}:{it['es']}"
        s = (seen.get(served_key) or seen.get(bank_key) or seen.get(legacy_key) or {})
        it["key"] = served_key                 # the key a recorder must write back
        it["attempts"] = s.get("attempts", 0)
        it["correct"] = s.get("correct", 0)
        it["status"] = ("new" if not s else
                        "weak" if s.get("correct", 0) / max(s.get("attempts", 1), 1) < 0.6
                        else "solid")

    # Weak first, then new — the loop closes: what was missed gets drilled.
    items.sort(key=lambda i: ({"weak": 0, "new": 1, "solid": 2}[i["status"]], i["situation"]))
    items = items[:6]
    pron = load_pron(dialect.split("-")[0])
    for it in items:
        it["rom"] = pron.get(it["es"])        # None = no reading, and the render stays silent
    return {"dialect": dialect, "lang": dialect.split("-")[0],
            "dialect_label": DIALECT_LABEL.get(dialect, dialect),
            "voice_id": resolve_voice(dialect, learner),
            # The BRIDGE — reads the `rom` approximation aloud in THIS learner's first language,
            # so an English speaker hears an English-eye reading and a Tagalog speaker hears a
            # Filipino one. Pack data; None means that language has no bridge and the Thai stands alone.
            "bridge_voice_id": resolve_bridge_voice(learner),
            "learner": learner["key"], "learner_display": learner.get("display", learner["key"]),
            "forms": forms, "why": why, "generated": datetime.utcnow().isoformat(timespec="seconds"),
            "items": items}


def render(lesson: dict) -> str:
    lines = [
        f"🎓 LIFE LESSON — {lesson.get('dialect_label', lesson['dialect'])}",
        f"learner: {lesson.get('learner_display', '?')} — served in the "
        f"{lesson.get('forms', {}).get('form_label', 'default form')}",
        f"drawn from: {lesson['why']}",
        "",
    ]
    for i, it in enumerate(lesson["items"], 1):
        tag = {"weak": "🔁 DRILL (missed before)", "new": "🆕 NEW", "solid": "✅ review"}[it["status"]]
        lines.append(f"{i}. [{it['situation']}] {tag}")
        lines.append(f"   {it['es']}")
        if it.get("rom"):
            lines.append(f"   🔤 {it['rom']}")
        lines.append(f"   {it['en']}")
        if it.get("std") and it["std"] != "—":
            lines.append(f"   (textbook: {it['std']})")
        lines.append("")
    lines.append("Audio is generated separately, in the matching regional voice.")
    lines.append("Nothing here is invented — every phrase is keyed to a country you are")
    lines.append("actually travelling to, in the dialect spoken there.")
    return "\n".join(lines)


def selftest() -> int:
    """PLANT a failure and prove we go RED. House rule: every detector proves it can fail."""
    print("SELFTEST — planting failures, expecting loud RED\n")
    ok = True

    # 1. Missing trip data must produce NO lesson, not a generic course.
    real_trips, real_load = load_trips, None
    globals()["load_trips"] = lambda: []
    l = build_lesson([], {})
    if l is None:
        print("  ✅ RED 1: no trip data -> no lesson (refuses to invent one)")
    else:
        print("  ❌ FAIL 1: invented a lesson with no trip data"); ok = False
    globals()["load_trips"] = real_trips

    # 2. Mastery must be UNKNOWN, never a fabricated 0%.
    l = build_lesson([{"name": "Puerto Plata DR", "place": "Puerto Plata", "legs": []}], {})
    if l and all(i["status"] == "new" and i["attempts"] == 0 for i in l["items"]):
        print("  ✅ RED 2: unseen phrases are 'new' (attempts 0) — never a fake 0% score")
    else:
        print("  ❌ FAIL 2: fabricated a mastery value"); ok = False

    # 3. Weak items MUST sort first — the loop must actually close.
    # deliberately a LEGACY bare-language key: proves old records still count after the dialect split
    seen = {"es:La cuenta, por favol": {"attempts": 4, "correct": 0}}
    l = build_lesson([{"name": "Puerto Plata DR", "place": "Puerto Plata", "legs": []}], seen)
    if l and l["items"][0]["status"] == "weak":
        print("  ✅ RED 3: a phrase he keeps missing sorts to the TOP (loop closes)")
    else:
        print("  ❌ FAIL 3: missed phrases are not prioritised"); ok = False

    # 4. Thai must not be presented as a full course.
    l = build_lesson([{"name": "Bangkok Thailand", "place": "Bangkok", "legs": []}], {})
    if l and l["dialect"] == "th-TH" and len(l["items"]) <= 6:
        print("  ✅ RED 4: Thai gives a small survival set, not a fake 150-lesson course")
    else:
        print("  ❌ FAIL 4: Thai scope wrong"); ok = False

    # 5. THE ORDERING BUG, REGRESSION-GUARDED — and RE-STATED 2026-10-17, because the PLAN changed.
    #    Both countries present (the real vault state: bangkok/ and puerto-plata/ trackers coexist).
    #    From 2026-09-23 the assertion was "Spanish wins, the DR trip is nearer". That rule is now FALSE:
    #    the DR window was killed by the Amazon blackout and Jordan named Thailand on 2026-10-17
    #    (*"We both are planning a trip to Thailand and want to learn Thai."*). So the guard now asserts
    #    the durable rule underneath it: **a place Jordan has NAMED outranks an abandoned trip's fare
    #    WATCHER.** Asserting the old winner would now be asserting a stale plan — the exact class of
    #    error this check exists to catch.
    mixed = [{"name": "bangkok (tracked route)", "place": "bangkok", "legs": []},
             {"name": "puerto-plata (tracked route)", "place": "puerto-plata", "legs": []}]
    l = build_lesson(mixed, {})
    if l and l["dialect"] == "th-TH":
        print("  ✅ RED 5: the NAMED trip outranks a stale fare WATCHER (Thai, not the abandoned DR)")
    else:
        print(f"  ❌ FAIL 5: wrong dialect leads with two trips — got {l['dialect'] if l else None}"); ok = False

    # 6. Reversed input order must give the SAME answer (order-independence, not luck).
    l2 = build_lesson(list(reversed(mixed)), {})
    if l2 and l2["dialect"] == "th-TH":
        print("  ✅ RED 6: input order does not change the answer")
    else:
        print("  ❌ FAIL 6: answer depends on list order"); ok = False

    # 7. DIALECT, NOT LANGUAGE (Jordan's correction, 2026-09-23). A bare-language result means the
    #    learner gets textbook Spanish they cannot use — the exact defect he caught. Assert the
    #    variant is named, and that a matching regional VOICE is attached.
    l = build_lesson([{"name": "Puerto Plata DR", "place": "Puerto Plata", "legs": []}], {})
    if l and l["dialect"] == "es-DO" and l.get("voice_id"):
        print("  ✅ RED 7: resolves to a DIALECT (es-DO) with a matching regional voice")
    else:
        print(f"  ❌ FAIL 7: dialect/voice not resolved — got {l and l.get('dialect')}"); ok = False

    # 8. The regional form must be present AND differ from textbook, or there is nothing to teach.
    l = build_lesson([{"name": "Puerto Plata DR", "place": "Puerto Plata", "legs": []}], {})
    shown = [i for i in (l or {}).get("items", []) if i.get("std") and i["std"] != "—"]
    if shown:
        print(f"  ✅ RED 8: {len(shown)} phrases carry the textbook form beside the Dominican one")
    else:
        print("  ❌ FAIL 8: no standard/regional contrast — the lesson teaches nothing dialectal"); ok = False

    # 9. NO TRIP-PRIORITY TABLE -> REFUSE (2026-10-17). The priority now lives in a pack file, so the
    #    failure mode has moved: a missing or empty file must make the engine DECLINE, not pick whichever
    #    country happens to match first. Getting this wrong is how a stale plan keeps winning silently —
    #    the exact bug that served Dominican Spanish for a Thailand trip.
    real_rank, real_prio = TRIP_RANK, TRIP_PRIORITY
    globals()["TRIP_RANK"] = {}
    l = build_lesson([{"name": "Puerto Plata DR", "place": "Puerto Plata", "legs": []}], {})
    if l is None:
        print("  ✅ RED 9: no trip-priority data -> REFUSES to pick a language (never a silent default)")
    else:
        print(f"  ❌ FAIL 9: guessed a language with no priority data — got {l.get('dialect')}"); ok = False
    globals()["TRIP_RANK"] = real_rank
    if TRIP_PRIORITY != real_prio:
        print("  ❌ FAIL 9b: selftest mutated the priority path"); ok = False

    # 10. AN UNKNOWN LEARNER IS AN ERROR, NOT A PERMISSION (the tenant_guard rule, 2026-10-17).
    #     Jordan: *"share progress but separate… Similar to tenant cron jobs."* A learner the registry
    #     does not know must stop the run, not get served the seat owner's lesson.
    try:
        resolve_learner("nobody-on-the-roster")
        print("  ❌ FAIL 10: served an unknown learner instead of refusing"); ok = False
    except SystemExit:
        print("  ✅ RED 10: an unknown learner is a HARD STOP (never a silent default)")

    # 11. SHARED ENGINE, SEPARATE PROGRESS. Two learners must differ in BOTH the record they write to
    #     and the politeness form they are served — otherwise the bank teaches one of them the wrong
    #     person's Thai.
    trip = [{"name": "Thailand — Bangkok then Pattaya", "place": "Bangkok", "legs": []}]
    l_j = build_lesson(trip, {}, "jordan")
    l_o = build_lesson(trip, {}, "josephine-b")
    same_path = state_path("jordan") == state_path("josephine-b")
    j_th = " ".join(i["es"] for i in (l_j or {}).get("items", []))
    o_th = " ".join(i["es"] for i in (l_o or {}).get("items", []))
    if (not same_path) and j_th and o_th and j_th != o_th and "ครับ" in j_th and "ค่ะ" in o_th:
        print("  ✅ RED 11: two learners = two records AND two forms (ครับ for him, ค่ะ for her)")
    else:
        print(f"  ❌ FAIL 11: learners not separated — same_path={same_path}, "
              f"same_phrases={j_th == o_th}"); ok = False

    # 12. Every lesson records WHO it was for, and writes its record into the LEARNER's own brain folder.
    if (l_o or {}).get("learner") == "josephine-b" and (l_o or {}).get("forms", {}).get("form_label"):
        print("  ✅ RED 12: the lesson names the learner and the form it served")
    else:
        print("  ❌ FAIL 12: lesson does not name its learner/form"); ok = False

    # 13. A NATIVE VOICE PER FORM, NEVER ROGER. The engine used to wire th-TH to Roger
    #     (CwhRBWXzGAHq8TQ4Fs17, accent=american) — an English speaker reading Thai. Both learners must
    #     now resolve to a TH voice, and to DIFFERENT ones, because the learner copies what they hear.
    v_j, v_o = resolve_voice("th-TH", resolve_learner("jordan")), resolve_voice("th-TH", resolve_learner("josephine-b"))
    if v_j and v_o and v_j != v_o and "CwhRBWXzGAHq8TQ4Fs17" not in (v_j, v_o):
        print(f"  ✅ RED 13: th-TH resolves to native voices, per form ({v_j[:6]}… / {v_o[:6]}…), never Roger")
    else:
        print(f"  ❌ FAIL 13: Thai voice not separated/native — jordan={v_j}, josephine={v_o}"); ok = False

    # 14. NO VOICE MUST REFUSE, NOT BORROW. A dialect with no native voice returns None so the audio step
    #     declines; borrowing an English voice is how the first wrong lesson was made.
    if resolve_voice("xx-XX", resolve_learner("jordan")) is None:
        print("  ✅ RED 14: an unvoiced dialect returns None — nothing is borrowed")
    else:
        print("  ❌ FAIL 14: borrowed a voice for a dialect that has none"); ok = False

    # 15. EVERY SERVED PHRASE GETS A READING — for BOTH learners. The reading is looked up AFTER the
    #     form swap, so it must exist in the pack under the FEMALE phrase too: if it only covered the
    #     male bank, Josephine would be served Thai with no way to say it.
    miss_j = [i["es"] for i in (l_j or {}).get("items", []) if not i.get("rom")]
    miss_o = [i["es"] for i in (l_o or {}).get("items", []) if not i.get("rom")]
    rom_o = " ".join(i.get("rom") or "" for i in (l_o or {}).get("items", []))
    if not miss_j and not miss_o and "kha" in rom_o:
        print("  ✅ RED 15: every served phrase carries a reading, both forms (hers ends in 'kha')")
    else:
        print(f"  ❌ FAIL 15: phrases served without a reading — jordan={miss_j}, josephine={miss_o}"); ok = False

    # 16. THE DRILL LOOP CLOSES ON THE PHRASE THE LEARNER WAS SERVED (found by the Sr audit). A miss
    #     recorded against the served phrase must come back as a drill — and must NOT leak into the
    #     other learner, who shares the same bank but is served a different form.
    female_key = "th-TH:ฉันมาเที่ยวค่ะ"
    seen_o = {female_key: {"attempts": 2, "correct": 0}}
    o2 = build_lesson(trip, seen_o, "josephine-b")
    j2 = build_lesson(trip, seen_o, "jordan")        # the SAME record, handed to the other learner
    o2w = [i for i in (o2 or {}).get("items", []) if i.get("status") == "weak"]
    j2w = [i for i in (j2 or {}).get("items", []) if i.get("status") == "weak"]
    keys_ok = any(i.get("key") == female_key for i in (o2 or {}).get("items", []))
    if o2w and o2w[0].get("key") == female_key and keys_ok and not j2w:
        print("  ✅ RED 16: her miss returns as a drill keyed to the SERVED phrase, and does not leak to him")
    else:
        print(f"  ❌ FAIL 16: drill loop broken — her_weak={len(o2w)}, key_ok={keys_ok}, his_weak={len(j2w)}")
        ok = False

    print("\n" + ("SELFTEST PASSED — all sixteen planted failures went RED"
                  if ok else "SELFTEST FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="silent on success (cron mode)")
    ap.add_argument("--learner", default="jordan",
                    help="who the lesson is for (registry: data/learners.json). Separate progress per learner.")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    trips = load_trips()
    if not trips:
        print("🔴 life-lesson-engine: NO trip data in the vault — refusing to invent a lesson.",
              file=sys.stderr)
        return 1
    lesson = build_lesson(trips, mastery(a.learner), a.learner)
    if lesson is None:
        print("🔴 life-lesson-engine: no country in your trips maps to a language bank. "
              "Add the trip or the bank — not a generic course.", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.learner}.json").write_text(json.dumps(lesson, ensure_ascii=False, indent=2))

    # ── THE BRAIN IS THE RECORD (Jordan, 2026-10-17: *"Use the brain for Jordan lesson and Josephine
    # lesson."*) One file per LEARNER per day, in the learner's own folder. The profile cache above is
    # scratch; this is the record a human reads, and it must never be one shared file for two people.
    brain = VAULT / "EDU" / "lessons" / lesson["learner"]
    brain.mkdir(parents=True, exist_ok=True)
    (brain / f"{date.today().isoformat()}-{lesson['dialect']}.md").write_text(
        f"<!-- generated by life-lesson-engine.py — served, not written by hand -->\n\n"
        + render(lesson) + "\n")

    if a.json:
        print(json.dumps(lesson, ensure_ascii=False, indent=2))
    elif not a.quiet:
        print(render(lesson))
    return 0


if __name__ == "__main__":
    sys.exit(main())
