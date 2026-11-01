#!/usr/bin/env python3
"""edu-ingest.py — turn ANY learning material into an EDU pack.

Jordan, 2026-10-18: *"I have a course for Thai... or I can use any type of material as the book and
from the book we can make our own examples. So that way GenTech EDU can also be compatible with any
type of learning material."*

That is the whole feature. This is the bridge: MATERIAL IN -> PACK OUT, where the examples are drawn
from what the brain already knows the learner does.

WHAT IT DOES
  1. Reads a source: a text file, a markdown/PDF-extracted file, or a URL.
  2. Extracts candidate phrase units: a target-language line and its English gloss.
  3. Scores each unit for RELEVANCE against the learner's own corpus (the brain: trips, venues,
     repos, incidents) — so the lesson leads with what he will actually need.
  4. Emits a pack in the engine's shape (`data/phrases/<dialect>.json`), with provenance on every
     unit and the license carried through.

WHAT IT REFUSES TO DO
  - Invent a phrase. Every unit must come from the source text; if the extraction finds nothing, it
    says so and writes nothing.
  - Strip a license. NonCommercial and ShareAlike are copied into the pack's `_license` block so the
    terms travel with the material.
  - Pretend the extraction is teaching. It is a CANDIDATE list; a human (or the fleet's teacher) still
    has to accept it. The output is marked `_review_required`.

USAGE
  python3 edu-ingest.py --dialect ne-NP --learner jordan --source <file-or-url> \\
      [--target-script devanagari|roman|auto] [--license CC-BY-NC-SA] [--title "..."] [--write]

  Without --write it prints a REPORT (what it found, what it ranked, what it refused).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

# ── paths derived from THIS file, so each seat uses its own — same idiom as the engine ────────────
SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
DATA = SKILL_DIR / "data"
VAULT = pathlib.Path("/opt/data/.obsidian-vault")

# The learner's own corpus. These are what make an example "about his life" rather than generic.
CORPUS_SOURCES = [
    VAULT / "00-HQ" / "01-Travel" / "travel-jordan.json",
    DATA / "travel-venues.json",
    DATA / "subjects.json",
]
# Situation keywords: a phrase mentioning one of these is likelier to be usable in that situation.
SITUATION_HINTS = {
    "greeting": ["hello", "hi", "greet", "good morning", "how are you", "thank", "please", "sorry",
                 "goodbye", "see you", "welcome"],
    "workplace": ["work", "shift", "help", "understand", "slow", "again", "name", "meet", "boss",
                  "break", "start", "finish", "同事", "team"],
    "food": ["eat", "food", "water", "tea", "rice", "bill", "menu", "delicious", "hungry", "spicy"],
    "taxi": ["taxi", "go to", "how much", "price", "stop", "hotel"],
    "hotel": ["room", "book", "check", "stay", "night"],
    "airport": ["passport", "tourism", "flight", "luggage", "arrive"],
}

DEVANAGARI = re.compile(r"[\u0900-\u097F]")


DOC_VENV_PY = pathlib.Path("/opt/data/profiles/arthur/cache/scratch/docsvenv/bin/python")
TS_RE = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?[.,]?\d*\s*-->")


def _read_pdf(path: pathlib.Path) -> str:
    """PDF text. Tries pdftotext, then a contained scratch venv (pypdf), then REFUSES.

    MEASURED 2026-10-26 on this host: no pdftotext, no system pypdf, and `uv` is NOT installed
    despite the environment note. `pip` is, so pypdf lives in a scratch venv — the same pattern the
    fleet used for Pillow. Verified on a real file: Jordan's resume → 3,356 chars.
    """
    import subprocess
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    if DOC_VENV_PY.exists():
        code = ("import sys;from pypdf import PdfReader;"
                "print('\\n'.join((p.extract_text() or '') for p in PdfReader(sys.argv[1]).pages))")
        r = subprocess.run([str(DOC_VENV_PY), "-c", code, str(path)], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    raise SystemExit(
        "🔴 CANNOT READ PDF — no extractor available.\n"
        f"   tried: pdftotext (absent), {DOC_VENV_PY} (absent or failed)\n"
        f"   fix:   python3 -m venv {DOC_VENV_PY.parents[1].parent} && "
        f"{DOC_VENV_PY} -m pip install pypdf\n"
        "   A PDF that cannot be read is UNMEASURED — never an empty pack.")


def _read_epub(path: pathlib.Path) -> str:
    """EPUB is a ZIP of XHTML. Stdlib only — no dependency, nothing to install, nothing to block."""
    import zipfile
    parts = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
        for n in sorted(names):
            try:
                parts.append(z.read(n).decode("utf-8", "replace"))
            except Exception:
                continue
    if not parts:
        raise SystemExit(f"🔴 EPUB has no readable XHTML members: {path}")
    return "\n".join(parts)


def _read_timed(text: str) -> list[tuple[int, str]]:
    """Parse .vtt / .srt into [(seconds, line)]. The DURABLE half of video learning.

    MEASURED 2026-10-26: this host cannot fetch YouTube transcripts — the API returns `RequestBlocked`
    (IP block) and the browser gets "Sign in to confirm you're not a bot". So the delivery is blocked,
    but the FORMAT is not: a transcript saved from the video's own "Show transcript" panel drops
    straight in here, timestamps and all. Own the part that cannot be taken away.
    """
    segs: list[tuple[int, str]] = []
    cur = None
    for line in text.splitlines():
        m = TS_RE.search(line)
        if m:
            h, mi, s = m.group(1), m.group(2), m.group(3)
            cur = (int(h) * 3600 + int(mi) * 60 + int(s)) if s else (int(h) * 60 + int(mi))
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if cur is not None and clean and not clean.isdigit() and "-->" not in clean:
            segs.append((cur, clean))
    # merge consecutive cues that share a timestamp
    merged: dict[int, list[str]] = {}
    for t, txt in segs:
        merged.setdefault(t, []).append(txt)
    return sorted(((t, " ".join(v)) for t, v in merged.items()), key=lambda x: x[0])


def _transcript_key() -> str:
    """The API key, from THIS seat's secrets first — never a hardcoded path to another seat."""
    import os
    if os.environ.get("TRANSCRIPT_API_KEY"):
        return os.environ["TRANSCRIPT_API_KEY"].strip()
    parts = pathlib.Path(__file__).resolve().parts
    seat = parts[parts.index("profiles") + 1] if "profiles" in parts else "gentech"
    for p in (pathlib.Path("/opt/data/profiles") / seat / "secrets" / "transcript_api_key",
              pathlib.Path("/opt/data/profiles") / seat / ".env"):
        if p.exists():
            t = p.read_text(errors="replace")
            if p.suffix == ".env":
                for line in t.splitlines():
                    if line.startswith("TRANSCRIPT_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            else:
                return t.strip()
    raise SystemExit("🔴 no TRANSCRIPT_API_KEY for this seat (secrets/transcript_api_key or .env)")


CUE_RE = re.compile(r"^\[([\d.]+)s\]\s*(.*)$")


def _read_video(url: str, max_chars: int) -> tuple[str, str, list[tuple[int, str]]]:
    """YouTube/Bilibili transcript via transcriptapi.com — VERIFIED WORKING 2026-10-26 (HTTP 200).

    Why this exists: youtube-transcript-api returns `RequestBlocked` from this host and the browser
    gets "Sign in to confirm you're not a bot" — both measured. transcriptapi.com is reachable and
    returns cues with timestamps, which is exactly what a lecture needs.
    """
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode({"video_url": url, "format": "text",
                                "include_timestamp": "true", "send_metadata": "true"})
    req = urllib.request.Request(f"https://transcriptapi.com/api/v2/youtube/transcript?{q}",
                                 headers={"Authorization": f"Bearer {_transcript_key()}",
                                          "User-Agent": "gentech-edu/1.0"})
    try:
        doc = json.loads(urllib.request.urlopen(req, timeout=120).read())
    except Exception as e:
        raise SystemExit(f"🔴 transcript fetch failed ({type(e).__name__}: {str(e)[:160]}). "
                         f"Nothing written; pass a .vtt/.srt file instead.")
    body = doc.get("transcript") or ""
    segs: list[tuple[int, str]] = []
    for line in body.splitlines():
        m = CUE_RE.match(line.strip())
        if m:
            segs.append((int(float(m.group(1))), m.group(2).strip()))
    if not segs:
        raise SystemExit("🔴 transcript came back empty or without cues — refusing to invent one. "
                         "The video may have captions disabled.")
    lang = doc.get("language", "?")
    text = "\n".join(f"[{t // 60}:{t % 60:02d}] {s}" for t, s in segs)
    return text[:max_chars], f"{url} (video, lang={lang}, {len(segs)} cues)", segs


def read_source(src: str, max_chars: int = 400_000) -> tuple[str, str, list[tuple[int, str]]]:
    """Return (text, provenance, timed_segments). Dispatch by what the source IS, not by hope."""
    low = src.lower().split("?")[0]
    is_video = any(h in low for h in ("youtube.com", "youtu.be", "bilibili.com"))

    if is_video:
        return _read_video(src, max_chars)

    if low.startswith(("http://", "https://")):
        import urllib.request
        req = urllib.request.Request(src, headers={"User-Agent": "gentech-edu/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                return raw.decode(enc)[:max_chars], src, []
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")[:max_chars], src, []

    p = pathlib.Path(src).expanduser()
    if not p.exists():
        raise SystemExit(f"🔴 no such file: {p}")

    if p.suffix.lower() == ".pdf":
        return _read_pdf(p)[:max_chars], f"{p} (PDF)", []
    if p.suffix.lower() == ".epub":
        return _read_epub(p)[:max_chars], f"{p} (EPUB)", []

    text = p.read_text(errors="replace")[:max_chars]
    if p.suffix.lower() in (".vtt", ".srt"):
        segs = _read_timed(text)
        return " ".join(s for _, s in segs)[:max_chars], f"{p} ({p.suffix[1:].upper()}, {len(segs)} cues)", segs
    return text, str(p), []


def load_corpus() -> dict:
    """What the brain says the learner actually does — used to RANK, never to invent."""
    corpus = {"places": [], "venues": [], "subjects": [], "words": set()}
    for f in CORPUS_SOURCES:
        if not f.exists():
            continue
        try:
            if f.suffix == ".json":
                d = json.loads(f.read_text())
            else:
                continue
        except Exception:
            continue
        if "travel-jordan" in f.name:
            t = d.get("trip") or {}
            corpus["places"] += [t.get("homeBase", ""), t.get("name", "")]
            for leg in t.get("legs", []):
                corpus["places"].append(leg.get("destination", ""))
        elif f.name == "travel-venues.json":
            corpus["venues"] += [v.get("name", "") for v in (d.get("venues") or [])][:40]
        elif f.name == "subjects.json":
            corpus["subjects"] += [s.get("name", "") for s in (d.get("subjects") or [])]
    for key in ("places", "venues", "subjects"):
        for item in corpus[key]:
            for w in re.findall(r"[a-zA-Z]{4,}", str(item).lower()):
                corpus["words"].add(w)
    return corpus


def clean_text(raw: str) -> str:
    """Strip markup BEFORE extraction.

    MEASURED 2026-10-18 against a real page: without this, the extractor read `<link rel="pingback"…>`
    as a target phrase and `</ul>` as its English gloss and reported **9 clean-looking units** —
    every one of them garbage. A pack built from that would have taught HTML tags as Nepali.
    A fenced code block (```…```) is treated as literal text and kept, so a real lesson can also be
    fed in markdown and parsed as its own content.
    """
    # keep fenced blocks as-is (they are the lesson); process everything else
    fences = re.findall(r"```(?:[a-zA-Z]*)\n(.*?)```", raw, flags=re.S)
    body = raw
    for f in fences:
        body = body.replace(f"```{f}```", "\n")
    body = re.sub(r"```.*?```", "\n", body, flags=re.S)
    if "<" in body and ">" in body:
        body = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", body)
        body = re.sub(r"(?s)<!--.*?-->", " ", body)
        body = re.sub(r"(?s)<[^>]+>", "\n", body)          # tags -> newlines, content survives
    # entities first (before the whitespace collapse), then the usual tidy
    body = (body.replace("&nbsp;", " ").replace("&#8211;", "–").replace("&#8212;", "—")
            .replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#038;", "&"))
    body = re.sub(r"[ \t]{2,}", "  ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body + "\n\n" + "\n".join(fences)


TOC_NOISE = re.compile(
    r"lesson|page|chapter|contents|table of|tense|grammatical|verb\b|exercise|vocabulary"
    r"|transliteration|introduction|appendi|index\b", re.I)


def _looks_like_phrase(target: str, eng: str) -> bool:
    """A gate against table-of-contents noise pretending to be vocabulary.

    MEASURED 2026-10-26 on the real Peace Corps course book (284 pages): without this gate the
    extractor reported **216 units**, led by `Lesson F ocus → Topical /G rammatical P age` and
    `4. \\ .. ne' → Present tense`. That is a TOC and a grammar table, not phrases — a pack built
    from it would teach layout artefacts as Nepali. Volume is not quality; a smaller honest list wins.
    """
    tl, el = target.strip(), eng.strip()
    if not (1 <= len(tl) <= 60) or not (2 <= len(el) <= 120):
        return False
    if TOC_NOISE.search(el) or TOC_NOISE.search(tl):
        return False
    if re.search(r"\.\.|\u2026|/|\\|\||_{2,}", tl):        # dotted leaders, slashes, backslashes
        return False
    if re.search(r"\b\d{2,}\b", el) and len(el.split()) <= 3:   # a bare page number
        return False
    # A numbered GRAMMAR-TABLE row ("17. 'ko laagi. → for ... (purpose)…") is not a phrase pair.
    if re.match(r"^\(?\d{1,2}[.)]\s", tl) or re.search(r"\.\.\.", el) or re.search(r"\.\.\.", tl):
        return False
    if len(tl.split()) > 6 or len(el.split()) > 14:            # a phrase, not a paragraph
        return False
    return True


def extract_units(text: str, dialect: str) -> list[dict]:
    """Candidate (target, english) pairs, in the shapes REAL material actually uses.

    A) TABULAR (how textbooks lay out vocabulary) — three consecutive non-empty lines:
           केही छैन            <- Nepali
           kehī chaina        <- transliteration
           No problem / It's okay   <- English
    B) INLINE — `नमस्ते — hello` / `नमस्ते (namaste) hello` on one line.

    Anything else is left alone. A phrase the extractor did not SEE is not emitted.
    """
    lines = [l.strip() for l in text.splitlines()]
    units: list[dict] = []
    used: set[int] = set()

    # ── A) the three-item table shape ────────────────────────────────────────────────────────────
    # MEASURED 2026-10-18: an HTML table cell becomes its OWN line, so a real vocabulary table reads
    #   'केही छैन' / '' / 'kehī chaina' / '' / 'No problem' — blank lines BETWEEN the cells.
    # Requiring consecutive lines found 2 units out of 16. The sequence must be over NON-EMPTY lines.
    nonempty = [l for l in lines if l]
    for i in range(len(nonempty) - 2):
        tgt, rom, eng = nonempty[i], nonempty[i + 1], nonempty[i + 2]
        if tgt in used:
            continue
        has_script = bool(DEVANAGARI.search(tgt))
        rom_ok = bool(re.fullmatch(r"[a-zA-Zāīūṭḍṇśṣḥṅñ\u0300-\u036f' .\-/]{2,60}", rom))
        eng_ok = bool(re.search(r"[A-Za-z]{2}", eng)) and not DEVANAGARI.search(eng)
        if has_script and rom_ok and eng_ok and 3 <= len(eng) <= 120:
            # A page title leaks through as target+rom+eng. The reliable signal is the middle line:
            # a real transliteration is LATIN-ONLY. A title's middle line is English words.
            rom_is_latin_only = not DEVANAGARI.search(rom) and not re.search(r"–|—|:", rom)
            titleish = re.search(r"–|—|Chapter \d|Unit \d|Introduction to", eng) or len(tgt) > 40
            if not rom_is_latin_only or titleish:
                continue
            if not _looks_like_phrase(tgt, eng):
                continue
            units.append({"target": tgt, "en": eng[:200], "rom": rom})
            used.update({tgt, rom, eng})

    # ── B) the inline shape ──────────────────────────────────────────────────────────────────────
    for raw in lines:
        if not raw or len(raw) < 4 or len(raw) > 400:
            continue
        parts = re.split(r"\s+[—–\-:|]\s+|\t+|\s{3,}", raw, maxsplit=1)
        if len(parts) != 2:
            continue
        left, right = parts[0].strip(), parts[1].strip()
        if not left or not right or not re.search(r"[A-Za-z]{2}", right):
            continue
        if DEVANAGARI.search(left) or (dialect.startswith("ne") and re.search(r"[A-Za-z]{2}", left)):
            # Same title filter as the table branch: a breadcrumb is not a phrase.
            if re.search(r"–|—|Chapter \d|Unit \d", right) or len(left) > 40:
                continue
            if not _looks_like_phrase(left, right):
                continue
            rom = None
            m = re.search(r"\(([^)]*)\)", left)
            if m:
                rom = m.group(1).strip()
                left = (left[: m.start()] + left[m.end():]).strip()
            units.append({"target": left, "en": right[:200], "rom": rom})

    # de-duplicate on the target string, keeping the first
    seen, out = set(), []
    for u in units:
        if u["target"] in seen or not u["target"].strip():
            continue
        seen.add(u["target"])
        out.append(u)
    return out


def situation_for(english: str) -> str:
    low = english.lower()
    best, best_hits = "greeting", 0
    for sit, words in SITUATION_HINTS.items():
        hits = sum(1 for w in words if w in low)
        if hits > best_hits:
            best, best_hits = sit, hits
    return best


def score(unit: dict, corpus: dict) -> tuple[int, list[str]]:
    """Relevance to THIS learner: does the English side touch something in his corpus?"""
    words = set(re.findall(r"[a-zA-Z]{4,}", unit["en"].lower()))
    overlap = words & corpus["words"]
    return len(overlap), sorted(overlap)[:5]


def build_pack(units: list[dict], dialect: str, args, provenance: str, corpus: dict) -> dict:
    grouped: dict[str, list[dict]] = {}
    scored = []
    for u in units:
        hits, why = score(u, corpus)
        scored.append((hits, u, why))
    scored.sort(key=lambda t: -t[0])
    for hits, u, why in scored:
        sit = situation_for(u["en"])
        entry = {("ne" if dialect.startswith("ne") else "text"): u["target"],
                 "en": u["en"], "register": "polite"}
        if u.get("rom"):
            entry["rom"] = u["rom"]
        if u.get("t"):
            entry["t"] = u["t"]        # where in the lecture it was said — never invented
        if why:
            entry["_corpus_hit"] = why
        grouped.setdefault(sit, []).append(entry)
    return {
        "_what": f"PACK INGESTED FROM MATERIAL — {args.title or pathlib.Path(provenance).name}",
        "_generated_by": "edu-ingest.py",
        "_source": provenance,
        "_license": args.license or "UNSTATED — do not redistribute until the terms are recorded",
        "_review_required": "This is a CANDIDATE list extracted by a machine from the source. It is not "
                            "a verified curriculum. A human (or the learner's colleague/teacher) must "
                            "accept each unit before it is taught.",
        "_ranking": "Units are ordered by overlap with the learner's OWN corpus (trip, venues, subjects). "
                    "Relevance ranks, it never invents: every unit below came from the source text.",
        "_count": sum(len(v) for v in grouped.values()),
        "dialect": dialect,
        "label": args.title or f"{dialect} — ingested",
        "phrases": grouped,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialect", required=True, help="e.g. ne-NP, th-TH")
    ap.add_argument("--source", required=True, help="file path or URL of the material")
    ap.add_argument("--title", default=None)
    ap.add_argument("--license", default=None, help="e.g. CC-BY-NC-SA — copied into the pack verbatim")
    ap.add_argument("--write", action="store_true", help="write the pack (default: report only)")
    ap.add_argument("--min-units", type=int, default=3)
    a = ap.parse_args()

    text, provenance, segments = read_source(a.source)
    raw_len = len(text)
    text = clean_text(text)
    corpus = load_corpus()
    units = extract_units(text, a.dialect)

    # ── TIMESTAMPS (video/lecture sources) ───────────────────────────────────────────────────────
    # A lecture's value is partly WHERE it was said. If the source carried cues, every unit that can
    # be located gets its timecode, so a lesson can point back to the moment. A unit that cannot be
    # located keeps no timestamp — an invented mm:ss is worse than none.
    if segments:
        for u in units:
            hit = next((t for t, s in segments if u["target"] and u["target"] in s), None)
            if hit is None:
                hit = next((t for t, s in segments if u["en"][:24].lower() in s.lower()), None)
            if hit is not None:
                u["t"] = f"{hit // 60}:{hit % 60:02d}"

    print(f"source      : {provenance}")
    print(f"text        : {raw_len:,} chars raw → {len(text):,} after stripping markup")
    if segments:
        print(f"cues        : {len(segments)} timestamped · {sum(1 for u in units if u.get('t'))} units located")
    print(f"corpus      : {len(corpus['words'])} distinct words from the brain (ranks, never invents)")
    print(f"units found : {len(units)}")

    if len(units) < a.min_units:
        print(f"\n🔴 REFUSING — found {len(units)} usable units, minimum is {a.min_units}.")
        print("   The material's shape is not one this extractor reads (it wants 'target — english'")
        print("   lines). That is a REFUSAL, not an empty result: nothing was written and no phrase")
        print("   was invented to fill the gap. Point it at the book's vocabulary/lesson pages.")
        return 3

    pack = build_pack(units, a.dialect, a, provenance, corpus)
    print(f"\nranked — top 8 by relevance to HIS corpus:")
    shown = 0
    for sit, entries in pack["phrases"].items():
        for e in entries:
            if shown >= 8:
                break
            print(f"  [{sit:9s}] {e.get('ne') or e.get('text')}  →  {e['en'][:60]}"
                  + (f"  @{e['t']}" if e.get("t") else "")
                  + (f"   ← {e['_corpus_hit']}" if e.get("_corpus_hit") else ""))
            shown += 1
    print(f"\ngroups: {', '.join(f'{k}={len(v)}' for k, v in pack['phrases'].items())}")
    print(f"license: {pack['_license'][:80]}")

    out = DATA / "phrases" / f"{a.dialect}.json"
    if not a.write:
        print(f"\n(dry run — would write {out}; re-run with --write)")
        return 0
    if out.exists():
        bak = out.with_suffix(".json.bak")
        bak.write_text(out.read_text())
        print(f"  existing pack backed up → {bak.name}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1))
    print(f"\n✅ wrote {out}  ({pack['_count']} units, {out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
