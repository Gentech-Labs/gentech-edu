#!/usr/bin/env python3
"""EVAL-7 — run the same golden set through two prompt variants and report the DELTA IN COUNTS.

THE TICKET: "Before we change the prompt, prove the change does not make it worse."

WHY THIS IS A REAL EVAL AND NOT A DEMO
  · The truth is external: 127 phrase pairs printed in a published textbook, not model output.
  · The grader is deterministic — no model judges the model. Every number is a count you can recount.
  · The two variants share one model, one golden set, one grader. Only the PROMPT differs.
  · n is printed next to every figure. No percentages of a tiny sample dressed as a rate.

WHAT IT MEASURES
  proposed      — units the model returned
  verified      — units whose `src` appears VERBATIM in the chunk (edu-extract.py's own rule)
  fabricated    — proposed − verified. The hallucination count, not a vibe.
  target_recall — golden phrases whose Nepali string the model actually found
  pair_correct  — golden phrases found WITH a correct English gloss
  precision     — pair_correct / verified  (of what it kept, how much is right)

DECISION RULE, written before the run:
  Ship B only if pair_correct is strictly higher AND fabricated does not increase.
  Otherwise keep A. No cherry-picking a single favourable case.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import pathlib
import re
import sys
import time
import unicodedata
import urllib.request
import uuid

ENV = pathlib.Path("/opt/data/profiles/arthur/.env")
GOLDEN = pathlib.Path("/opt/data/.obsidian-vault/10-Labs/skills-distribution/edu/data/eval/golden-extract-ne.json")
OUTDIR = pathlib.Path("/opt/data/profiles/arthur/cache/eval7")
URL = "https://opencode.ai/zen/go/v1/chat/completions"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

# ── VARIANT A — the prompt currently shipping in edu-extract.py, verbatim ─────────────────────────
PROMPT_A = """You are extracting vocabulary from a language-learning document. The document may be
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

# ── VARIANT B — the candidate. Each change answers a measured defect in A. ────────────────────────
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
   instructions, page numbers, and isolated single-word vocabulary glossaries where no sentence is given.
6. If text is garbled so a pair cannot be read with confidence, SKIP it. Silence beats a guess.
7. Include "rom" ONLY if the document itself gives a transliteration for that row.

Return STRICT JSON, no prose:
{{"units":[{{"target":"<phrase in {lang}>","en":"<english>","rom":"<transliteration or empty>","src":"<exact line>"}}]}}"""

VARIANTS = {"A": PROMPT_A, "B": PROMPT_B}
STOP = {"the", "a", "an", "is", "are", "am", "to", "of", "in", "on", "at", "and", "or", "i", "you",
        "he", "she", "it", "we", "they", "my", "your", "his", "her", "this", "that", "these",
        "those", "not", "do", "does", "did", "be", "was", "were", "have", "has"}


def api_key() -> str:
    for line in ENV.read_text().splitlines():
        if line.strip().startswith("OPENCODE_GO_API_KEY="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return v
    raise SystemExit("🔴 OPENCODE_GO_API_KEY absent")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def content(s: str) -> set[str]:
    words = re.findall(r"[a-z']+", (s or "").lower())
    return {w for w in words if w not in STOP and len(w) > 1}


def call_model(prompt: str, chunk: str, model: str, max_tokens: int = 14000) -> tuple[list[dict], str]:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt.format(lang="Nepali", chunk=chunk)}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "x-opencode-session": str(uuid.uuid4()),
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=600) as r:
        payload = json.load(r)
    msg = (payload.get("choices") or [{}])[0].get("message", {})
    text = msg.get("content") or ""
    finish = (payload.get("choices") or [{}])[0].get("finish_reason")
    if not text and msg.get("reasoning_content"):
        text = msg["reasoning_content"]      # a reasoning model that never emitted content

    # strip code fences — the model wraps JSON in ```json ... ```
    body = re.sub(r"^\s*```(?:json)?\s*", "", text.strip())
    body = re.sub(r"\s*```\s*$", "", body)

    units: list[dict] = []
    try:
        units = json.loads(body).get("units", [])
    except Exception:
        # salvage complete objects if truncated (finish_reason == length)
        for m in re.finditer(r"\{.*?\"target\".*?\}", body, re.S):
            try:
                u = json.loads(m.group(0))
                if "target" in u:
                    units.append(u)
            except Exception:
                continue
    return units, (finish or "")


def grade(case: dict, units: list[dict]) -> dict:
    chunk = case["chunk"]
    nchunk = unicodedata.normalize("NFC", chunk)

    verified, fabricated = [], 0
    for u in units:
        src = unicodedata.normalize("NFC", (u.get("src") or "").strip())
        if src and src in nchunk:
            verified.append(u)
        else:
            fabricated += 1

    golden = case["golden"]
    target_hits, pair_hits = 0, 0
    for g in golden:
        gt = norm(g["target"])
        gg = content(g["gloss"])
        # BEST match, not first. Taking the first substring match let a one-word unit
        # ('यो' -> 'this') shadow the correct longer unit ('यो किताब' -> 'this book') and
        # scored a perfect extraction as 0/14. Score every candidate on gloss overlap.
        best, best_score = None, -1.0
        for u in verified:
            ut = norm(u.get("target", ""))
            if not ut:
                continue
            if not (gt in ut or ut in gt):
                continue
            ug = content(u.get("en", ""))
            score = (len(ug & gg) / len(gg)) if gg else 0.0
            if score > best_score:
                best, best_score = u, score
        if best is None:
            continue
        target_hits += 1
        if best_score >= 0.5:
            pair_hits += 1

    return {
        "proposed": len(units),
        "verified": len(verified),
        "fabricated": fabricated,
        "golden_total": len(golden),
        "target_hits": target_hits,
        "pair_correct": pair_hits,
        "precision": round(pair_hits / len(verified), 3) if verified else None,
        "recall": round(pair_hits / len(golden), 3) if golden else None,
    }


def selftest() -> int:
    """A grader nobody has tested is a random number generator with a confident voice."""
    case = {"chunk": "यो किताब हो।\n yo kitāb ho. \n This is a book.\n",
            "golden": [{"target": "यो किताब हो।", "gloss": "This is a book."}]}
    trials = [
        ("exact correct", [{"target": "यो किताब हो।", "en": "This is a book.", "src": "यो किताब हो।"}], 1, 1, 0),
        ("correct but a decoy single word also present",
         [{"target": "यो", "en": "this", "src": "यो किताब हो।"},
          {"target": "यो किताब हो।", "en": "This is a book.", "src": "यो किताब हो।"}], 1, 1, 0),
        ("wrong gloss", [{"target": "यो किताब हो।", "en": "That is a house.", "src": "यो किताब हो।"}], 1, 0, 0),
        ("fabricated src", [{"target": "यो किताब हो।", "en": "This is a book.", "src": "not in chunk"}], 0, 0, 1),
        ("nothing returned", [], 0, 0, 0),
    ]
    bad = 0
    for name, units, exp_t, exp_p, exp_f in trials:
        g = grade(case, units)
        ok = (g["target_hits"] == exp_t and g["pair_correct"] == exp_p and g["fabricated"] == exp_f)
        print(f"  {'✅' if ok else '🔴'} {name:46s} targets={g['target_hits']} pairs={g['pair_correct']} "
              f"fab={g['fabricated']}  (want {exp_t}/{exp_p}/{exp_f})")
        bad += 0 if ok else 1
    print(f"\n  {'ALL PASS' if bad == 0 else str(bad) + ' FAILED'}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--model", default="kimi-k2.7-code")
    ap.add_argument("--variants", default="A,B")
    ap.add_argument("--cases", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4,
                    help="parallel model calls; 1 = serial. Wall clock is the only thing this changes.")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    data = json.loads(GOLDEN.read_text())
    cases = data["cases"][:a.cases]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    results_path = OUTDIR / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}

    lock = threading.Lock()

    todo = []
    for vname in a.variants.split(","):
        v = vname.strip()
        for c in cases:
            if results.get(f"{v}:{c['id']}", {}).get("ok"):
                print(f"  {v}:{c['id']} cached — skipping")
                continue
            todo.append((v, c))

    def work(v: str, c: dict) -> tuple[str, dict]:
        key = f"{v}:{c['id']}"
        t0 = time.time()
        try:
            units, finish = call_model(VARIANTS[v], c["chunk"], a.model)
            g = grade(c, units)
            rec = {"ok": True, "finish": finish, "secs": round(time.time() - t0, 1), **g,
                   "units": [{"target": u.get("target"), "en": u.get("en"),
                              "keys": sorted(u.keys())} for u in units][:30]}
        except Exception as e:
            rec = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        with lock:
            results[key] = rec
            results_path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
            if rec.get("ok"):
                print(f"  {key}  proposed {rec['proposed']:3d} · verified {rec['verified']:3d} · "
                      f"fab {rec['fabricated']:3d} · pair {rec['pair_correct']:3d}/{rec['golden_total']:3d} · "
                      f"{rec['secs']}s")
            else:
                print(f"  {key} 🔴 {rec['error'][:90]}")
        return key, rec

    if a.workers <= 1:
        for v, c in todo:
            work(v, c)
    else:
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(work, v, c) for v, c in todo]
            for f in as_completed(futs):
                f.result()

    # ── aggregate ────────────────────────────────────────────────────────────────────────────────
    agg = {}
    for vname in a.variants.split(","):
        v = vname.strip()
        rows = [results[f"{v}:{c['id']}"] for c in cases
                if results.get(f"{v}:{c['id']}", {}).get("ok")]
        if not rows:
            continue
        agg[v] = {
            "cases_run": len(rows),
            "proposed": sum(r["proposed"] for r in rows),
            "verified": sum(r["verified"] for r in rows),
            "fabricated": sum(r["fabricated"] for r in rows),
            "golden_total": sum(r["golden_total"] for r in rows),
            "pair_correct": sum(r["pair_correct"] for r in rows),
            "target_hits": sum(r["target_hits"] for r in rows),
        }
        n = agg[v]
        n["precision"] = round(n["pair_correct"] / n["verified"], 3) if n["verified"] else None
        n["recall"] = round(n["pair_correct"] / n["golden_total"], 3) if n["golden_total"] else None

    summary = {"model": a.model, "n_cases": len(cases), "aggregate": agg,
               "results_path": str(results_path)}
    (OUTDIR / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print("\n── AGGREGATE (counts) ──")
    for v, n in agg.items():
        print(f"  {v}: {n['cases_run']} cases · proposed {n['proposed']} · verified {n['verified']} · "
              f"fabricated {n['fabricated']} · correct pairs {n['pair_correct']}/{n['golden_total']} "
              f"· precision {n['precision']} · recall {n['recall']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
