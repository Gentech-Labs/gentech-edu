#!/usr/bin/env python3
"""edu-serve.py — the missing endpoint. Closes the loop: a click in the hub becomes a recorded attempt.

MEASURED 2026-10-26: the hub page had a Complete button wired to `POST /record`, and nothing served
that path — so the button told the truth ("offline — not recorded") and nothing was ever written. EDU
could read mastery and sort weak-first, but no click anywhere produced a row. Half a loop.

This serves:
    GET  /            → the generated lesson page
    GET  /edu-data.json, /edu-template.json
    POST /record      → {"key": "...", "correct": true}  → writes through edu-record.py
    GET  /progress    → the learner's record as JSON (what the UI can re-read)

RULES (same as the rest of EDU)
  - The key must belong to this learner's dialect; edu-record.py enforces it and this passes the error
    back as-is rather than swallowing it into a green tick.
  - Bind to LOOPBACK by default. This is a personal learning page, not a public API; --host 0.0.0.0 is
    opt-in and says so out loud.
  - No authentication = not on the internet. Stated at startup.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class Handler(BaseHTTPRequestHandler):
    learner = "jordan"
    dialect = None
    root: pathlib.Path | None = None

    def log_message(self, fmt, *a):          # quiet: one line per request is noise in a chat log
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                         # noqa: N802
        path = self.path.split("?")[0]
        if path == "/progress":
            rec = pathlib.Path(f"/opt/data/profiles/{self._seat()}/state/learners/{self.learner}.json")
            if not rec.exists():
                # UNMEASURED, not 0%
                return self._send(200, json.dumps({"observed": 0, "note": "no attempts recorded yet"}).encode(),
                                  "application/json")
            return self._send(200, rec.read_bytes(), "application/json")
        fname = {"": "index.html", "/": "index.html"}.get(path, path.lstrip("/"))
        f = (self.root or pathlib.Path(".")) / fname
        if not f.exists() or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = ("text/html" if f.suffix == ".html" else
                 "application/json" if f.suffix == ".json" else "text/plain")
        return self._send(200, f.read_bytes(), ctype)

    def _seat(self) -> str:
        """This script's own seat, derived from its path — the fleet idiom (never a hardcoded name)."""
        parts = pathlib.Path(__file__).resolve().parts
        return parts[parts.index("profiles") + 1] if "profiles" in parts else "arthur"

    def do_POST(self):                        # noqa: N802
        if self.path.split("?")[0] != "/record":
            return self._send(404, b"not found", "text/plain")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._send(400, json.dumps({"ok": False, "error": f"bad body: {e}"}).encode(),
                              "application/json")
        key = (payload.get("key") or "").strip()
        flag = "--correct" if payload.get("correct") else "--miss"
        if not key:
            return self._send(400, json.dumps({"ok": False, "error": "no key"}).encode(), "application/json")

        cmd = [sys.executable, str(SCRIPTS / "edu-record.py"),
               "--learner", self.learner, "--dialect", self.dialect or key.split(":")[0],
               "--key", key, flag]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            # The refusal is the feature — pass it through instead of pretending success.
            return self._send(400, json.dumps({"ok": False, "error": (r.stderr or r.stdout).strip()[:300]}).encode(),
                              "application/json")
        return self._send(200, json.dumps({"ok": True, "key": key,
                                           "result": r.stdout.strip().splitlines()[0] if r.stdout else ""}).encode(),
                          "application/json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="dir holding index.html + edu-data.json")
    ap.add_argument("--learner", default="jordan")
    ap.add_argument("--dialect", default=None)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()

    root = pathlib.Path(a.root).expanduser().resolve()
    if not (root / "index.html").exists():
        raise SystemExit(f"🔴 no index.html in {root} — generate one with edu-hub.py first")

    Handler.learner, Handler.dialect, Handler.root = a.learner, a.dialect, root
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"EDU learn-server → http://{a.host}:{a.port}/")
    print(f"  root    : {root}")
    print(f"  learner : {a.learner}  dialect: {a.dialect or '(from key)'}")
    print(f"  POST /record writes through edu-record.py — a refusal comes back as an error, never a tick")
    if a.host not in ("127.0.0.1", "localhost"):
        print(f"  ⚠️  BOUND TO {a.host} — no authentication. Anyone who can reach this port can record")
        print(f"      attempts for this learner. Put it behind a proxy before it leaves the box.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
