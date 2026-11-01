#!/usr/bin/env python3
"""TOOL-42 demo — does a REAL model act on the rejection, or just repeat itself?

The claim under test is not "the validator works" (the selftest proves that). It is:
    **the rejection message is something a model can act on.**

So this measures two things, and refuses to conflate them:

  A. NATURAL RATE — give the model the tool and a request, see whether it emits a wrong type on its own.
     If the model never errs, the retry path is untested by nature and I say so instead of claiming it.
  B. FORCED CORRECTION — hand the model a malformed call *as its own* plus our rejection text, and see
     whether it fixes it. This is the actual product claim: the error message teaches.

Both halves write through toolgate's real validate/call path, so the failure log fills with real classes.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import urllib.request
import uuid

sys.path.insert(0, "/opt/data/profiles/arthur/scripts")
spec = importlib.util.spec_from_file_location("tg", "/opt/data/profiles/arthur/scripts/toolgate.py")
tg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tg)

ENV = pathlib.Path("/opt/data/profiles/arthur/.env")
URL = "https://opencode.ai/zen/go/v1/chat/completions"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")
MODEL = "kimi-k2.7-code"

REQUESTS = [
    "What is the price of 2 BTC in USD?",
    "Price check: 0.5 ETH, euros please.",
    "I want 1500 USDC quoted in USD.",
]


def key() -> str:
    for line in ENV.read_text().splitlines():
        if line.strip().startswith("OPENCODE_GO_API_KEY="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return v
    raise SystemExit("🔴 no key")


def ask(prompt: str) -> dict:
    body = json.dumps({"model": MODEL, "max_tokens": 14000,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Authorization": f"Bearer {key()}", "Content-Type": "application/json",
        "x-opencode-session": str(uuid.uuid4()), "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        payload = json.load(r)
    msg = (payload.get("choices") or [{}])[0].get("message", {})
    text = msg.get("content") or msg.get("reasoning_content") or ""
    text = re.sub(r"^\s*```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"_unparsed": text[:200]}


# ⚠️ The prompts below contain LITERAL JSON braces. Never .format() them — it raises KeyError on
# '"name"'. Use explicit .replace() substitution.
TOOL_JSON = json.dumps({k: v for k, v in tg.PRICE_TOOL.items() if k != "additional_properties"}, indent=1)

CALL_PROMPT = """You have exactly one tool. Respond with ONLY the tool call as JSON:
{"name":"get_price","arguments":{...}}

TOOL SCHEMA:
{tool}

USER REQUEST: {req}

JSON only, no prose."""

RETRY_PROMPT = """You tried to call a tool and it REJECTED your arguments:

{rejection}

TOOL SCHEMA:
{tool}

USER REQUEST: {req}

Send the corrected tool call. Respond with ONLY JSON:
{"name":"get_price","arguments":{...}}"""


def main() -> int:
    out = pathlib.Path("/opt/data/profiles/arthur/cache/toolgate")
    out.mkdir(parents=True, exist_ok=True)
    results = {"model": MODEL, "natural": [], "forced": []}

    print("── A. NATURAL RATE — does the model err on its own? ──")
    for i, req in enumerate(REQUESTS, 1):
        got = ask(CALL_PROMPT.replace("{tool}", TOOL_JSON).replace("{req}", req))
        args = got.get("arguments", got) if isinstance(got, dict) else {}
        cleaned, problems, cls = tg.validate(tg.PRICE_TOOL, args)
        ok = not problems
        print(f"  req {i}: {'VALID' if ok else 'REJECTED ' + cls:22s} args={json.dumps(args)[:90]}")
        if not ok:
            tg.log_failure("get_price", cls, 1, args, problems, run_id=f"natural-{i}")
        results["natural"].append({"request": req, "args": args, "ok": ok, "class": cls,
                                   "problems": problems})
        # if it did err, run the forced correction on the SAME case and record it
        if not ok:
            rej = tg.ToolError(cls, "get_price", problems).render()
            got2 = ask(RETRY_PROMPT.replace("{rejection}", rej).replace("{tool}", TOOL_JSON).replace("{req}", req))
            args2 = got2.get("arguments", got2) if isinstance(got2, dict) else {}
            _, p2, c2 = tg.validate(tg.PRICE_TOOL, args2)
            r_ok = not p2
            print(f"          ↳ after rejection: {'CORRECTED' if r_ok else 'STILL BAD (' + c2 + ')'}"
                  f"  args={json.dumps(args2)[:80]}")
            results["forced"].append({"request": req, "args": args2, "ok": r_ok, "class": c2})

    # ── B. FORCED CORRECTION — a deliberately malformed call, the exact ticket scenario ─────────────
    print("\n── B. FORCED — the ticket's exact bug: quantity sent as a string ──")
    bad_args = {"symbol": "BTC", "quantity": "2", "currency": "USD"}
    cleaned, problems, cls = tg.validate(tg.PRICE_TOOL, bad_args)
    rej = tg.ToolError(cls, "get_price", problems).render()
    print("  rejection text handed to the model:")
    for line in rej.splitlines():
        print(f"    {line}")
    req = REQUESTS[0]
    got3 = ask(RETRY_PROMPT.replace("{rejection}", rej).replace("{tool}", TOOL_JSON).replace("{req}", req))
    args3 = got3.get("arguments", got3) if isinstance(got3, dict) else {}
    _, p3, c3 = tg.validate(tg.PRICE_TOOL, args3)
    ok3 = not p3
    print(f"\n  model returned: {json.dumps(args3)[:110]}")
    print(f"  → {'✅ CORRECTED' if ok3 else '🔴 STILL INVALID (' + c3 + ')'}")
    results["forced"].append({"request": req, "case": "ticket scenario", "args": args3,
                              "ok": ok3, "class": c3})

    # ── the real tool path, end to end, through toolgate.call ───────────────────────────────────────
    print("\n── C. END-TO-END through toolgate.call (fail closed proven on the real tool) ──")
    r = tg.call(tg.PRICE_TOOL, bad_args, tg._price, ask_model_again=lambda m: {"symbol": "BTC", "quantity": 2, "currency": "USD"})
    print(f"  recovered: ok={r['ok']} retry_used={r['retry_used']} total={r.get('value',{}).get('total')}")
    r2 = tg.call(tg.PRICE_TOOL, bad_args, tg._price, ask_model_again=lambda m: bad_args)
    print(f"  repeated mistake: ok={r2['ok']} exhausted={r2['exhausted']} value={'value' in r2}")

    results["failure_counts"] = tg.counts()
    (out / "demo.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"\n── FAILURE LOG ({out/'failures.jsonl'}) ──")
    for k, v in sorted(results["failure_counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {k:20s} {v}")
    print(f"\n✅ {out/'demo.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
