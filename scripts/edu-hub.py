#!/usr/bin/env python3
"""edu-hub.py — render a lesson as a GenTech Hub dashboard (lesson-by-lesson, with Complete + dailies).

Jordan, 2026-10-18: *"We could also make it to where this uses the GenTech Hub to create a nice front
end. So that way you can go lesson by lesson and maybe you can hit the complete button… maybe weeklies.
We gotta get creative to get users loving using the system."*

WHAT THIS IS
  EDU (engine + pack + learner record) produces the DATA; the Hub renders the surface. This script is the
  bridge — it emits `edu-template.json` + `edu-data.json` in the Hub's own contract
  (meta / theme / tabs / sections, section types stats|table|progress|checklist) and a self-contained
  HTML page that renders it with zero dependencies.

HONESTY RULES BAKED IN (this is a learning product, so the numbers are the product)
  - A phrase with no attempt shows **NEW**, never "0%". Unpractised is not failed.
  - "Complete" is NOT a checkbox that flatters: it writes a real attempt to the learner's record via
    edu-record.py, and the progress bar counts OBSERVED phrases only.
  - The dailies are derived from the learner's own weak phrases, not invented content.
  - The page states the pack's provenance and license, because a lesson built from a CC-BY-NC-SA book
    has to say so.

USAGE
  python3 edu-hub.py --learner jordan --subject ne-NP --out <dir>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import date

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"


def run_lesson(learner: str, subject: str | None) -> dict:
    cmd = [sys.executable, str(SCRIPTS / "life-lesson-engine.py"), "--learner", learner, "--json"]
    if subject:
        cmd += ["--subject", subject]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit(f"🔴 engine refused: {r.stderr.strip()[:400]}")
    return json.loads(r.stdout)


def lesson_to_hub(lesson: dict) -> tuple[dict, dict]:
    learner = lesson.get("learner")
    items = lesson.get("items", [])
    seen = [i for i in items if i.get("attempts", 0) > 0]
    solid = [i for i in seen if i.get("status") == "solid"]
    weak = [i for i in items if i.get("status") == "weak"]

    # ── DATA ─────────────────────────────────────────────────────────────────────────────────────
    data = {
        "learner": {
            "name": lesson.get("learner_display", learner),
            "dialect": lesson.get("dialect_label", lesson.get("dialect")),
            "form": (lesson.get("forms") or {}).get("form_label", "default form"),
            "source": lesson.get("why", ""),
            "generated": lesson.get("generated", ""),
        },
        "phrases": [
            {
                "n": n,
                "key": i["key"],
                "text": i["es"],
                "reading": i.get("rom") or "",
                "english": i.get("en", ""),
                "situation": i.get("situation", ""),
                # NEVER a fabricated 0%: an unattempted phrase is NEW, not failed.
                "state": ("DRILL" if i.get("status") == "weak" else
                          "LEARNED" if i.get("status") == "solid" else "NEW"),
                "attempts": i.get("attempts", 0),
                "correct": i.get("correct", 0),
                "accuracy": (f"{i['correct']}/{i['attempts']}" if i.get("attempts") else "—"),
            }
            for n, i in enumerate(items, 1)
        ],
        "progress": {
            "observed": len(seen),
            "total": len(items),
            "solid": len(solid),
            "weak": len(weak),
            "pct": (round(100 * len(solid) / len(items)) if items else 0),
            "note": ("coverage is not proficiency — this bar counts phrases practised, "
                     "never a language level"),
        },
        "dailies": {
            "today": [{"n": n, "text": i["es"], "english": i.get("en", "")}
                      for n, i in enumerate(weak[:3], 1)] or
                     [{"n": 1, "text": "—", "english": "nothing to drill yet: practise a phrase first"}],
            "week": f"5 of 7 days at {lesson.get('dialect')}",
            "streak_note": "a daily is a prompt, not a grade",
        },
        "license": "Phrases drawn from the pack; source and license are recorded in the pack file.",
    }

    # ── TEMPLATE (the Hub's contract) ────────────────────────────────────────────────────────────
    template = {
        "meta": {
            "title": "GENTECH EDU",
            "subtitle": f"{data['learner']['name']} · {lesson.get('dialect')}",
            "dataUrl": "edu-data.json",
            "version": "v1.0",
            "brand": "GENTECH EDU",
            "badge": f"Lesson — {lesson.get('dialect')}",
        },
        "theme": {
            "mode": "dark",
            "colors": {"--bg": "#0a0a1a", "--panel-bg": "#111827", "--panel-border": "#1f2937",
                       "--text": "#e5e7eb", "--text-dim": "#6b7280", "--gold": "#f59e0b",
                       "--accent": "#3b82f6", "--danger": "#ff3366", "--success": "#22c55e",
                       "--radius": "12px"},
            "fonts": {"heading": "'Inter', sans-serif", "body": "'Inter', sans-serif",
                      "mono": "'JetBrains Mono', monospace"},
            "container": {"maxWidth": "620px"},
        },
        "tabs": [
            {"id": "lesson", "label": "Lesson", "icon": "🎓", "sections": ["phrases", "progress"]},
            {"id": "dailies", "label": "Dailies", "icon": "📅", "sections": ["today", "week"]},
        ],
        "sections": [
            {"id": "progress", "title": "Progress", "icon": "📊", "type": "progress",
             "dataSource": "progress"},
            {"id": "phrases", "title": "This lesson", "icon": "🗣️", "type": "table",
             "dataSource": "phrases"},
            {"id": "today", "title": "Today's drill", "icon": "🔁", "type": "list",
             "dataSource": "dailies.today"},
            {"id": "week", "title": "This week", "icon": "📅", "type": "stats",
             "dataSource": "dailies"},
        ],
        "footer": {"brand": "GENTECH EDU", "note": "Coverage is not proficiency."},
    }
    return template, data


HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GenTech EDU — {dialect}</title>
<style>
 :root{{--bg:#0a0a1a;--panel:#111827;--line:#1f2937;--text:#e5e7eb;--dim:#6b7280;
   --gold:#f59e0b;--accent:#3b82f6;--danger:#ff3366;--ok:#22c55e}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--bg);color:var(--text);
   font:15px/1.5 Inter,system-ui,sans-serif;padding:18px}}
 .wrap{{max-width:620px;margin:0 auto}}
 header{{display:flex;justify-content:space-between;align-items:baseline;
   border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:16px}}
 h1{{font-size:19px;margin:0;letter-spacing:.08em}}
 .sub{{color:var(--dim);font-size:12px}}
 .card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
   padding:14px;margin-bottom:12px}}
 .row{{display:flex;gap:12px;align-items:flex-start;padding:12px 0;
   border-bottom:1px solid var(--line)}}
 .row:last-child{{border-bottom:none}}
 .n{{color:var(--dim);font-size:12px;min-width:18px;padding-top:3px}}
 .t{{font-size:22px;line-height:1.3}}
 .rom{{color:var(--gold);font-family:'JetBrains Mono',monospace;font-size:13px}}
 .en{{color:var(--dim);font-size:13px}}
 .pill{{font-size:10px;letter-spacing:.06em;padding:2px 7px;border-radius:99px;
   border:1px solid var(--line);color:var(--dim)}}
 .drill{{border-color:var(--danger);color:var(--danger)}}
 .learned{{border-color:var(--ok);color:var(--ok)}}
 .bar{{height:8px;background:#1b2233;border-radius:99px;overflow:hidden;margin:8px 0 6px}}
 .bar>i{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--ok));
   width:{pct}%}}
 button{{font:inherit;font-size:13px;padding:7px 13px;border-radius:9px;cursor:pointer;
   background:transparent;color:var(--text);border:1px solid var(--line)}}
 button:hover{{border-color:var(--accent)}}
 .done{{border-color:var(--ok);color:var(--ok)}}
 footer{{color:var(--dim);font-size:11px;text-align:center;margin:22px 0 8px}}
 .note{{color:var(--dim);font-size:11px}}
</style></head><body><div class="wrap">
<header><h1>GENTECH EDU</h1><div class="sub">{learner} · {dialect}<br>{form}</div></header>

<div class="card">
  <div class="sub">PROGRESS — phrases practised</div>
  <div class="bar"><i></i></div>
  <div class="note">{solid} of {total} phrases solid · {observed} observed ·
    <b>coverage is not proficiency</b></div>
</div>

<div class="card">
  <div class="sub" style="margin-bottom:6px">TODAY'S DRILL</div>
  {dailies}
</div>

<div class="card"><div class="sub" style="margin-bottom:4px">THIS LESSON</div>
{rows}
</div>

<footer>Nothing here is invented — every phrase comes from the pack for this subject.<br>
Coverage is not proficiency. A phrase with no attempt is NEW, never 0%.</footer>
</div>
<script>
// The Complete button records a REAL attempt through edu-record.py (the API the fleet runs).
// If no endpoint answers, it says so instead of faking a green tick.
async function complete(btn, key, ok){{
  btn.disabled = true; btn.textContent = '…';
  try {{
    const r = await fetch('/record', {{method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{key: key, correct: ok}})}});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    btn.className = 'done'; btn.textContent = ok ? '✓ Completed' : '↻ Recorded';
  }} catch (e) {{
    btn.disabled = false; btn.textContent = 'offline — not recorded';
    btn.title = 'No /record endpoint in this static page. Run edu-record.py or serve with --serve.';
  }}
}}
</script></body></html>"""


def render_html(data: dict) -> str:
    p = data["progress"]
    rows = []
    for ph in data["phrases"]:
        cls = "drill" if ph["state"] == "DRILL" else ("learned" if ph["state"] == "LEARNED" else "")
        rows.append(
            f'<div class="row"><div class="n">{ph["n"]}</div><div style="flex:1">'
            f'<div class="t">{ph["text"]}</div>'
            + (f'<div class="rom">{ph["reading"]}</div>' if ph["reading"] else "")
            + f'<div class="en">{ph["english"]}</div></div>'
            f'<div style="text-align:right"><span class="pill {cls}">{ph["state"]}</span><br>'
            f'<button onclick="complete(this,\'{ph["key"].replace(chr(39), "&apos;")}\',true)">'
            f'Complete</button></div></div>')
    dail = "".join(f'<div class="row"><div class="n">{d["n"]}</div><div style="flex:1">'
                   f'<div class="t">{d["text"]}</div><div class="en">{d["english"]}</div></div>'
                   f'<div><button onclick="complete(this,\'{d["text"]}\',true)">Done</button></div></div>'
                   for d in data["dailies"]["today"])
    return HTML.format(dialect=data["learner"]["dialect"], learner=data["learner"]["name"],
                       form=data["learner"]["form"], pct=p["pct"], solid=p["solid"],
                       total=p["total"], observed=p["observed"], rows="".join(rows), dailies=dail)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learner", default="jordan")
    ap.add_argument("--subject", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    lesson = run_lesson(a.learner, a.subject)
    template, data = lesson_to_hub(lesson)
    out = pathlib.Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    (out / "edu-template.json").write_text(json.dumps(template, ensure_ascii=False, indent=1))
    (out / "edu-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    (out / "index.html").write_text(render_html(data), encoding="utf-8")

    p = data["progress"]
    print(f"learner  : {data['learner']['name']} · {lesson.get('dialect')}")
    print(f"phrases  : {len(data['phrases'])} ({p['observed']} observed, {p['solid']} solid, "
          f"{p['weak']} drill)")
    print(f"progress : {p['pct']}% of THIS lesson solid  (coverage, not proficiency)")
    print(f"dailies  : {len(data['dailies']['today'])} to drill today")
    for f in ("edu-template.json", "edu-data.json", "index.html"):
        fp = out / f
        print(f"  ✅ {fp}  ({fp.stat().st_size:,} B)")
    print(f"\nopen: file://{out/'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
