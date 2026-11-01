#!/usr/bin/env python3
"""toolgate — strict tool schemas, actionable rejections, ONE retry, then fail closed.

TOOL-42: "The agent calls the pricing tool and sometimes passes a string where a number belongs."

THE RULE THIS FILE ENFORCES
  A tool that accepts junk and returns a plausible number is worse than a tool that refuses.
  A model cannot debug a stack trace, so every rejection is written FOR THE MODEL: name the field,
  name what it expected, name what arrived, and show the shape that would pass.

    Invalid arguments for `get_price`:
      - quantity: expected a number, received the string "5". Send it as a JSON number: 5
    Fix these and call `get_price` again.

  After ONE retry the tool FAILS CLOSED — it returns a structured failure and never a value. The
  caller must surface it, not smooth it over.

WHY ONE RETRY, NOT THREE
  Measured prompt-loop behaviour: the second attempt mostly succeeds when the error is concrete.
  A third attempt mostly burns tokens on the same mistake. One retry, then stop and say so.

FAILURE CLASSES (the enum OPS-114's dashboard counts)
  missing_required · wrong_type · enum_violation · out_of_range · unexpected_field · retry_exhausted
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid

LOG_PATH = pathlib.Path(os.environ.get(
    "TOOLGATE_LOG", "/opt/data/profiles/arthur/cache/toolgate/failures.jsonl"))

TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict,
         "array": list}


class ToolError(Exception):
    """A rejection the MODEL can act on. `message` is written to be pasted back into a prompt."""

    def __init__(self, cls: str, tool: str, problems: list[str]):
        self.cls = cls
        self.tool = tool
        self.problems = problems
        super().__init__(self.render())

    def render(self) -> str:
        head = f"Invalid arguments for `{self.tool}`:"
        body = "\n".join(f"  - {p}" for p in self.problems)
        tail = f"Fix these and call `{self.tool}` again."
        return f"{head}\n{body}\n{tail}"


def _typename(v) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, str):
        return f'the string "{v}"'
    if isinstance(v, (int, float)):
        return f"the number {v}"
    if isinstance(v, list):
        return "an array"
    if isinstance(v, dict):
        return "an object"
    return f"{type(v).__name__}"


def validate(spec: dict, args: dict) -> tuple[dict, list[str], str]:
    """Returns (cleaned_args, problems, failure_class). problems == [] means valid.

    Strict on purpose:
      · required fields must be present and non-null
      · types are exact — a numeric STRING is rejected, never silently coerced, because coercion is how
        "5" becomes 5 in one place and "5 apples" becomes 0 somewhere else with no error
      · enums and ranges are checked at the boundary, not inside the tool body
    """
    tool = spec["name"]
    params = spec["params"]
    problems: list[str] = []
    classes: list[str] = []
    cleaned: dict = {}

    for name, rule in params.items():
        want = rule["type"]
        py = TYPES.get(want)
        if name not in args or args[name] is None:
            if rule.get("required", True):
                problems.append(f"{name}: required, but it was not sent. Send a {want}"
                                + (f" (one of: {', '.join(rule['enum'])})" if rule.get("enum") else ""))
                classes.append("missing_required")
            continue
        val = args[name]
        ok = isinstance(val, py) if py else True
        if want in ("number", "integer") and isinstance(val, bool):
            ok = False                       # bool is an int in Python — the classic silent pass
        if not ok:
            hint = ""
            if want in ("number", "integer") and isinstance(val, str):
                try:
                    hint = f" Send it as a JSON number: {float(val):g}"
                except Exception:
                    hint = " Send it as a JSON number, e.g. 5"
            problems.append(f"{name}: expected a {want}, received {_typename(val)}.{hint}")
            classes.append("wrong_type")
            continue
        if rule.get("enum") and val not in rule["enum"]:
            problems.append(f"{name}: must be one of {', '.join(map(str, rule['enum']))}, "
                            f"received {val!r}.")
            classes.append("enum_violation")
            continue
        if rule.get("min") is not None and val < rule["min"]:
            problems.append(f"{name}: must be >= {rule['min']}, received {val}.")
            classes.append("out_of_range")
            continue
        if rule.get("max") is not None and val > rule["max"]:
            problems.append(f"{name}: must be <= {rule['max']}, received {val}.")
            classes.append("out_of_range")
            continue
        cleaned[name] = val

    extra = [k for k in args if k not in params]
    if extra and spec.get("additional_properties") is False:
        problems.append(f"{', '.join(extra)}: not part of this tool's schema. Allowed: "
                        f"{', '.join(params)}.")
        classes.append("unexpected_field")

    return cleaned, problems, (classes[0] if classes else "")


def log_failure(tool: str, cls: str, attempt: int, args: dict, problems: list[str],
                run_id: str | None = None) -> None:
    """Structured JSONL — one line per rejection, so a dashboard counts classes, not strings."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id or str(uuid.uuid4()),
        "tool": tool,
        "class": cls,
        "attempt": attempt,
        "terminal": cls in ("retry_exhausted", "missing_required") and attempt >= 2,
        # SHAPE ONLY — never the values, so a log cannot leak a customer's data
        "arg_shape": {k: type(v).__name__ for k, v in (args or {}).items()},
        "problems": problems[:4],
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def call(spec: dict, args: dict, fn, ask_model_again=None, run_id: str | None = None) -> dict:
    """Validate → call. On rejection: log it, hand the message back for ONE retry, then fail closed.

    Returns {"ok": True, "value": ...} or
            {"ok": False, "class": ..., "message": ..., "retry_used": bool, "exhausted": bool}
    NEVER returns a made-up value on failure — fail closed is the whole point.
    """
    tool = spec["name"]
    run_id = run_id or str(uuid.uuid4())

    cleaned, problems, cls = validate(spec, args)
    if not problems:
        return {"ok": True, "value": fn(**cleaned), "retry_used": False}

    log_failure(tool, cls, 1, args, problems, run_id)
    first_message = ToolError(cls, tool, problems).render()

    if ask_model_again is None:
        return {"ok": False, "class": cls, "message": first_message,
                "retry_used": False, "exhausted": True}

    # ONE retry, with the rejection text as the only new information
    retry_args = ask_model_again(first_message)
    cleaned2, problems2, cls2 = validate(spec, retry_args or {})
    if not problems2:
        return {"ok": True, "value": fn(**cleaned2), "retry_used": True}

    # ONE record per rejection. Earlier version wrote BOTH the violation class and retry_exhausted for
    # the same event, so a dashboard counting classes double-counted every exhausted retry. The terminal
    # fact is "retry_exhausted"; the underlying violation travels in `problems`.
    log_failure(tool, "retry_exhausted", 2, retry_args or {}, problems2, run_id)
    return {"ok": False, "class": cls2, "message": ToolError(cls2, tool, problems2).render(),
            "retry_used": True, "exhausted": True}


# ── the tool under test: a pricing tool with a numeric field ────────────────────────────────────────
PRICE_TOOL = {
    "name": "get_price",
    "description": "Latest price for one asset. quantity must be a JSON number.",
    "additional_properties": False,
    "params": {
        "symbol":   {"type": "string",  "required": True, "enum": ["BTC", "ETH", "USDC", "SOL"]},
        "quantity": {"type": "number",  "required": True, "min": 0, "max": 1_000_000},
        "currency": {"type": "string",  "required": True, "enum": ["USD", "EUR"]},
    },
}


def _price(symbol: str, quantity: float, currency: str) -> dict:
    base = {"BTC": 67000.0, "ETH": 3300.0, "USDC": 1.0, "SOL": 150.0}[symbol]
    if currency == "EUR":
        base *= 0.92
    return {"symbol": symbol, "unit": round(base, 2), "quantity": quantity,
            "total": round(base * quantity, 2), "currency": currency}


# ── selftest — every guard tested in the direction that BLOCKS ─────────────────────────────────────
def selftest() -> int:
    # ⚠️ Isolate the log: a selftest that writes into the production failure log inflates the counts a
    # dashboard reads. Measured 2026-10-28 — the demo's counts were 6 wrong_type, but only 2 were real.
    global LOG_PATH
    _real_log = LOG_PATH
    LOG_PATH = pathlib.Path("/tmp/toolgate-selftest.jsonl")
    LOG_PATH.unlink(missing_ok=True)
    try:
        return _selftest_body()
    finally:
        LOG_PATH.unlink(missing_ok=True)
        LOG_PATH = _real_log


def _selftest_body() -> int:
    trials = [
        # name,                                  args,                                                    expect_ok, expect_class
        ("valid numbers pass",                    {"symbol": "BTC", "quantity": 2, "currency": "USD"},      True,  ""),
        ("numeric STRING is rejected",            {"symbol": "BTC", "quantity": "2", "currency": "USD"},    False, "wrong_type"),
        ("'5 apples' is rejected",                {"symbol": "BTC", "quantity": "5 apples", "currency": "USD"}, False, "wrong_type"),
        ("bool cannot pose as a number",          {"symbol": "BTC", "quantity": True, "currency": "USD"},   False, "wrong_type"),
        ("missing field",                         {"symbol": "BTC", "currency": "USD"},                     False, "missing_required"),
        ("bad enum",                              {"symbol": "DOGE", "quantity": 1, "currency": "USD"},     False, "enum_violation"),
        ("out of range",                          {"symbol": "BTC", "quantity": -3, "currency": "USD"},     False, "out_of_range"),
        ("unexpected field",                      {"symbol": "BTC", "quantity": 1, "currency": "USD", "x": 1}, False, "unexpected_field"),
        ("float is fine",                         {"symbol": "ETH", "quantity": 0.5, "currency": "EUR"},    True,  ""),
    ]
    bad = 0
    for name, args, want_ok, want_cls in trials:
        cleaned, problems, cls = validate(PRICE_TOOL, args)
        ok = not problems
        good = (ok == want_ok) and (not problems or cls == want_cls)
        bad += 0 if good else 1
        print(f"  {'✅' if good else '🔴'} {name:34s} ok={ok!s:5s} class={cls or '-'}")

    # the retry path: first call bad, model corrects it, tool succeeds
    print("\n  retry path")
    calls = {"n": 0}

    def ask(msg: str):
        calls["n"] += 1
        assert "quantity" in msg and "JSON number" in msg, "rejection must name the field and the fix"
        return {"symbol": "BTC", "quantity": 2, "currency": "USD"}

    r = call(PRICE_TOOL, {"symbol": "BTC", "quantity": "2", "currency": "USD"}, _price, ask)
    good = r["ok"] and r["retry_used"] and calls["n"] == 1
    bad += 0 if good else 1
    print(f"  {'✅' if good else '🔴'} corrects after one actionable rejection → total {r.get('value',{}).get('total')}")

    # the fail-closed path: model repeats the SAME mistake → never a value
    print("\n  fail-closed path")
    def ask_bad(msg: str):
        return {"symbol": "BTC", "quantity": "2", "currency": "USD"}
    r2 = call(PRICE_TOOL, {"symbol": "BTC", "quantity": "2", "currency": "USD"}, _price, ask_bad)
    good = (not r2["ok"]) and r2["exhausted"] and "value" not in r2
    bad += 0 if good else 1
    print(f"  {'✅' if good else '🔴'} repeated mistake → ok={r2['ok']} exhausted={r2['exhausted']} "
          f"value_present={'value' in r2}")

    print(f"\n  {'ALL PASS' if bad == 0 else str(bad) + ' FAILED'}")
    return 1 if bad else 0


def counts() -> dict:
    if not LOG_PATH.exists():
        return {}
    out: dict = {}
    for line in LOG_PATH.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        out[rec["class"]] = out.get(rec["class"], 0) + 1
    return out


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if "--counts" in sys.argv:
        c = counts()
        print(f"  failure log: {LOG_PATH}  ({sum(c.values())} records)")
        for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
            print(f"    {k:20s} {v}")
        raise SystemExit(0)
    print(__doc__)
