#!/usr/bin/env python3
"""RAG-9 — retrieval measured, not asserted.

THE TICKET: "The assistant answers from last year's docs. Make it answer from the current ones."
  chunk the corpus · embed it · answer with citations by chunk id · measure hit@k · defend the chunk size.

WHY THIS IS A REAL MEASUREMENT
  · The corpus is a real published textbook (817,656 chars, 186 sections) — not a toy.
  · Every question's answer is a VERIFIED SUBSTRING of the corpus. If the string is not in the corpus the
    question is dropped, not silently scored 0 — a question whose answer does not exist measures nothing.
  · A hit is deterministic: the retrieved chunk either contains the answer string or it does not.
  · Two chunking strategies and TWO embedding models are compared, so "which" is answered by counts.

THE FINDING THIS IS BUILT TO EXPOSE
  An English-only embedding model looks fine on English questions and fails on Devanagari ones. The corpus is
  Devanagari + English. Testing only an English model would have produced a confident wrong answer to
  "does our retrieval work" — so both are run and the contrast is the result.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys
import unicodedata
import zipfile

EPUB = pathlib.Path("/opt/data/profiles/arthur/cache/scratch/nepali-textbook.epub")
OUT = pathlib.Path("/opt/data/profiles/arthur/cache/rag9")
DEV = re.compile(r"[\u0900-\u097F]")

# Question → the exact substring that must appear in the retrieved chunk for it to count as a hit.
# Written by reading the book. Verified against the corpus at load time; failures are DROPPED and reported.
QUESTIONS = [
    ("How do you say 'I read a book' in Nepali?",        "म किताब पढ्छु"),
    ("What is the Nepali word for 'where'?",             "कहाँ"),
    ("How do you say 'I need water' in Nepali?",         "मलाई पानी चाहिन्छ"),
    ("How do you say 'I am not Canadian' in Nepali?",    "म क्यानेडियन होइन"),
    ("What is the polite form of 'how are you'?",        "तपाईंलाई कस्तो छ"),
    ("How do you say 'turn right' in Nepali?",           "दायाँ मोड्नुहोस्"),
    ("What does 'धन्यवाद' mean?",                        "धन्यवाद"),
    ("How do you say 'I liked the tea' in Nepali?",      "मलाई चिया मन पर्‍यो"),
    ("How do you say 'go straight' in Nepali?",          "सीधा जानुहोस्"),
    ("What is the Nepali for 'I was at home'?",          "म घरमा थिएँ"),
    ("How do you say 'these books are' in Nepali?",      "यी किताबहरू हुन्"),
    ("Which verb means 'to be' in Nepali?",              "हुनु"),
]


QUESTIONS_NE = [
    ("पानी चाहिन्छ भन्ने वाक्य कसरी लेखिन्छ?",        "मलाई पानी चाहिन्छ"),
    ("'धन्यवाद' को अर्थ के हो?",                       "धन्यवाद"),
    ("घरमा थिएँ भन्ने वाक्य कुन पाठमा छ?",             "म घरमा थिएँ"),
    ("किताबहरू हुन् भन्ने वाक्य कसरी बनाउँछ?",        "यी किताबहरू हुन्"),
    ("दायाँ मोड्नुहोस् भन्ने कहाँ पढाइन्छ?",           "दायाँ मोड्नुहोस्"),
    ("चिया मन पर्‍यो भन्ने कसरी भन्छ?",                "मलाई चिया मन पर्‍यो"),
    ("काठमाडौंसम्म जान्छु भन्ने वाक्य कसरी बन्छ?",    "काठमाडौंसम्म"),
    ("बजार नजिक छ भन्ने कसरी भन्छ?",                  "बजार नजिक छ"),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    return re.sub(r"\s+", " ", s).strip()


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


def load_corpus() -> list[dict]:
    z = zipfile.ZipFile(EPUB)
    docs = []
    for n in sorted(z.namelist()):
        if not n.lower().endswith((".xhtml", ".html")):
            continue
        t = doc_text(z, n)
        if len(t) < 200:
            continue
        docs.append({"id": n.split("/")[-1].replace(".xhtml", ""), "text": t})
    return docs


def chunk_fixed(docs: list[dict], size: int = 1200, overlap: int = 200) -> list[dict]:
    """Fixed-character windows. Simple, blind to structure — the baseline everyone ships."""
    out = []
    for d in docs:
        t = d["text"]
        i = 0
        while i < len(t):
            piece = t[i:i + size]
            if len(piece.strip()) >= 120:
                out.append({"id": f"{d['id']}#c{i}", "text": piece, "doc": d["id"]})
            i += size - overlap
    return out


def chunk_structural(docs: list[dict], max_chars: int = 2600) -> list[dict]:
    """One chunk per document, split only where a document exceeds max_chars — respects section boundaries.

    A textbook section is a semantic unit: the table, its header and its example sentences belong together.
    Splitting mid-table is what makes retrieval return a row with no column header.
    """
    out = []
    for d in docs:
        t = d["text"]
        if len(t) <= max_chars:
            out.append({"id": d["id"], "text": t, "doc": d["id"]})
            continue
        # split on blank-line-ish boundaries, packing up to max_chars — never mid-line
        lines = [l for l in t.splitlines() if l.strip()]
        buf: list[str] = []
        n = 0
        k = 0
        for l in lines:
            if n + len(l) > max_chars and buf:
                out.append({"id": f"{d['id']}#p{k}", "text": "\n".join(buf), "doc": d["id"]})
                k += 1
                buf, n = [], 0
            buf.append(l)
            n += len(l) + 1
        if buf:
            out.append({"id": f"{d['id']}#p{k}", "text": "\n".join(buf), "doc": d["id"]})
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    docs = load_corpus()
    total_chars = sum(len(d["text"]) for d in docs)
    print(f"  corpus: {len(docs)} sections · {total_chars:,} chars ≈ {total_chars//4:,} tokens")

    # ── verify every question's answer actually exists, and say which survive ────────────────────
    corpus_all = norm("\n".join(d["text"] for d in docs))
    QSETS = {}
    for name, qs in (("en", QUESTIONS), ("ne", QUESTIONS_NE)):
        live, dropped = [], []
        for q, a in qs:
            (live if norm(a) in corpus_all else dropped).append((q, a))
        QSETS[name] = live
        print(f"  questions[{name}]: {len(qs)} written · {len(live)} verified · {len(dropped)} DROPPED")
        for q, a in dropped:
            print(f"    🔴 dropped (answer not in corpus): {q}  ← {a}")

    chunkers = {"fixed-1200": chunk_fixed(docs), "structural-2600": chunk_structural(docs)}
    for name, ch in chunkers.items():
        avg = sum(len(c["text"]) for c in ch) / max(1, len(ch))
        print(f"  chunking {name:16s} → {len(ch):5d} chunks · avg {avg:6.0f} chars")

    from fastembed import TextEmbedding
    import numpy as np

    MODELS = [("multilingual", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
              ("english-only", "BAAI/bge-small-en-v1.5")]

    results = {}
    for label, model_name in MODELS:
        print(f"\n  ── {label}: {model_name}")
        try:
            model = TextEmbedding(model_name=model_name)
        except Exception as e:
            print(f"    🔴 model unavailable: {type(e).__name__}: {str(e)[:120]}")
            results[label] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
            continue

        for cname, ch in chunkers.items():
            try:
                cm = np.array(list(model.embed([c["text"] for c in ch])), dtype="float32")
            except Exception as e:
                print(f"    🔴 {cname}: embed failed {type(e).__name__}: {str(e)[:100]}")
                continue
            cm /= (np.linalg.norm(cm, axis=1, keepdims=True) + 1e-9)
            for qset, live in QSETS.items():
              if not live: continue
              qm = np.array(list(model.embed([q for q, _ in live])), dtype="float32")
              qm /= (np.linalg.norm(qm, axis=1, keepdims=True) + 1e-9)
              sims = qm @ cm.T
              ranks = []
              for qi, (q, ans) in enumerate(live):
                order = np.argsort(-sims[qi])
                r = None
                for pos, idx in enumerate(order[:10], start=1):
                    if norm(ans) in norm(ch[idx]["text"]):
                        r = pos; break
                ranks.append(r)
              hit1 = sum(1 for r in ranks if r == 1)
              hit3 = sum(1 for r in ranks if r and r <= 3)
              hit5 = sum(1 for r in ranks if r and r <= 5)
              mrr = sum(1.0 / r for r in ranks if r) / len(ranks)
              results.setdefault(label, {}).setdefault(cname, {})[qset] = {
                  "n": len(live), "chunks": len(ch), "hit@1": hit1, "hit@3": hit3,
                  "hit@5": hit5, "mrr": round(mrr, 3),
                  "misses": [live[i][0] for i, r in enumerate(ranks) if r is None][:4],
              }
              print(f"    {cname:16s} [{qset}] chunks {len(ch):5d} · hit@1 {hit1:2d}/{len(live)} · "
                    f"hit@3 {hit3:2d}/{len(live)} · hit@5 {hit5:2d}/{len(live)} · MRR {mrr:.3f}")

    # ⚠️ TIMESTAMPED WRITE — measured need, 2026-10-28: a STALE run of this same script finished after a
    # newer one and could have overwritten a completed matrix with the older single-language shape. Results
    # now go to a run-scoped file first, then results.json — so a clobber costs nothing and runs are diffable.
    import time as _t
    stamp = _t.strftime("%Y%m%dT%H%M%SZ", _t.gmtime())
    payload = json.dumps(
        {"corpus": {"sections": len(docs), "chars": total_chars,
                    "est_tokens": total_chars // 4},
         "questions": {k: len(v) for k, v in QSETS.items()},
         "results": results,
         "schema": 2,
         "run_at": stamp}, indent=1, ensure_ascii=False)
    (OUT / f"results-{stamp}.json").write_text(payload)
    (OUT / "results.json").write_text(payload)
    print(f"\n  ✅ {OUT/f'results-{stamp}.json'}")
    print(f"  ✅ {OUT/'results.json'}  (schema 2 — carries the query-language matrix)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
