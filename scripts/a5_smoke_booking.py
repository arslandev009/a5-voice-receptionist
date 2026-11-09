"""A5 booking smoke test against the PUBLISHED n8n workflows (production URLs only).

Usage (from project root, venv active):
    python scripts/a5_smoke_booking.py

WARNING: this consumes two slots in the `slots` data table (it books them as
patient_name "Smoke Test"). Reset those rows before re-running.

Defaults use fictional seed data:
  slot A (sequential checks): 2026-11-10 17:00
  slot B (parallel race):     2026-11-12 17:30
Optional env: N8N_BASE (default http://localhost:5678)
Only the standard library is used.
"""
import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request

NAME = "Smoke Test"
PHONE = "0300-0000099"


def post(base: str, path: str, payload: dict):
    url = f"{base}/webhook/{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
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


def slots_for(base: str, date: str):
    status, data, raw = post(base, "check-availability", {"date": date})
    if not isinstance(data, dict) or not isinstance(data.get("slots"), list):
        return None, raw
    return data["slots"], raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-11-10")
    ap.add_argument("--time", default="17:00")
    ap.add_argument("--race-date", default="2026-11-12")
    ap.add_argument("--race-time", default="17:30")
    args = ap.parse_args()
    base = os.environ.get("N8N_BASE", "http://localhost:5678").rstrip("/")

    results = []

    def check(name: str, ok: bool, detail: str = ""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))

    good = {"date": args.date, "time": args.time, "patient_name": NAME, "phone": PHONE}

    before, raw = slots_for(base, args.date)
    check(f"slot {args.date} {args.time} is available first",
          before is not None and args.time in before, raw)

    bad = dict(good)
    bad.pop("phone")
    _, d, raw = post(base, "book-appointment", bad)
    check("missing phone is rejected (invalid_input)",
          isinstance(d, dict) and d.get("booked") is False and d.get("reason") == "invalid_input", raw)

    after_bad, raw = slots_for(base, args.date)
    check("rejected request did not consume the slot",
          after_bad is not None and args.time in after_bad, raw)

    _, d, raw = post(base, "book-appointment", good)
    check("valid booking succeeds", isinstance(d, dict) and d.get("booked") is True, raw)

    after, raw = slots_for(base, args.date)
    check("booked slot disappears from availability",
          after is not None and args.time not in after, raw)

    _, d, raw = post(base, "book-appointment", good)
    check("booking the same slot again is refused (slot_unavailable)",
          isinstance(d, dict) and d.get("booked") is False and d.get("reason") == "slot_unavailable", raw)

    race = {"date": args.race_date, "time": args.race_time, "patient_name": NAME, "phone": PHONE}
    race_before, raw = slots_for(base, args.race_date)
    if race_before is None or args.race_time not in race_before:
        check(f"race slot {args.race_date} {args.race_time} is available first", False, raw)
    else:
        outs = []
        gate = threading.Barrier(2)

        def worker():
            gate.wait()
            outs.append(post(base, "book-appointment", race))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wins = sum(1 for _, d, _ in outs if isinstance(d, dict) and d.get("booked") is True)
        check("two parallel bookings of one slot: exactly one wins", wins == 1,
              f"wins={wins} replies={[o[2] for o in outs]}")

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
