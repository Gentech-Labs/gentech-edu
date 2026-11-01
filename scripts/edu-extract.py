#!/usr/bin/env python3
"""edu-extract.py — the LLM extraction pass. Regex reads a TABLE; this reads a BOOK.

Jordan, 2026-10-26: "eat the meat and spit out the bones" — and the bones here are honest:
`edu-ingest.py` pulled 191 units out of a 284-page OCR'd coursebook, with rows like
`be afraid → Dar laagnu, chew (food, betel)` (scrambled) and `Lesson F ocus → …`. Regex cannot
read a book. A model can.

THE RULE THAT MAKES THIS SAFE — and it is the whole design:

    **The model NEVER invents a phrase. It only QUOTES the source, with a line reference.**

Every unit it returns must carry `src`, a verbatim line from the source text. This script then
**verifies that line actually appears in the source** and DROPS any unit whose evidence is not
found. A model that fabricates a phrase produces text that is not in the document — and that is
exactly what the verifier catches. Nothing here is trusted because a model said it; it is trusted
because it can be pointed at.

USAGE
  python3 edu-extract.py --dialect ne-NP --source <file|pdf|url> [--chunk 6000] [--max-chunks 4] [--write]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
DATA = SKILL_DIR / "data"
SCRIPTS = SKILL_DIR / "scripts"


def _seat() -> str:
    parts = pathlib.Path(__file__).resolve().parts
    return parts[parts.index("profiles") + 1] if "profiles" in parts else "gentech"


SEAT = _seat()
PROFILE = pathlib.Path("/opt/data/profiles") / SEAT


def api_key() -> str:
    import os
    if os.environ.get("OPENCODE_GO_API_KEY"):
        return os.environ["OPENCODE_GO_API_KEY"].strip()
    env = PROFILE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENCODE_GO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("🔴 no OPENCODE_GO_API_KEY for this seat")


PROMPT = """You are extracting vocabulary from a language-learning document. The document may be
OCR'd, so text can be misaligned or garbled.

TARGET LANGUAGE : {lang}
DOCUMENT CHUNK  :
---
{chunk}
---

Extract ONLY phrase pairs that are genuinely present in the chunk: a phrase in {lang} and its
English meaning, as the document states them.

ABSOLUTE RULES
1. NEVER invent a phrase, a translation, or a reading. If the chunk has no clear pairs, return [].
2. Every unit MUST include "src": the EXACT line from the chunk (copy it character for character)
   that contains the evidence. A unit whose src is not literally in the chunk will be deleted.
3. If the document's text is garbled so that a pair cannot be read with confidence, SKIP it. Silence
   beats a guess.
4. Do not translate rows that are titles, page numbers, grammar-table rows, or lesson headings.
5. Include "rom" (transliteration) ONLY if the document itself gives it.

Return STRICT JSON, no prose:
{{"units":[{{"target":"<phrase in {lang}>","en":"<english>","rom":"<transliteration or empty>","src":"<exact line>"}}]}}"""

# ── VARIANT B — MEASURED BETTER, NOT YET DEFAULT. EVAL-7, 2026-10-28 ────────────────────────────────
# Measured on a 127-pair hand-reviewed golden set from the UBC Nepali textbook, model held constant:
#   A: 97/127 correct pairs (76.4% recall, 58.1% precision), 0 fabricated
#   B: 118/127 correct pairs (92.9% recall, 70.7% precision), 1 fabricated
# B found 21 more pairs and failed on ZERO chapters where A failed on two. It regressed on one chapter
# (case-08, 12 -> 8) by being conservative. B produced 1 unverifiable unit out of 168 — the verifier
# below deletes those, which is why it is not a ship blocker but IS why this is a flag and not the default.
# Select with --prompt b. Full report: EDU/workload/2026-10-28-eval7-report.md
PROMPT_B = """You are extracting phrase pairs from a language-learning textbook chapter.

TARGET LANGUAGE : {lang}
DOCUMENT CHUNK  :
---
{chunk}
---

The chapters contain TABLES. A table header tells you the columns, for example:
    Nepali | Transliteration | Literal (word-by-word) | English
    Nepali | Transliteration | English
Each DATA ROW of such a table is one phrase pair and IS the material to extract.

ABSOLUTE RULES
1. EXTRACT every data row of every vocabulary and example table. A table row is the primary source of
   phrase pairs in this document — do not skip it because it is a table.
2. The English meaning is the ENGLISH column. Never use the Transliteration column or the
   Literal (word-by-word) column as the English meaning.
3. NEVER invent a phrase, a translation, or a reading. If the chunk has no table rows, return [].
4. Every unit MUST include "src": the EXACT line from the chunk (copy it character for character)
   that contains the {lang} phrase. A unit whose src is not literally in the chunk will be deleted.
5. SKIP only: the table header itself, noun-class labels, chapter/section headings, exercise
   instructions, page numbers, and isolated single-word glossaries where no sentence is given.
6. If text is garbled so a pair cannot be read with confidence, SKIP it. Silence beats a guess.
7. Include "rom" ONLY if the document itself gives a transliteration for that row.

Return STRICT JSON, no prose:
{{"units":[{{"target":"<phrase in {lang}>","en":"<english>","rom":"<transliteration or empty>","src":"<exact line>"}}]}}"""

# MODEL DEFAULT CHANGED 2026-10-28 — the old default could not work. MEASURED on the rail:
#   deepseek-v4-flash    -> HTTP 410 ModelDeprecated ("has been ...")
#   deepseek-v4.1-flash  -> HTTP 403
#   glm-4.7, gpt-5-mini  -> HTTP 400 "Model is unavailable"
#   kimi-k2.7-code       -> HTTP 200, clean JSON
# A default that cannot answer is worse than no default: every run fails and reads like a document problem.
def call_model(chunk: str, lang: str, model: str = "kimi-k2.7-code",
               prompt: str = None) -> list[dict]:
    """One chunk in, candidate units out. Returns [] on any failure — never a partial fabrication."""
    import uuid
    import urllib.request
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": (prompt or PROMPT).format(lang=lang, chunk=chunk)}],
        # NO `temperature` — MEASURED 2026-10-28: kimi-k2.7-code rejects temperature:0 with
        # HTTP 400 "invalid temperature", which reads like a broken model and is a rejected field.
        # The eval harness never sent it and worked; the engine sent it and failed. Same prompt,
        # same model, one field different.
        # NO `response_format` — MEASURED 2026-10-26: with `{"type":"json_object"}` this rail returns
        # HTTP 200 and an EMPTY content field (0 chars), which then fails JSON parsing and looks like
        # a model failure. Without it the same prompt returns clean JSON. The prompt already demands
        # strict JSON, so the flag only breaks things.
        "max_tokens": 14000,          # room for reasoning + a full JSON array; truncated JSON is the
                                     # failure mode, not a short answer
        "reasoning_effort": "low",   # extraction is transcription, not deduction — measured: this
                                     # model burned 1,332 reasoning tokens of a 2,000 budget and
                                     # returned `finish_reason: "length"` with half a JSON object
    }).encode()
    req = urllib.request.Request("https://opencode.ai/zen/go/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {api_key()}",
                                          "Content-Type": "application/json",
                                          # MEASURED 2026-10-26: without a browser-like UA Cloudflare
                                          # answers "error code: 1010" for every model — which reads
                                          # like a bad key and is not. The UA is the door.
                                          "User-Agent": "Mozilla/5.0 (compatible; gentech-edu/1.0)",
                                          # The rail REFUSES a request with no session header:
                                          # `{"type":"MissingSessionID"}` — documented in the
                                          # model-routing skill and already used by profiles/arthur/
                                          # scripts/sr-audit.py. Without it the call 400s.
                                          "x-opencode-session": str(uuid.uuid4()),
                                          "Accept": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
        ch = r["choices"][0]
        txt = (ch["message"].get("content") or "")
        txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
        if not txt:
            print("  ⚠️  model returned EMPTY content — chunk skipped", file=sys.stderr)
            return []
        try:
            return json.loads(txt).get("units") or []
        except json.JSONDecodeError:
            # SALVAGE rather than drop: a truncated array is still a list of verifiable quotes, and
            # every unit still has to pass the src gate. Keep only complete objects.
            objs = re.findall(r"\{[^{}]*\}", txt)
            units = []
            for o in objs:
                try:
                    units.append(json.loads(o))
                except Exception:
                    continue
            print(f"  ⚠️  truncated JSON (finish={ch.get('finish_reason')}) — salvaged "
                  f"{len(units)} complete object(s), each still gated on its src", file=sys.stderr)
            return units
    except Exception as e:
        detail = ""
        try:
            detail = e.read()[:200].decode("utf-8", "replace")  # type: ignore[attr-defined]
        except Exception:
            pass
        print(f"  ⚠️  model call failed ({type(e).__name__}: {str(e)[:90]} {detail[:120]}) — chunk skipped",
              file=sys.stderr)
        return []


def verify(units: list[dict], source: str) -> tuple[list[dict], list[dict]]:
    """THE GATE. A unit survives only if its `src` is literally in the source text.

    This is what makes an LLM safe to use for this job: inventing a phrase produces a `src` that
    cannot be found, and a not-found src is a rejection. The model does not get the benefit of the
    doubt — the document does.
    """
    norm = re.sub(r"\s+", " ", source)
    kept, dropped = [], []
    for u in units:
        t = (u.get("target") or "").strip()
        e = (u.get("en") or "").strip()
        src = re.sub(r"\s+", " ", (u.get("src") or "")).strip()
        if not t or not e:
            dropped.append({"unit": u, "why": "missing target or english"})
            continue
        if len(src) < 4:
            dropped.append({"unit": u, "why": "no src cited"})
            continue
        if src not in norm:
            dropped.append({"unit": u, "why": "src NOT FOUND in source — fabricated or paraphrased"})
            continue
        if t not in norm and t not in src:
            dropped.append({"unit": u, "why": "target does not appear in the source"})
            continue
        kept.append(u)
    return kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialect", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--chunk", type=int, default=6000)
    ap.add_argument("--max-chunks", type=int, default=4)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--prompt", choices=["a", "b"], default="b",
                    help="extraction prompt. DEFAULT IS 'b' since 2026-10-28 — measured on the EVAL-7 "
                         "golden set (127 hand-reviewed pairs): b 118/127 vs a 97/127 correct pairs, and "
                         "a returned nothing on 2 of 10 chapters where b returned nothing on none. "
                         "b produced 1 unverifiable unit in 168, which the verbatim-src verifier deletes. "
                         "'a' is kept selectable for rollback. See EDU/workload/2026-10-28-eval7-report.md")
    a = ap.parse_args()

    # reuse the ingester's readers so PDF/EPUB/URL/video all work here too
    sys.path.insert(0, str(SCRIPTS))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ing", SCRIPTS / "edu-ingest.py")
    ing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ing)

    text, provenance, segments = ing.read_source(a.source)
    text = ing.clean_text(text)
    lang = {"ne-NP": "Nepali", "th-TH": "Thai", "es-DO": "Spanish"}.get(a.dialect, a.dialect)

    # chunk on paragraph boundaries so a pair never gets cut in half
    paras = [p for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > a.chunk and cur:
            chunks.append(cur); cur = p
        else:
            cur += ("\n" if cur else "") + p
    if cur:
        chunks.append(cur)
    chunks = chunks[: a.max_chunks]

    print(f"source   : {provenance}")
    print(f"text     : {len(text):,} chars → {len(chunks)} chunk(s) × ≤{a.chunk:,} (max {a.max_chunks})")
    print(f"language : {lang}")

    raw: list[dict] = []
    for i, c in enumerate(chunks, 1):
        got = call_model(c, lang, prompt=(PROMPT_B if a.prompt == "b" else PROMPT))
        print(f"  chunk {i}: model proposed {len(got)}")
        raw += got

    kept, dropped = verify(raw, text)
    print(f"\nGATE — proposed {len(raw)} · kept {len(kept)} · dropped {len(dropped)}")
    for d in dropped[:6]:
        print(f"  ✗ {d['unit'].get('target','?')[:36]:38s} {d['why']}")

    if not kept:
        print("\n🔴 NOTHING SURVIVED THE GATE — no pack written. The source may not contain readable")
        print("   pairs, or the model could not quote its evidence. Silence beats an invented lesson.")
        return 3

    print("\nkept (each with a verifiable line from the source):")
    for u in kept[:10]:
        print(f"  {u['target'][:34]:36s} → {u['en'][:44]:46s}"
              + (f" [{u.get('rom')}]" if u.get("rom") else ""))

    if not a.write:
        print(f"\n(dry run — re-run with --write to emit {DATA / 'phrases' / (a.dialect + '.json')})")
        return 0

    pack = {
        "_what": f"PACK EXTRACTED BY MODEL, EVERY UNIT VERIFIED AGAINST SOURCE — {a.title or provenance}",
        "_generated_by": "edu-extract.py",
        "_source": provenance,
        "_license": "carried from the source reference — confirm before redistributing",
        "_method": ("An LLM read the text and quoted the line for each pair; this script then checked "
                    "that line literally exists in the source. Units whose evidence could not be found "
                    "were DELETED, not stored. The model proposes; the document decides."),
        "_review_required": "Still a candidate list — a human should accept each unit before teaching.",
        "_count": len(kept),
        "dialect": a.dialect,
        "label": a.title or f"{a.dialect} — extracted",
        "phrases": {"extracted": [
            {"ne" if a.dialect.startswith("ne") else "text": u["target"], "en": u["en"],
             **({"rom": u["rom"]} if u.get("rom") else {}), "_src": u.get("src")} for u in kept]},
    }
    out = DATA / "phrases" / f"{a.dialect}-extracted.json"
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1))
    print(f"\n✅ wrote {out} ({len(kept)} verified units, {out.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
