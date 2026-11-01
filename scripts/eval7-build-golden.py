#!/usr/bin/env python3
"""Build EVAL-7's golden set — v2, anchored on TABLE HEADERS, not on row shape.

WHAT WENT WRONG IN v1 (kept as a pitfall, because it is the whole lesson):
  v1 accepted any 4 consecutive lines where line 1 had Devanagari and line 4 had Latin. That matched
  PROSE, not tables, and produced 161 "golden pairs" like:
      "The final उ ( u ) is not dropped." → "Core Takeaway"        (a sentence and a heading)
      "बस-" → "bolnu"                                              (a verb stem and a different verb)
  A garbage golden set is WORSE than no golden set: it launders falsehood into the word "truth", and
  every number computed against it is confidently wrong. That is the exact failure class this eval exists
  to catch — and I nearly shipped it.

v2 RULES (each one closes a hole v1 had):
  1. A pair only counts if it sits AFTER a real 4-column table header (Nepali / Transliteration /
     Literal / English). Prose can no longer be parsed as a table.
  2. Within a table, rows are strictly 4 lines, and parsing STOPS at the first line that breaks the shape.
     No resynchronising — a table that goes ragged is a table I do not trust.
  3. The target must be a PHRASE (>=2 Devanagari words, or contain a danda) — a bare stem like "बस-" is
     vocabulary, not an extractable phrase pair, and mixing the two corrupts the metric.
  4. The gloss must be sentence-like English (>=2 Latin words, lowercase present) — not a heading.
  5. One chunk per chapter, so the golden set is not secretly one document.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import zipfile

EPUB = pathlib.Path("/opt/data/profiles/arthur/cache/scratch/nepali-textbook.epub")
OUT = pathlib.Path("/opt/data/.obsidian-vault/10-Labs/skills-distribution/edu/data/eval")
N_CASES = 10
CHUNK_CHARS = 2600
DEV = re.compile(r"[\u0900-\u097F]")


def doc_text(z: zipfile.ZipFile, name: str) -> str:
    s = z.read(name).decode("utf-8", "ignore")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|li|h[1-6]|tr|td|th)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _is_phrase(t: str) -> bool:
    if "।" in t:
        return True
    return len([w for w in t.split() if DEV.search(w)]) >= 2


DIACRITIC = re.compile(r"[\u0101\u012b\u016b\u1e6d\u1e0d\u1e47\u1e45\u00f1\u015b\u1e63\u1e25\u0303]")


def _is_gloss(g: str) -> bool:
    if DEV.search(g):
        return False
    # A romanisation is not an English gloss. Caught on review: case-06 had
    # 'मलाई थकाइ लागेको छ।' -> 'tapāī̃lāī bhok lāgeko cha?' — a table row slipped by one.
    if DIACRITIC.search(g):
        return False
    words = [w for w in g.split() if re.search(r"[A-Za-z]", w)]
    if len(words) < 2:
        return False
    if g[0].isupper() and g.endswith(":") is False and len(words) < 3 and not re.search(r"[.!?]$", g):
        return False  # looks like a heading
    return True


def table_pairs(text: str) -> list[dict]:
    """Only rows inside a header-confirmed table. Stop at the first ragged line.

    Tables in this book are 3-column (Nepali / Transliteration / English) or 4-column (… / Literal /
    English). The HEADER BLOCK tells us the width, so one parser handles both instead of assuming four
    and skipping every three-column table.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out: list[dict] = []
    i = 0
    while i < len(lines):
        win = lines[i:i + 6]
        joined = " | ".join(l.lower() for l in win)
        if ("nepali" in joined or "देवनागरी" in joined) and "transliteration" in joined and "english" in joined:
            start = next((k for k, l in enumerate(win) if "nepali" in l.lower() or "देवनागरी" in l), None)
            end = next((k for k, l in enumerate(win) if "english" in l.lower()), None)
            if start is None or end is None or end <= start:
                i += 1
                continue
            width = end - start + 1              # 3 or 4
            j = i + end + 1
            while j + width - 1 < len(lines):
                cells = lines[j:j + width]
                t, g = cells[0], cells[-1]
                if not (DEV.search(t) and _is_phrase(t) and _is_gloss(g)):
                    break                        # ragged: stop, never resynchronise
                out.append({"target": t,
                            "roman": cells[1] if width >= 3 else "",
                            "literal": cells[-2] if width >= 4 else "",
                            "gloss": g})
                j += width
            i = j
        else:
            i += 1
    seen, clean = set(), []
    for p in out:
        if p["target"] in seen:
            continue
        seen.add(p["target"])
        clean.append(p)
    return clean


def main() -> int:
    z = zipfile.ZipFile(EPUB)
    names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html"))]
    scored = []
    for n in names:
        t = doc_text(z, n)
        if len(DEV.findall(t)) < 300:
            continue
        pairs = table_pairs(t)
        if len(pairs) < 3:
            continue
        scored.append((len(pairs), n, t, pairs))
    scored.sort(reverse=True)

    cases = []
    for npairs, n, t, pairs in scored:            # ONE chunk per chapter — rule 5
        best = None
        for c in range(0, len(t), CHUNK_CHARS):
            chunk = t[c:c + CHUNK_CHARS]
            if len(chunk) < 900:
                continue
            inside = [p for p in pairs if p["target"] in chunk]
            if len(inside) >= 2 and (best is None or len(inside) > len(best[2])):
                best = (chunk, inside, inside)
        if not best:
            continue
        cases.append({"id": f"case-{len(cases)+1:02d}", "doc": n.split("/")[-1],
                      "chunk": best[0], "golden": best[1]})
        if len(cases) >= N_CASES:
            break

    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "_what": "EVAL-7 golden set — phrase pairs from the UBC open-access Nepali textbook.",
        "_source": "Introduction to the Nepali Language (UBC, 2026), CC BY-NC-SA 4.0, doi 10.14288/0yy1-0x56",
        "_why": "An eval needs a truth that is not the model. These pairs are printed in the source tables.",
        "_extraction_rule": "Only rows inside a header-confirmed 4-column table; phrase targets only; "
                            "sentence-like glosses only; one chunk per chapter.",
        "_v1_pitfall": "v1 matched row SHAPE without a header and produced 161 fabricated pairs "
                       "('The final उ (u) is not dropped.' -> 'Core Takeaway'). A garbage golden set "
                       "is worse than none: it launders falsehood into the word 'truth'.",
        "_reviewed": None,
        "n_cases": len(cases),
        "cases": cases,
    }
    p = OUT / "golden-extract-ne.json"
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tot = sum(len(c["golden"]) for c in cases)
    print(f"  {len(cases)} cases · {tot} golden pairs · {len(scored)} chapters had usable tables")
    for c in cases:
        print(f"    {c['id']}  {c['doc'][:46]:48s} {len(c['golden']):3d} pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
