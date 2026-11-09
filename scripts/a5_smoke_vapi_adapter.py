"""A5 smoke test for the VAPI adapter webhook (a5-vapi-tools), production URL.

Usage (from project root, venv active):
    python scripts/a5_smoke_vapi_adapter.py

It sends messages shaped like VAPI "tool-calls" server messages and checks the
reply contract: HTTP 200, {"results": [{"toolCallId", "result"}]} with result a string.
No slot is consumed (booking is only tried with a missing phone).
The adapter webhook is protected by a shared secret sent in the x-a5-secret header;
set A5_VAPI_SECRET in the environment (the value is never printed).
Reads seed data: 2026-11-10 has 17:00 and 18:00 available, 2026-11-11 has none.
Required env: A5_VAPI_SECRET
Optional env: N8N_BASE (default http://localhost:5678), ADAPTER_PATH (default vapi-tools)
Only the standard library is used.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def post(url: str, payload: dict, secret: str = ""):
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-a5-secret"] = secret
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        return e.code, None, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"
    try:
        return status, json.loads(raw), raw
    except json.JSONDecodeError:
        return status, None, raw


def tool_call(call_id: str, name: str, arguments, nested: bool = False) -> dict:
    if nested:  # OpenAI-style: function.name / function.arguments (arguments as a JSON string)
        return {"id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)}}
    return {"id": call_id, "name": name, "arguments": arguments}


def message(calls: list) -> dict:
    return {"message": {"type": "tool-calls", "toolCallList": calls,
                        "call": {"id": "smoke-call", "type": "webCall"}}}


def parse_result(data, idx=0):
    """Return (toolCallId, parsed result JSON) or (None, None) if the contract is broken."""
    try:
        item = data["results"][idx]
        if not isinstance(item["result"], str):
            return None, None
        return item["toolCallId"], json.loads(item["result"])
    except Exception:
        return None, None


def main() -> int:
    base = os.environ.get("N8N_BASE", "http://localhost:5678").rstrip("/")
    path = os.environ.get("ADAPTER_PATH", "vapi-tools")
    url = f"{base}/webhook/{path}"
    secret = os.environ.get("A5_VAPI_SECRET", "")
    if not secret:
        print("FAIL: set A5_VAPI_SECRET in the environment first")
        return 2
    results = []

    def check(name: str, ok: bool, detail: str = ""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))

    probe = message([tool_call("p0", "check_availability", {"date": "2026-11-10"})])
    st0, _, raw0 = post(url, probe)
    check("request without the secret is rejected (401/403)", st0 in (401, 403), f"HTTP {st0}")
    st1, _, raw1 = post(url, probe, secret="definitely-wrong-secret")
    check("request with a wrong secret is rejected (401/403)", st1 in (401, 403), f"HTTP {st1}")

    st, d, raw = post(url, message([tool_call("c1", "check_availability", {"date": "2026-11-10"})]), secret)
    cid, res = parse_result(d)
    check("check_availability returns the available slots",
          st == 200 and cid == "c1" and isinstance(res, dict)
          and sorted(res.get("slots", [])) == ["17:00", "18:00"], raw)

    st, d, raw = post(url, message([tool_call("c2", "check_availability", {"date": "2026-11-10"}, nested=True)]), secret)
    cid, res = parse_result(d)
    check("OpenAI-style call (function.arguments as JSON string) also works",
          st == 200 and cid == "c2" and isinstance(res, dict)
          and sorted(res.get("slots", [])) == ["17:00", "18:00"], raw)

    st, d, raw = post(url, message([tool_call(
        "c3", "book_appointment",
        {"date": "2026-11-10", "time": "17:00", "patient_name": "Smoke Test"})]), secret)
    cid, res = parse_result(d)
    check("book_appointment with missing phone is rejected, no slot consumed",
          st == 200 and cid == "c3" and isinstance(res, dict)
          and res.get("booked") is False and res.get("reason") == "invalid_input", raw)

    st, d, raw = post(url, message([tool_call("c4", "delete_everything", {})]), secret)
    cid, res = parse_result(d)
    check("unknown tool gets an error result (not a crash)",
          st == 200 and cid == "c4" and isinstance(res, dict) and res.get("error") == "unknown_tool", raw)

    st, d, raw = post(url, message([
        tool_call("a", "check_availability", {"date": "2026-11-10"}),
        tool_call("b", "check_availability", {"date": "2026-11-11"})]), secret)
    id0, r0 = parse_result(d, 0)
    id1, r1 = parse_result(d, 1)
    check("two tool calls in one message keep ids and order",
          st == 200 and isinstance(d, dict) and len(d.get("results", [])) == 2
          and id0 == "a" and id1 == "b"
          and isinstance(r0, dict) and sorted(r0.get("slots", [])) == ["17:00", "18:00"]
          and isinstance(r1, dict) and r1.get("slots") == [], raw)

    st, d, raw = post(url, {"message": {"type": "status-update", "status": "in-progress"}}, secret)
    check("non tool-calls message gets HTTP 200 and empty results",
          st == 200 and isinstance(d, dict) and d.get("results") == [], raw)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
