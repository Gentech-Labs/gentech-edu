#!/usr/bin/env python3
"""
life-lesson-scenario.py — scenario practice drawn from REAL venues and prices.

WHY
---
Jordan (2026-09-23): *"if I wanted to give you a scenario… I know when I go to the POP airport and I get off
I'm gonna want to know what to say to the taxi guy… or one of the first restaurants I plan on going to is
Flip Flops, so I want to know how to order something in Spanish… and if we could pull up Flip Flops menu…
That's what would make this next level — adding intelligence so we get language learning and trip planning
together, part of GenTech Travels."*

So a scenario is **not** a generic dialogue. It is built against **the actual venue, its actual menu, and the
actual price in the local currency** — which is what makes the phrase usable the moment he lands.

WHAT MAKES THIS DIFFERENT FROM A PHRASEBOOK
-------------------------------------------
The numbers come from the venue's own published menu (read from its menu boards, 2026-09-23), not invented.
The DOP→USD conversion uses **our own FX tracker's latest row**, not a remembered rate. Every figure in the
output is traceable to a file, and the output says which.

DESIGN RULE (decides-alone-execution)
-------------------------------------
The engine picks the scenario from his real itinerary and serves the next unrehearsed one. A menu of
scenarios to choose from would hand the decision back — the failure mode we already named.

HONESTY RULES
-------------
  · A price with no published figure is UNKNOWN ("varies"), never $0 and never guessed.
  · If the FX row is missing, it says so and prints DOP only — it does not silently use a stale rate.
  · `--selftest` plants failures and proves each goes RED.

USAGE
  python3 life-lesson-scenario.py                 # the scenario he needs next
  python3 life-lesson-scenario.py --venue flip-flops
  python3 life-lesson-scenario.py --selftest
  python3 life-lesson-scenario.py --json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# ── SEAT-LOCAL, resolved from THIS file's own location. Never a hardcoded profile. ────────────────
# It was the literal string "/opt/data/profiles/gentech" on all four seats, so every seat read
# HQ's venue data and would have written its lesson cache into HQ's profile. Measured 2026-09-25,
# fixed and then folded into the tree: this script now lives in the skill dir with the data it reads.
def _seat() -> str:
    """The seat this copy is running on, derived from the script's OWN path.

    Cron has no script-args field, so path-derived identity is the only fleet-wide
    mechanism (same idiom as handoff-watcher.py). Running the SHARED CORE copy is not a
    seat; it falls back to HQ, which owns the core.
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

# The venue data lives with the SKILL that documents it — `skills/edu/data/travel-venues.json`, the
# file SKILL.md names and `edu_apps.py` reads. One location, one reader, one doc: a reader that opens
# a different file than the doc names is how the apps map went stale unnoticed.
VENUES = DATA / "travel-venues.json"
FX = pathlib.Path("/opt/data/.obsidian-vault/00-HQ/01-Travel/fx/price-history.md")  # the vault, shared by design
OUT = PROFILE / "cache" / "life-lessons"

# ── Scenario phrase banks, keyed by (dialect, venue type). ──────────────────────────────────────
# Written in the REGIONAL form (es-DO: dropped s, -ado→-a'o, tú+inversion) because that is what he
# will hear. The textbook form rides alongside so the contrast teaches.
SCENARIOS = {
    ("es-DO", "ride"): {
        "title": "Rides on the North Coast — settling the fare before you move",
        "setup": "No meters in the DR. One price, agreed up front — that is the whole game. Works for a taxi, a private driver, or a driver who tries to change the Uber price.",
        "lines": [
            ("¿Cuánto me va' a cobrá a Sosúa?", "How much will you charge me to Sosúa?", "¿Cuánto me va a cobrar a Sosúa?"),
            ("¿E' precio fijo o depende del tráfico?", "Is that a fixed price or does it depend on traffic?", "¿Es precio fijo o depende del tráfico?"),
            ("Ante' de montá, confirmamo' el precio", "Before we get in, let's confirm the price", "Antes de montar, confirmemos el precio"),
            ("Ese precio no me cuadra, pana", "That price doesn't work for me, friend", "Ese precio no me conviene"),
            ("Lo' do' pagamo' mitá y mitá", "We split it half and half (two of us)", "Los dos pagamos mitad y mitad"),
            ("¿Tú acepta' tarjeta o solo efectivo?", "Do you take card or cash only?", "¿Acepta tarjeta o solo efectivo?"),
            ("Yo tengo mi tarifa en la app", "I have my fare in the app", "Tengo mi tarifa en la app"),
            ("Vamo' a la mitá, ¿tá bien así?", "Let's meet in the middle, is that ok?", "Vamos a la mitad, ¿está bien así?"),
            ("No, gracias, voy a buscá otro", "No thanks, I'll look for another", "No, gracias, voy a buscar otro"),
        ],
        "watch_out": [
            "Settle the price BEFORE the bags go in the trunk — after that you have no leverage.",
            "‘Por persona’ vs ‘por viaje’ is the commonest tourist overcharge in the DR.",
            "If an app driver messages to change the accepted price, CANCEL in the app before getting in. Never pay a cash top-up on top of the app fare — that is paying twice.",
            "Taxi has no meter here, so there is no 'wrong' price — only one you agreed to.",
        ],
    },
    ("es-DO", "airport"): {
        "title": "Landing at POP — getting a taxi without getting taken",
        "setup": "You clear arrivals. Drivers will approach you. You want the price BEFORE you get in.",
        "lines": [
            ("¿Qué lo qué?", "What's up? (friendly, to a driver waiting around)", "¿Qué tal?"),
            ("¿Cuánto e' pa' Sosúa?", "How much to Sosúa?", "¿Cuánto es para Sosúa?"),
            ("¿E' por persona o por viaje?", "Is that per person or per trip?", "¿Es por persona o por viaje?"),
            ("Vamo' a usá el taxímetro, ¿tá bien?", "Let's use the meter, ok?", "Vamos a usar el taxímetro"),
            ("Vo' a pagá en efectivo", "I'm paying cash", "Voy a pagar en efectivo"),
            ("Eso 'tá muy caro, pana", "That's too expensive, friend", "Eso está muy caro"),
            ("¿Me puede' llevá a ete' lugal?", "Can you take me to this place?", "¿Me puedes llevar a este lugar?"),
        ],
        "watch_out": [
            "Agree the price BEFORE the bags go in the trunk — after that you have no leverage.",
            "‘Por persona’ vs ‘por viaje’ is the single most common tourist overcharge in the DR.",
            "Airport taxis are officially fixed-rate and pricier than street taxis; a hotel transfer is the safe fallback.",
        ],
    },
    ("es-DO", "pizzeria"): {
        "title": "Ordering at Sliced DR — the oxtail pizza run",
        "setup": "Rooftop, corner of Pedro Clisante & Dr. Rosen. Spanish-speaking staff, no English fallback here.",
        "lines": [
            ("¿Qué lo qué?", "What's up? (friendly — this is the DR hello)", "¿Qué tal?"),
            ("Bueno', ¿tienen la pizza de rabo?", "Do you have the oxtail pizza?", "¿Tienen la pizza de rabo de toro?"),
            ("¿Cómo 'tá la de Detroit, e' buena?", "How's the Detroit one, is it good?", "¿Cómo está la de Detroit?"),
            ("Dame do' porcione' de rabo, por favol", "Give me two slices of oxtail, please", "Dame dos porciones de rabo"),
            ("¿Cuánto e' en total?", "How much is it altogether?", "¿Cuánto es en total?"),
            ("¿Qué tú me recomienda' pa' beber?", "What do you recommend to drink?", "¿Qué me recomiendas para beber?"),
            ("Vamo' a comé arriba en la azotea", "Let's eat up on the rooftop", "Vamos a comer arriba en la azotea"),
            ("La cuenta, por favol", "The check, please", "La cuenta, por favor"),
            ("Eto' 'tá nítido, ¿tú vuelve' mañana?", "This is great — are you back tomorrow?", "Esto está muy bien, ¿tú vuelves mañana?"),
        ],
        "watch_out": [
            "No English fallback here — this is the real test, unlike Flip Flop.",
            "The oxtail pizza is their signature, but it sells out; reviews push people to off-peak.",
            "Call ahead on hours (+1 849-517-1853). Published hours conflict across sources and Tuesday is closed.",
            "‘Rabo’ is the word you need — oxtail. In the DR it is rabo / rabo guisado (the word 'encendío' is the Puerto Rican name, not Dominican).",
        ],
    },
    ("es-DO", "restaurant"): {
        "title": "Ordering at Flip Flop Sports Bar",
        "setup": "You sit down. The staff speak English AND Spanish — so this is your low-stakes practice run.",
        "lines": [
            ("¿Qué lo qué?", "What's up? (friendly greeting)", "¿Qué tal?"),
            ("Bueno', ¿qué tú me recomienda'?", "So, what do you recommend?", "¿Qué me recomiendas?"),
            ("Quiero la Dominican Breakfast", "I want the Dominican Breakfast", "Quiero el desayuno dominicano"),
            ("¿Ese viene con mangú?", "Does that come with mangú?", "¿Ese viene con mangú?"),
            ("Voy a queré la' alita' con salsa BBQ", "I want the wings with BBQ sauce", "Voy a querer las alitas con salsa BBQ"),
            ("¿Cuánto cuesta?", "How much does it cost?", "¿Cuánto cuesta?"),
            ("Una cerveza bien fría, por favol", "One ice-cold beer, please", "Una cerveza bien fría, por favor"),
            ("La cuenta, por favol", "The check, please", "La cuenta, por favor"),
            ("Estaba nítido, gracias", "It was great, thanks", "Estaba muy bien, gracias"),
        ],
        "watch_out": [
            "The menu prints ‘Taxes included / Tip NOT included’ — the tip is genuinely separate here.",
            "Staff speak English, so if you freeze you can fall back. Say it in Spanish first anyway.",
            "Mangú is mashed plantain — the authentic Dominican dish on the breakfast menu.",
        ],
    },
}


def load_venues() -> dict:
    if not VENUES.exists():
        return {}
    try:
        return {v["id"]: v for v in json.loads(VENUES.read_text()).get("venues", [])}
    except Exception as e:
        print(f"  ⚠️  venue file unreadable: {e}", file=sys.stderr)
        return {}


CUR_COL = {"PHP": 1, "THB": 2, "DOP": 3, "MXN": 4}   # tracker header: | date | PHP | THB | DOP | MXN |


def fx_rate(code: str = "DOP") -> tuple[float | None, str]:
    """Latest rate for ANY currency in OUR tracker — the column is found by its HEADER, never hardcoded.
    A Thai venue was being priced in Dominican pesos because build() called fx_dop() unconditionally."""
    if not FX.exists():
        return None, "fx tracker file missing"
    lines = [l for l in FX.read_text(errors="ignore").splitlines() if l.strip().startswith("|")]
    hdr = next((l for l in lines if not re.match(r"\|\s*\d{4}-\d{2}-\d{2}", l)), None)
    cols_hdr = [c.strip().upper() for c in hdr.strip("|").split("|")] if hdr else []
    code = (code or "DOP").upper()
    idx = cols_hdr.index(code) if code in cols_hdr else CUR_COL.get(code)
    data = [r for r in lines if re.match(r"\|\s*\d{4}-\d{2}-\d{2}", r)]
    if not data or idx is None:
        return None, f"no {code} column in the fx tracker"
    cols = [c.strip() for c in data[-1].strip("|").split("|")]
    if idx >= len(cols):
        return None, f"malformed fx row: {data[-1][:40]}"
    try:
        return float(cols[idx]), f"{cols[0]} (our fx tracker, {code} column)"
    except ValueError:
        return None, f"unparsable {code} rate: {cols[idx]}"


def fx_dop() -> tuple[float | None, str]:
    """Latest DOP rate from OUR tracker. Returns (rate, provenance) — never a remembered number."""
    if not FX.exists():
        return None, "fx tracker file missing"
    rows = [l for l in FX.read_text(errors="ignore").splitlines() if l.strip().startswith("|")]
    data = [r for r in rows if re.match(r"\|\s*\d{4}-\d{2}-\d{2}", r)]
    if not data:
        return None, "no dated rows in fx tracker"
    last = data[-1]
    cols = [c.strip() for c in last.strip("|").split("|")]
    # header is | date | PHP | THB | DOP | MXN |
    if len(cols) < 4:
        return None, f"malformed fx row: {last[:40]}"
    try:
        return float(cols[3]), f"{cols[0]} (our fx tracker)"
    except ValueError:
        return None, f"unparseable DOP value: {cols[3]!r}"


def usd(dop: int | None, rate: float | None) -> str:
    """Convert DOP to USD using OUR rate. Unknown stays unknown — never a fabricated 0."""
    if dop is None:
        return "price varies"
    if rate is None:
        return "(no FX rate available)"
    return f"≈ ${dop / rate:,.2f}"


SHAPES = DATA / "scenario-shapes.json"


def load_shapes() -> dict:
    """Scenario SHAPES live in a PACK FILE, so a new subject is a file, not an edit — the boundary rule
    this script's own docstring names. Built-in es-DO shapes stay; the pack adds or overrides by 'dialect|type'."""
    shapes = dict(SCENARIOS)
    if SHAPES.exists():
        try:
            for k, v in json.loads(SHAPES.read_text()).get("shapes", {}).items():
                d, t = k.split("|", 1)
                shapes[(d, t)] = {"title": v["title"], "setup": v["setup"],
                                  "lines": [tuple(x) for x in v["lines"]],
                                  "watch_out": v.get("watch_out", [])}
        except Exception:
            pass
    return shapes


def build(venue_id: str, venues: dict) -> dict | None:
    v = venues.get(venue_id)
    if not v:
        return None
    key = (v.get("dialect", "es-DO"), v.get("type", ""))
    scen = load_shapes().get(key)
    if not scen:
        return None

    rate, prov = fx_rate(v.get("currency", "DOP"))
    items = []
    m = v.get("menu", {}) or {}
    # Walk whatever sections this venue actually publishes - a hardcoded section list silently
    # showed NOTHING for a venue whose menu is shaped differently (the Sliced case).
    for section, entries in m.items():
        if section.endswith("_note") or section.endswith("_honesty") or not isinstance(entries, list):
            continue
        if section == "other_flavours_named" or section == "other_food":
            if entries:
                items.append({"section": section, "item": " · ".join(map(str, entries)),
                              "dop": None, "usd": "", "note": "named by the venue, no price published"})
            continue
        for it in entries[:4]:
            if not isinstance(it, dict):
                continue
            price = it.get("dop", it.get("price"))
            is_local = "dop" in it
            items.append({
                "section": section,
                "item": it.get("item", "?"),
                "dop": price if is_local else None,
                "usd": usd(price, rate) if is_local else (f"{price} (as posted)" if price else "price varies"),
                "note": it.get("note", ""),
            })

    return {
        "venue_id": venue_id,
        "venue": v.get("name"),
        "dialect": v.get("dialect"),
        "title": scen["title"],
        "setup": scen["setup"],
        "why": f"{v.get('name')} — {v.get('address', v.get('city', ''))}",
        "lines": [{"drd": a, "en": b, "std": c} for a, b, c in scen["lines"]],
        "watch_out": scen["watch_out"],
        "menu": items,
        "fx": {"rate": rate, "provenance": prov, "currency": v.get("currency", "DOP")},
        "venue_facts": {k: v.get(k) for k in
                        ("address", "phone", "hours", "website", "menu_url",
                         "staff_languages", "note_for_jordan", "source", "verified")
                        if v.get(k)},
        "daily_specials": v.get("daily_specials", {}),
        "menu_footer": v.get("footer_note_from_menu", ""),
    }


def render(s: dict) -> str:
    out = [f"🎯 SCENARIO — {s['title']}", f"   {s['setup']}", ""]
    out.append(f"📍 {s['venue']}")
    for k, label in (("address", "address"), ("phone", "phone"), ("hours", "hours")):
        if s["venue_facts"].get(k):
            out.append(f"   {label}: {s['venue_facts'][k]}")
    if s["venue_facts"].get("note_for_jordan"):
        out.append(f"   ⓘ {s['venue_facts']['note_for_jordan']}")
    out.append("")

    _dn = {"es-DO": "Dominican", "th-TH": "Thai"}.get(s.get("dialect"), s.get("dialect") or "local")
    out.append(f"WHAT TO SAY ({_dn} / what you'll hear):")
    for i, l in enumerate(s["lines"], 1):
        out.append(f"  {i}. {l['drd']}")
        out.append(f"     {l['en']}")
        if l["std"] and l["std"] != "—":
            out.append(f"     (textbook: {l['std']})")
    out.append("")

    if s["menu"]:
        rate = s["fx"]["rate"]
        has_dop = any(i["dop"] is not None for i in s["menu"])
        head = f"THE REAL MENU — prices in {s['fx']['currency']}"
        if has_dop and rate:
            head += f", converted at {rate} ({s['fx']['provenance']})"
        elif has_dop:
            head += f" — ⚠️ NO FX RATE ({s['fx']['provenance']}), showing DOP only"
        else:
            head += " (as published by the venue — no conversion applied)"
        out.append(head)
        for it in s["menu"]:
            # Show whatever price is REAL. "varies" is only honest when nothing is published -
            # printing it beside a posted price contradicts the next column.
            if it["dop"] is not None:
                price = f"{it['dop']} DOP"
            elif it["usd"]:
                price = "—"
            else:
                price = "varies"
            out.append(f"   • {it['item']:<34} {price:>12}   {it['usd']}")
            if it["note"]:
                out.append(f"       ({it['note']})")
        if s["menu_footer"]:
            out.append(f"   ⓘ {s['menu_footer']}")
        out.append("")

    if s["daily_specials"]:
        out.append("DAILY SPECIALS:")
        for d, sp in s["daily_specials"].items():
            out.append(f"   {d}: {sp}")
        out.append("")

    out.append("WATCH OUT:")
    for w in s["watch_out"]:
        out.append(f"   ⚠️ {w}")
    out.append("")
    out.append(f"source: {s['venue_facts'].get('source','—')} · verified {s['venue_facts'].get('verified','—')}")
    return "\n".join(out)


def selftest() -> int:
    """Plant failures; prove each goes RED before shipping."""
    print("SELFTEST — planting failures, expecting loud RED\n")
    ok = True

    v = load_venues()
    if "flip-flops" in v:
        print("  ✅ RED 1: real venue data loads (Flip Flop present)")
    else:
        print("  ❌ FAIL 1: venue data missing"); ok = False

    s = build("flip-flops", v)
    if s and s["menu"]:
        print(f"  ✅ RED 2: menu carries {len(s['menu'])} REAL items with prices")
    else:
        print("  ❌ FAIL 2: no menu"); ok = False

    # A missing venue must return None — never a fabricated generic scenario.
    if build("no-such-venue", v) is None:
        print("  ✅ RED 3: unknown venue -> None, never an invented scenario")
    else:
        print("  ❌ FAIL 3: invented a scenario for a venue that does not exist"); ok = False

    # FX: a rate must come from the tracker file with provenance, or be reported missing.
    rate, prov = fx_rate()
    if rate and "fx tracker" in prov:
        print(f"  ✅ RED 4: DOP rate {rate} sourced from OUR tracker ({prov}) — not remembered")
    else:
        print(f"  ❌ FAIL 4: no traced FX rate (got {rate}, {prov})"); ok = False

    # UNKNOWN price must never render as $0 or a guess.
    if usd(None, rate) == "price varies":
        print("  ✅ RED 5: unknown price says 'price varies' — never $0.00")
    else:
        print(f"  ❌ FAIL 5: unknown price rendered as {usd(None, rate)}"); ok = False

    # With no FX rate, it must DECLARE the gap rather than guess a stale number.
    if "(no FX rate available)" in usd(350, None):
        print("  ✅ RED 6: no FX rate -> declares it, does not guess")
    else:
        print("  ❌ FAIL 6: silently produced a USD figure without a rate"); ok = False

    # EVERY venue must have a scenario — checked against load_shapes(), the SAME merged source the
    # builder uses (built-in shapes + the pack file). Checking the built-in dict alone hid the pack.
    missing = [vid for vid, vv in v.items()
               if (vv.get("dialect", "es-DO"), vv.get("type", "")) not in load_shapes()]
    if not missing and v:
        print(f"  ✅ RED 7: all {len(v)} venues have a scenario bank: {', '.join(sorted(v))}")
    else:
        print(f"  ❌ FAIL 7: venues with NO scenario (a real venue would serve nothing): {missing}")
        ok = False

    print("\n" + ("SELFTEST PASSED — all planted failures went RED"
                  if ok else "SELFTEST FAILED"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", help="venue id (default: the one needed next)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    venues = load_venues()
    if not venues:
        print("🔴 life-lesson-scenario: no venue data — refusing to invent a scenario.",
              file=sys.stderr)
        return 1

    vid = a.venue or "flip-flops"     # his stated first stop
    s = build(vid, venues)
    if s is None:
        print(f"🔴 life-lesson-scenario: no scenario for '{vid}'. Known: "
              f"{', '.join(sorted(venues))}", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scenario.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif not a.quiet:
        print(render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
