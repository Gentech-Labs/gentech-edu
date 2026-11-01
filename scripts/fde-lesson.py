#!/usr/bin/env python3
"""fde-lesson.py — a track renderer on the EDU engine.

Engine/pack boundary (EDU's rule): this script is deliberately subject-BLIND — it reads a pack file and knows
nothing about Go, clouds, credentials or job postings. `data/<track>-track.json` is the pack. A different
subject means a different JSON, not an edit here.

Because that rule has to be *true*, the pack is addressed by NAME, never hardcoded:
    --track fde        -> data/fde-track.json      + state/fde-progress.json      (default)
    --track career     -> data/career-track.json   + state/career-progress.json
Adding a track is adding a file. `--tracks` lists what is installed. The default track and its state path are
unchanged from the pre-selector version on purpose: renaming stored state orphans a learner silently.

Four honesty rules are load-bearing, and the selftest plants a failure for each:
  1. No observed work  ->  UNMEASURED, never a fabricated 0%.
  2. Reading the steps is NOT doing the milestone — coverage is not proficiency.
  3. An unattempted milestone is not a miss; it is excluded, not counted against the learner.
  4. A gate that cannot refuse is decoration — a blocked milestone refuses to close.

Usage:
  fde-lesson.py                       serve the next unmet milestone of the default track
  fde-lesson.py --track career        ... of a named track
  fde-lesson.py --tracks              list installed tracks
  fde-lesson.py --status              progress, labelled honestly
  fde-lesson.py --done C1 --evidence "Pearson VUE pass" \
                --proof-kind exam --proof-id CLF-123456 --proof-date 2027-01-14
  fde-lesson.py --selftest            plant failures and prove each goes RED
"""
import argparse, datetime, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
STATE_DIR = os.path.join(HERE, "..", "state")
DEFAULT_TRACK = "fde"
TODAY = datetime.date.today().isoformat()


def pack_path(track):
    return os.path.join(DATA, f"{track}-track.json")


def state_path(track):
    return os.path.join(STATE_DIR, f"{track}-progress.json")


def available_tracks():
    out = []
    for p in sorted(glob.glob(os.path.join(DATA, "*-track.json"))):
        out.append(os.path.basename(p)[: -len("-track.json")])
    return out


def load_pack(path=None, track=DEFAULT_TRACK):
    path = path or pack_path(track)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"no pack for track {track!r} at {path} — installed: {', '.join(available_tracks()) or 'none'}"
        )
    d = json.load(open(path, encoding="utf-8"))
    ids = [m["id"] for m in d["milestones"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate milestone ids in the pack")
    # A dangling blocked_by would block a milestone forever with no error — same class as a dangling
    # reference path. Catch it at load, not at close.
    unknown = {b for m in d["milestones"] for b in _blockers(m) if b not in set(ids)}
    if unknown:
        raise ValueError(f"pack {track!r} declares blocked_by on unknown milestones: {sorted(unknown)}")
    return d


def _blockers(m):
    b = m.get("blocked_by")
    if not b:
        return []
    return [b] if isinstance(b, str) else list(b)


def load_state(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def save_state(s, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(s, open(path, "w", encoding="utf-8"), indent=1)


def unmet_blockers(pack, state, m):
    done = state.get("done", {})
    return [b for b in _blockers(m) if b not in done]


def next_milestone(pack, state):
    """The engine owns the sequence. Closed milestones are skipped; order is the pack's order.

    Returns (milestone, blockers). A milestone whose blockers are unmet is returned WITH its blockers so the
    caller can say why it is not being served, instead of silently serving something later in the list.
    """
    done = state.get("done", {})
    for m in pack["milestones"]:
        if m["id"] in done:
            continue
        return m, unmet_blockers(pack, state, m)
    return None, []


def progress_line(pack, state):
    total = len(pack["milestones"])
    done = state.get("done", {})
    closed = [m for m in pack["milestones"] if m["id"] in done]
    if not done:
        # RULE 1: no observation is not zero progress.
        return (f"UNMEASURED — 0 of {total} milestones closed, and no work recorded yet. "
                f"Practice is not certification.")
    n = len(closed)
    hours = sum(m.get("hours", 0) for m in closed)
    return (f"{n} of {total} milestones closed with evidence ({hours:g}h). "
            f"RULE 2: this counts closed milestones, NOT ability — reading a milestone is not doing it.")


def mask(proof_id):
    s = str(proof_id)
    return f"…{s[-4:]}" if len(s) > 4 else "…"


def cmd_tracks():
    tracks = available_tracks()
    print(f"installed tracks ({len(tracks)}): {', '.join(tracks) or 'none'}")
    for t in tracks:
        try:
            pack = load_pack(track=t)
            load_state(state_path(t))
            print(f"  {t:<10} {len(pack['milestones'])} milestones · {pack.get('_pack','')[:60]}")
        except Exception as e:  # a broken pack must be visible, not skipped
            print(f"  {t:<10} INVALID PACK: {e}")
    return 0


def cmd_serve(pack, state, track):
    m, blockers = next_milestone(pack, state)
    print(progress_line(pack, state))
    if not m:
        print("\nEvery milestone in the pack is closed. The next move is the pack's, not this script's.")
        return 0
    if blockers:
        # A refusal, not a nudge: the milestone is named, the blocker is named, nothing is served past it.
        print(f"\nBLOCKED — {m['id']}: {blockers[0]} must close first ({', '.join(blockers)}).")
        if m.get("gate"):
            print(f"  the pack's own note: {m['gate']}")
        print(f"  nothing after {m['id']} is served until its blocker closes.")
        return 0
    print(f"\nNEXT — {m['id']}: {m['skill']}  ({m.get('kind','')}, ~{m.get('hours','?')}h)")
    print(f"  why: {m['why']}")
    print(f"  artifact it produces: {m['artifact']}")
    print("  steps:")
    for i, s in enumerate(m["steps"], 1):
        print(f"    {i}. {s}")
    print(f"  done when: {m['done_when']}")
    print(f"\n  close it with:  fde-lesson.py --track {track} --done {m['id']} --evidence \"<what proves it>\"")
    return 0


def cmd_status(pack, state, track):
    print(f"track: {track}")
    print(progress_line(pack, state))
    done = state.get("done", {})
    for m in pack["milestones"]:
        d = done.get(m["id"])
        if d:
            proof = d.get("proof") or {}
            tail = ""
            if proof:
                bits = [proof.get("kind", "proof")]
                if proof.get("id"):
                    bits.append(mask(proof["id"]))
                if proof.get("date"):
                    bits.append(proof["date"])
                tail = f" [{', '.join(bits)}]"
            mark = f"✅ closed {d['date']} — {d['evidence']}{tail}"
        else:
            bl = unmet_blockers(pack, state, m)
            mark = f"·  open (blocked by {', '.join(bl)})" if bl else "·  open"
        print(f"  {m['id']:<4} {m['skill'][:38]:<40} {mark}")
    hd = pack.get("hard_dates") or []
    if hd:
        print("\nhard dates:")
        today = datetime.date.today()
        for x in sorted(hd, key=lambda y: y.get("date", "")):
            try:
                d = datetime.date.fromisoformat(x["date"])
                days = (d - today).days
                when = f"in {days}d" if days >= 0 else f"{-days}d ago"
            except Exception:
                when = "unparseable"
            print(f"  {x.get('date','?'):<12} {when:<10} {x.get('what','')}")
    return 0


def cmd_done(pack, state, mid, evidence, proof, track, spath=None):
    by_id = {m["id"]: m for m in pack["milestones"]}
    if mid not in by_id:
        print(f"REFUSED: {mid} is not a milestone in this pack.")
        return 2
    if not evidence or len(evidence.strip()) < 4:
        # RULE 4-adjacent: a milestone closed with nothing behind it is a claim, not a completion.
        print("REFUSED: a milestone needs evidence (commit, url, path, or an exam result). "
              "A closed milestone with nothing behind it is a claim, not a completion.")
        return 2
    bl = unmet_blockers(pack, state, by_id[mid])
    if bl:
        print(f"REFUSED: {mid} is blocked by {', '.join(bl)} — close that first. "
              "A gate that cannot refuse is decoration.")
        return 3
    rec = {"date": TODAY, "evidence": evidence.strip()}
    if proof:
        rec["proof"] = proof
    state.setdefault("done", {})[mid] = rec
    save_state(state, spath or state_path(track))
    print(f"closed {mid} — {evidence.strip()}" + (f"  proof: {json.dumps(proof)}" if proof else ""))
    print(progress_line(pack, state))
    return 0


def cmd_selftest():
    """Plant failures; prove each check goes RED. A check that cannot fail proves nothing."""
    import tempfile, copy

    results = []
    pack = load_pack(track=DEFAULT_TRACK)

    # 0 — the selftest must not write to REAL state (it once did: a synthetic milestone landed in the live
    #     fde-progress.json, which is exactly the "test writes to production" class). Snapshot and compare.
    real_state = state_path(DEFAULT_TRACK)
    before = os.stat(real_state).st_mtime_ns if os.path.exists(real_state) else None

    # 1 — the sequence skips what is closed
    s = {"done": {"M0": {"date": TODAY, "evidence": "x"}}}
    m, _ = next_milestone(pack, s)
    results.append(("sequence skips closed milestones", m["id"] != "M0"))

    # 2 — no state means UNMEASURED, not 0%
    line = progress_line(pack, {})
    results.append(("empty state reads UNMEASURED, never 0%", "UNMEASURED" in line and "0%" not in line))

    # 3 — an unattempted milestone is not a miss (ratio excludes it)
    line = progress_line(pack, {"done": {"M1": {"date": TODAY, "evidence": "x"}}})
    results.append(("unattempted milestones are excluded, not misses", "1 of" in line and "not" in line.lower()))

    # 4 — a done without evidence is refused
    rc = cmd_done(pack, {}, "M1", "", None, DEFAULT_TRACK, tempfile.mktemp(suffix=".json"))
    results.append(("closing with no evidence is refused", rc == 2))

    # 5 — the pack has unique ids (a duplicate would silently drop a milestone)
    try:
        bad = copy.deepcopy(pack)
        bad["milestones"].append(bad["milestones"][0])
        p2 = tempfile.mktemp(suffix=".json")
        json.dump(bad, open(p2, "w"))
        try:
            load_pack(p2, DEFAULT_TRACK)
            ok = False
        except ValueError:
            ok = True
    except Exception:
        ok = False
    results.append(("duplicate milestone ids are rejected", ok))

    # 6 — a GATE refuses to close (proved with a synthetic pack, so the test never depends on live pack data)
    gpack = {
        "milestones": [
            {"id": "G0", "skill": "gate", "kind": "admin", "why": "w", "artifact": "a",
             "steps": ["s"], "done_when": "d", "hours": 0},
            {"id": "G1", "skill": "gated", "kind": "cert", "why": "w", "artifact": "a",
             "steps": ["s"], "done_when": "d", "hours": 1, "blocked_by": "G0"},
        ]
    }
    m2, bl = next_milestone(gpack, {"done": {"G0": {"date": TODAY, "evidence": "x"}}})
    open_blocked = (m2["id"] == "G1" and bl == [])
    rc_blocked = cmd_done(gpack, {}, "G1", "something", None, DEFAULT_TRACK, tempfile.mktemp(suffix=".json"))
    results.append(("a blocked milestone refuses to close", open_blocked and rc_blocked == 3))

    # 7 — unknown pack keys are IGNORED, not an error (a new pack must not need an engine edit to load)
    upack = copy.deepcopy(gpack)
    upack["hard_dates"] = [{"date": "2099-01-01", "what": "future"}]
    upack["milestones"][0]["mystery_key"] = {"nested": True}
    upack["milestones"][1]["gate"] = "prose that blocks nothing"
    try:
        p3 = tempfile.mktemp(suffix=".json")
        json.dump(upack, open(p3, "w"))
        load_pack(p3, "synthetic")
        ok = True
    except Exception:
        ok = False
    results.append(("unknown pack keys are ignored, not fatal", ok))

    # 8 — a DANGLING blocked_by is rejected at load (else a milestone blocks forever, silently)
    dpack = copy.deepcopy(gpack)
    dpack["milestones"][1]["blocked_by"] = "NOPE"
    try:
        p4 = tempfile.mktemp(suffix=".json")
        json.dump(dpack, open(p4, "w"))
        try:
            load_pack(p4, "synthetic")
            ok = False
        except ValueError:
            ok = True
    except Exception:
        ok = False
    results.append(("a blocked_by naming an unknown milestone is rejected", ok))

    # 9 — a track's state cannot leak into another track's state path
    results.append(("per-track state paths are distinct",
                    state_path("fde") != state_path("career")
                    and state_path("career").endswith("career-progress.json")))

    # 10 — structured proof is stored and its id is masked in status output
    spack = copy.deepcopy(gpack)
    spack["milestones"][1]["blocked_by"] = []
    st = {}
    tmp_state = tempfile.mktemp(suffix=".json")
    cmd_done(spack, st, "G1", "Pearson VUE pass", {"kind": "exam", "id": "CLF-123456", "date": "2099-01-01"},
             DEFAULT_TRACK, tmp_state)
    rec = st.get("done", {}).get("G1", {})
    ok = rec.get("proof", {}).get("id") == "CLF-123456" and mask("CLF-123456") == "…3456"
    results.append(("an exam proof is stored and its id masked in output", ok))

    # 11 — the suite left the real state file byte-untouched
    after = os.stat(real_state).st_mtime_ns if os.path.exists(real_state) else None
    results.append(("the selftest does not write to live state", before == after))

    for name, ok in results:
        print(f"  {'GREEN' if ok else 'RED  '}  {name}")
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} pass" + (f" — FAILING: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default=DEFAULT_TRACK)
    ap.add_argument("--tracks", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--done", metavar="ID")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--proof-kind", default="")
    ap.add_argument("--proof-id", default="")
    ap.add_argument("--proof-date", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try:
        if a.selftest:
            sys.exit(cmd_selftest())
        if a.tracks:
            sys.exit(cmd_tracks())
        try:
            pk = load_pack(track=a.track)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERROR: {e}")
            sys.exit(2)
        sp = state_path(a.track)
        if a.done:
            proof = {}
            if a.proof_kind or a.proof_id or a.proof_date:
                proof = {"kind": a.proof_kind or "other", "id": a.proof_id, "date": a.proof_date}
            sys.exit(cmd_done(pk, load_state(sp), a.done, a.evidence, proof or None, a.track))
        sys.exit(cmd_status(pk, load_state(sp), a.track) if a.status else cmd_serve(pk, load_state(sp), a.track))
    except BrokenPipeError:
        # `fde-lesson.py --status | head` is a normal thing to type. A traceback there reads as a crash and is
        # a false alarm — silence it and exit on the consumer's terms.
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
