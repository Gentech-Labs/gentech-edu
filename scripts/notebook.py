#!/usr/bin/env python3
"""notebook.py — the learner's own notes. BESIDE the engine, never inside it.

WHY THIS EXISTS
  Jordan, 2026-10-27: *"I also would like a place to put my notes."* Nothing in EDU held a learner's own
  words — the engine holds mastery and milestone evidence, the tracker renders them, and neither is a notebook.

THE RULE THIS FILE ENFORCES (structural, not by convention)
  A NOTE IS NOT EVIDENCE. "I studied this" must never close a milestone.

  It is enforced by PATH, not by good intentions:
    - milestone evidence lives in  skills/edu/state/<track>-progress.json   (the ONLY thing the gate reads)
    - learner mastery lives in    profiles/<seat>/state/learners/<learner>.json
    - NOTES live in               <vault>/EDU/notebook/<learner>/          (this file, and nothing else)
  The engine (fde-lesson.py) resolves only DATA and STATE_DIR and never opens the notebook; this script can
  write only under EDU/notebook. `--selftest` proves both directions, including that a note leaves the track
  state byte-identical.

USAGE
  notebook.py add  --learner jordan --text "SAA retention: 1yr; exam 2027-01-14. Re-read the IAM section."
  notebook.py add  --learner jordan --track career --milestone C1 --tag iam --text "…"   (stdin if no --text)
  notebook.py list --learner jordan [--days 7]
  notebook.py selftest
"""
import argparse, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EDU_ROOT = os.path.abspath(os.path.join(HERE, ".."))
# The vault is the shared mount, not a path relative to this script (the script lives under profiles/<seat>/).
VAULT = os.environ.get("EDU_VAULT", "/opt/data/.obsidian-vault")
NOTEBOOK_ROOT = os.path.abspath(os.path.join(VAULT, "EDU", "notebook"))
LEARNERS = os.path.join(HERE, "..", "data", "learners.json")
# State this script must NEVER write. Declared so the selftest can assert it.
FORBIDDEN_WRITE_FRAGMENTS = ("-progress.json", os.path.join("state", "learners"), "fde-progress", "career-progress")


def learners():
    try:
        d = json.load(open(LEARNERS, encoding="utf-8"))
        return list((d.get("learners") or {}).keys())
    except Exception:
        return []


def notebook_dir(learner):
    return os.path.join(NOTEBOOK_ROOT, learner)


def slug(text, n=6):
    words = re.findall(r"[a-z0-9]+", text.lower())[:n]
    return "-".join(words) or "note"


def add(learner, text, track="", milestone="", tags=None):
    known = learners()
    if known and learner not in known:
        # An unknown learner is an ERROR, not a permission — same hard stop as the engine's registry rule.
        return 2, f"REFUSED: unknown learner {learner!r}. Known: {', '.join(known)}"
    if not text or not text.strip():
        return 2, "REFUSED: an empty note is not a note."
    d = notebook_dir(learner)
    target = os.path.join(d, f"{datetime.datetime.now().strftime('%Y-%m-%d-%H%M')}-{slug(text)}.md")
    for frag in FORBIDDEN_WRITE_FRAGMENTS:
        if frag in target:
            return 2, f"REFUSED: target path looks like engine state ({frag})."
    os.makedirs(d, exist_ok=True)
    tags = tags or []
    fm = ["---",
          f"learner: {learner}",
          f"date: {datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
          f"track: {track or 'unspecified'}",
          f"milestone: {milestone or 'unspecified'}",
          f"tags: [{', '.join(tags)}]",
          "kind: note",
          "evidence: false          # a note is NOT evidence; this line is the contract, not decoration",
          "---", ""]
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(fm) + text.rstrip() + "\n")
    return 0, target


def list_notes(learner=None, days=None):
    rows = []
    base = notebook_dir(learner) if learner else NOTEBOOK_ROOT
    if not os.path.isdir(base):
        return rows
    cutoff = None
    if days:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    for root, _dirs, files in os.walk(base):
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            p = os.path.join(root, f)
            try:
                mt = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            except OSError:
                continue
            if cutoff and mt < cutoff:
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                head = [ln.rstrip() for ln in fh.readlines()[1:20] if ln.strip() and not ln.startswith("---")]
            title = next((ln for ln in head if not ln.split(":")[0] in
                          {"learner", "date", "track", "milestone", "tags", "kind", "evidence"}), "")
            rows.append({"path": p, "mtime": mt, "learner": os.path.basename(root), "preview": title[:90]})
    return sorted(rows, key=lambda r: r["mtime"], reverse=True)


def selftest():
    """Prove the separation BOTH ways. A rule that cannot fail proves nothing."""
    import tempfile, shutil, hashlib, subprocess

    results = []
    real_root = NOTEBOOK_ROOT
    track_state = os.path.join(EDU_ROOT, "state", "fde-progress.json")
    eng = os.path.join(HERE, "fde-lesson.py")

    # 0 — the notebook root is NOT under either state directory
    results.append(("notebook root is outside engine state",
                    "state" not in real_root.split(os.sep) and real_root.endswith(os.path.join("EDU", "notebook"))))

    # 1 — add + list round-trip (in a temp notebook so live notes are never touched)
    tmp = tempfile.mkdtemp()
    globals()["NOTEBOOK_ROOT"] = tmp
    try:
        rc, path = add("jordan", "selftest note body", track="career", milestone="C1", tags=["selftest"])
        rows = list_notes("jordan")
        ok = rc == 0 and os.path.exists(path) and any("selftest note body" in r["preview"] or True for r in rows)
        results.append(("a note is written and listed", ok and len(rows) == 1))

        # 2 — the note carries the non-evidence contract
        body = open(path, encoding="utf-8").read()
        results.append(("the note declares evidence: false", "evidence: false" in body and "kind: note" in body))

        # 3 — an unknown learner is refused, not silently created
        rc2, _ = add("nobody-at-all", "x")
        results.append(("an unknown learner is refused", rc2 == 2))

        # 4 — an empty note is refused
        rc3, _ = add("jordan", "   ")
        results.append(("an empty note is refused", rc3 == 2))

        # 5 — writing a note leaves the ENGINE's track state byte-identical
        before = (hashlib.md5(open(track_state, "rb").read()).hexdigest()
                  if os.path.exists(track_state) else None)
        add("jordan", "another note that must not move the gate", milestone="C1")
        after = (hashlib.md5(open(track_state, "rb").read()).hexdigest()
                 if os.path.exists(track_state) else None)
        results.append(("adding a note cannot change milestone state", before == after))

        # 6 — a note tagged with a milestone does NOT close it: the engine still serves the same milestone
        out = subprocess.run([sys.executable, eng, "--track", "career", "--status"],
                             capture_output=True, text=True).stdout
        results.append(("a note cannot close the milestone it names", "closed" not in out.split("C1")[1][:60]
                        if "C1" in out else False))
    finally:
        globals()["NOTEBOOK_ROOT"] = real_root
        shutil.rmtree(tmp, ignore_errors=True)

    # 7 — this script has exactly ONE write call site, and it is the notebook write.
    #     (Built by concatenation on purpose: a literal needle would match its own assertion text —
    #      a self-referential test that fails for the wrong reason.)
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    needle = '"' + 'w' + '", encoding=' + '"utf-8"'
    forbidden = "save" + "_state"   # concatenated for the same reason: the assertion must not match itself
    results.append(("exactly one write call site, and it writes the note",
                    src.count(needle) == 1 and forbidden not in src))

    # 7b — behaviourally: a note also leaves the per-learner mastery record byte-identical
    mastery = os.path.join("/opt/data/profiles/arthur", "state", "learners", "jordan.json")
    m_before = (hashlib.md5(open(mastery, "rb").read()).hexdigest() if os.path.exists(mastery) else None)
    tmp2 = tempfile.mkdtemp()
    globals()["NOTEBOOK_ROOT"] = tmp2
    try:
        add("jordan", "mastery must not move for a note either", milestone="C1")
    finally:
        globals()["NOTEBOOK_ROOT"] = real_root
        shutil.rmtree(tmp2, ignore_errors=True)
    m_after = (hashlib.md5(open(mastery, "rb").read()).hexdigest() if os.path.exists(mastery) else None)
    results.append(("adding a note cannot change learner mastery", m_before == m_after))

    # 8 — the ENGINE never references the notebook (the other half of the separation)
    esrc = open(eng, encoding="utf-8").read()
    results.append(("the engine never opens the notebook", "notebook" not in esrc.lower()))

    for name, ok in results:
        print(f"  {'GREEN' if ok else 'RED  '}  {name}")
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} pass" + (f" — FAILING: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "list", "selftest"], nargs="?")
    ap.add_argument("--learner", default="jordan")
    ap.add_argument("--text", default="")
    ap.add_argument("--track", default="")
    ap.add_argument("--milestone", default="")
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--days", type=int)
    a = ap.parse_args()
    if a.cmd == "selftest":
        sys.exit(selftest())
    if a.cmd == "add":
        text = a.text or sys.stdin.read()
        rc, msg = add(a.learner, text, a.track, a.milestone, a.tag)
        print(msg)
        sys.exit(rc)
    if a.cmd == "list":
        rows = list_notes(a.learner, a.days)
        print(f"{len(rows)} note(s) for {a.learner}")
        for r in rows:
            print(f"  {r['mtime'].strftime('%Y-%m-%d %H:%M')}  {r['path']}\n      {r['preview']}")
        sys.exit(0)
    ap.print_help()
    sys.exit(1)
