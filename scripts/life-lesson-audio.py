#!/usr/bin/env python3
"""
life-lesson-audio.py — turn today's life-lesson into listenable Spanish/Thai audio.

Part of GenTech EDU (life-based lessons). Reads the lesson the engine produced and renders it with
ElevenLabs so Jordan can drill it while walking, not just read it.

WHY A SEPARATE SCRIPT: generation and synthesis fail for different reasons. The engine can be perfectly
correct while the API key is dead or the account is out of characters — keeping them apart means a voice
outage never masquerades as a broken lesson, and the engine stays runnable with zero network access.

HONESTY: never writes a "success" audio file from an error body. A non-audio response is a loud failure.

USAGE
  python3 life-lesson-audio.py --learner <name>   # voices cache/life-lessons/<name>.json
  python3 life-lesson-audio.py --quiet    # cron mode: silent unless it breaks
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

def _seat() -> str:
    """The seat this copy is running on, derived from the script's OWN path.

    Cron has no script-args field, so path-derived identity is the only fleet-wide
    mechanism (same idiom as handoff-watcher.py). These three paths were hardcoded to
    /opt/data/profiles/gentech and carried byte-identical into all four seats, so
    a worker seat rendered from HQ's lesson file and could never produce its own audio.
    Running the SHARED CORE copy is not a seat; it falls back to HQ, which owns the core.
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
ENV = PROFILE / ".env"
LESSON_DIR = PROFILE / "cache" / "life-lessons"   # ONE FILE PER LEARNER (engine split, 2026-10-17)


def lesson_path(learner: str) -> pathlib.Path:
    return LESSON_DIR / f"{learner}.json"


def out_path(learner: str) -> pathlib.Path:
    return LESSON_DIR / f"{learner}.mp3"

# FALLBACK voice only. The real choice comes from the lesson's own `voice_id`, which the engine
# resolves per DIALECT. Hardcoding a single voice here is what produced the first wrong lesson:
# Roger (an ENGLISH voice, accent=american) read Dominican Spanish with an American accent.
#
# ⚠️ Shared-library voices are NOT synthesis-capable by id alone — the API returns
#    `404 voice_not_found` until the voice is ADDED to our account:
#      POST /v1/voices/add/{public_owner_id}/{voice_id}
#    Anderson (Dominican, es-DO) is already added. A new dialect needs the same step.
# NO FALLBACK VOICE. It used to be FALLBACK_VOICE = "CwhRBWXzGAHq8TQ4Fs17" — Roger, accent=american.
# A fallback voice is not a safety net for this job: the learner copies what they hear, so an English
# voice reading Thai teaches an accent they will pay to unlearn. No native voice -> refuse.
import os

KEY_SOURCES = [
    PROFILE / "secrets" / "elevenlabs_api_key",        # THIS seat's own — the correct place
    # ⚠️ FLEET-COMPAT: this entry is ANOTHER SEAT's filesystem, which the fleet-compat checklist forbids
    #    ("no absolute profile path hardcoded"). It is kept as a DECLARED last resort because the key
    #    currently lives only on the treasury seat, and it announces itself at runtime instead of
    #    resolving silently. Proper fix is distributing the key to each seat's own secrets/ — a
    #    credential-ownership decision, flagged to HQ rather than taken here.
    pathlib.Path("/opt/data/profiles/gentech-treasury/secrets/elevenlabs_api_key"),
]

INTRO = {
    "es": "Lección de español dominicano. Escucha y repite.",
    "th": "บทเรียนภาษาไทย ฟังแล้วพูดตาม",
}


def api_key() -> str:
    """Env first, then the fleet secrets files, then this seat's .env.

    The key on this host lives in a 600-mode secrets file, so a seat with no .env entry reported
    'ELEVENLABS_API_KEY not found' as if the fleet had no key at all — the gate was the LOOKUP, not
    the credential. Values are never printed.
    """
    k = os.environ.get("ELEVENLABS_API_KEY")
    if k and k.strip():
        return k.strip()
    for p in KEY_SOURCES:
        if p.exists():
            v = p.read_text().strip().strip('"').strip("'")
            if v:
                if p.parent != PROFILE / "secrets":
                    # Declare the degradation: reading another seat's credential, not ours.
                    print(f"  ⚠️  using the fleet key at {p.parent} (this seat has no secrets/ "
                          f"elevenlabs_api_key) — declared, not silent.", file=sys.stderr)
                return v
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("🔴 ELEVENLABS_API_KEY not found (env, secrets file, or profile .env)")


def model_for(voice_id: str) -> str:
    """The TTS model for this voice. PACK DATA (data/voices.json), default v2.

    MEASURED 2026-10-18: `eleven_multilingual_v2` lists neither `ne` nor `th` in its published language
    list, but it ACCEPTS that text and returns audio anyway — so "it produced a file" proves nothing.
    `eleven_v3` publishes support for ne/th/fil/es and is the only model that does for Nepali or Thai.
    v2 stays the default for the dialects it is actually trained on, because it is cheaper.
    """
    try:
        voices = json.loads((DATA / "voices.json").read_text())
    except Exception:
        return "eleven_multilingual_v2"          # no mapping -> the old behaviour, not a crash
    for _dialect, entry in (voices.get("dialects") or {}).items():
        ids = [v for k, v in (entry.get("by_form") or {}).items() if k != "note"]
        if voice_id in ids and entry.get("model_id"):
            return entry["model_id"]
    return "eleven_multilingual_v2"


def synth(voice_id: str, text: str) -> bytes | None:
    """One utterance. Returns None — never a fake file — if the API refuses or the body is not audio."""
    body = json.dumps({"text": text, "model_id": model_for(voice_id),
                       "voice_settings": {"stability": 0.45, "similarity_boost": 0.8}}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=body, headers={"xi-api-key": api_key(), "Content-Type": "application/json"})
    try:
        audio = urllib.request.urlopen(req, timeout=200).read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        print(f"🔴 life-lesson-audio: HTTP {e.code} — {detail}", file=sys.stderr)
        if e.code == 404:
            print("   hint: a shared-library voice must be ADDED to the account first —\n"
                  "   POST /v1/voices/add/{public_owner_id}/{voice_id}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"🔴 life-lesson-audio: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    # A JSON/HTML error body saved as .mp3 would look like success and play as noise. Verify audio.
    if not audio.startswith(b"ID3") and audio[:2] != b"\xff\xfb":
        print(f"🔴 life-lesson-audio: response is not MPEG audio (starts {audio[:12]!r}) — not writing it",
              file=sys.stderr)
        return None
    return audio


def join_mp3(parts: list, dest, gap: float = 0.45) -> bool:
    """Stitch clips into one track, with a short pause between them.

    Returns True only if ffmpeg actually produced the file. A silent "no join" would leave the learner
    holding pieces and no track, so the caller is told which happened rather than assuming.
    """
    import shutil
    import subprocess
    parts = [p for p in parts if p.exists() and p.stat().st_size > 0]
    if len(parts) < 2 or shutil.which("ffmpeg") is None:
        return False
    sil = dest.parent / "_silence.mp3"
    if not sil.exists():
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-t", str(gap), "-i", "anullsrc=r=44100:cl=mono", "-q:a", "9",
                        "-y", str(sil)], check=False)
    seq = []
    for i, p in enumerate(parts):
        if i and sil.exists():
            seq.append(sil)
        seq.append(p)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for p in seq:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex",
            "".join(f"[{i}:a]" for i in range(len(seq))) + f"concat=n={len(seq)}:v=0:a=1[out]",
            "-map", "[out]", "-y", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️  join failed for {dest.name}: {r.stderr.strip()[:180]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the character cost and write nothing — measure before spending")
    ap.add_argument("--learner", default="jordan",
                    help="whose lesson to voice (one file per learner, since 2026-10-17)")
    a = ap.parse_args()

    lesson_file, out_file = lesson_path(a.learner), out_path(a.learner)

    if not lesson_file.exists():
        print(f"🔴 life-lesson-audio: no lesson at {lesson_file} — run life-lesson-engine.py "
              f"--learner {a.learner} first", file=sys.stderr)
        return 1

    lesson = json.loads(lesson_file.read_text())
    dialect = lesson.get("dialect") or lesson.get("lang", "")
    if not lesson.get("items"):
        print("🔴 life-lesson-audio: lesson has no items — refusing to synthesise silence",
              file=sys.stderr)
        return 1

    voice_id = lesson.get("voice_id")
    if not voice_id:
        print(f"🔴 life-lesson-audio: the lesson for {a.learner} carries NO native voice for "
              f"{dialect} — refusing to synthesise. A borrowed English voice reading {dialect} is a "
              f"wrong answer, not a rough draft. Add one to edu/data/voices.json ",
              file=sys.stderr)
        return 1

    # ── THE TWO-VOICE BRIDGE (Jordan, 2026-10-17) ────────────────────────────────────────────────
    # Per phrase the learner hears three things, in order: the THAI in the native voice, then the
    # LATIN READING and the English meaning in the bridge voice. A reading on paper cannot carry Thai
    # tones (RTGS drops them), so the native audio beside it IS the teaching — and the DELTA between
    # the two voices is the point, not a nicety.
    #
    # The previous shape spoke `{thai} ... {english}` in ONE voice: the Thai voice reading English,
    # with the `rom` reading never spoken aloud at all. Both defects are fixed here.
    bridge_voice = lesson.get("bridge_voice_id")
    if not bridge_voice:
        print("  ⚠️  no bridge voice declared in data/voices.json — the Thai is voiced, but the learner "
              "will not HEAR the English approximation. Declared, not silent.", file=sys.stderr)

    items = lesson["items"]

    if a.dry_run:
        # MEASURE BEFORE SPENDING. The lane is metered per character, and a render that runs out
        # halfway leaves a half-lesson. So the cost is stated first and NOTHING is written — and the
        # caller can compare it with what the account actually has, instead of discovering it by
        # failing. (A "lane open" probe on 1 character does NOT prove a ~1,000-character render fits.)
        need = 0
        for it in items:
            need += len(it["es"])
            if bridge_voice:
                if it.get("rom"):
                    need += len(it["rom"])
                need += len(it["en"])
        per = 3 if bridge_voice else 1
        print(f"DRY RUN — {len(items)} phrases · native={voice_id} · bridge={bridge_voice or 'NONE'}")
        print(f"  characters required : {need}")
        print(f"  clips that would be made : {len(items) * per}")
        print("  nothing written")
        return 0
    outdir = out_file.parent / a.learner
    outdir.mkdir(parents=True, exist_ok=True)
    thai_tracks: list = []
    clips = 0

    for n, it in enumerate(items, 1):
        p_thai = outdir / f"{n:02d}-thai.mp3"
        blob = synth(voice_id, it["es"])
        if blob is None:
            print(f"🔴 life-lesson-audio: refusing — item {n} Thai did not synthesise. No partial "
                  f"track is written; a half-lesson is a wrong lesson.", file=sys.stderr)
            return 1
        p_thai.write_bytes(blob)
        thai_tracks.append(p_thai)
        clips += 1

        segs = [p_thai]
        if bridge_voice:
            if it.get("rom"):
                blob = synth(bridge_voice, it["rom"])
                if blob:
                    p = outdir / f"{n:02d}-reading.mp3"
                    p.write_bytes(blob)
                    segs.append(p)
                    clips += 1
            blob = synth(bridge_voice, it["en"])
            if blob:
                p = outdir / f"{n:02d}-meaning.mp3"
                p.write_bytes(blob)
                segs.append(p)
                clips += 1
        if len(segs) > 1:
            join_mp3(segs, outdir / f"{n:02d}-full.mp3")

    full = out_file.parent / f"{a.learner}-lesson.mp3"
    joined = join_mp3(thai_tracks, full)

    if not a.quiet:
        print(f"✅ {outdir}/ — {clips} clips across {len(items)} phrases · learner={a.learner} · "
              f"dialect={dialect} · native={voice_id} · bridge={bridge_voice or 'NONE'}")
        print(f"   Thai-only track: {full} "
              f"({'joined' if joined else 'NOT joined — ffmpeg absent or a single clip'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
