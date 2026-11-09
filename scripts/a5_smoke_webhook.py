"""A5 smoke test: POST to the n8n check-availability webhook and validate the reply.

Usage (from project root, venv active):
    python scripts/a5_smoke_webhook.py            # test URL (workflow must be "listening")
    python scripts/a5_smoke_webhook.py --prod     # production URL (workflow must be Active)
    python scripts/a5_smoke_webhook.py --date 2026-11-10 --expect "17:00,18:00"   # also check the values
    python scripts/a5_smoke_webhook.py --date 2026-11-11 --expect none            # expect no slots

Optional env: N8N_BASE (default http://localhost:5678), WEBHOOK_PATH (default check-availability)
Only the standard library is used, so no pip install is needed.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", action="store_true", help="use /webhook/ instead of /webhook-test/")
    ap.add_argument("--date", default="2026-11-10", help="YYYY-MM-DD to ask about")
    ap.add_argument(
        "--expect",
        default=None,
        help='comma-separated expected slots, e.g. "17:00,18:00"; use "none" for an empty list',
    )
    args = ap.parse_args()

    base = os.environ.get("N8N_BASE", "http://localhost:5678").rstrip("/")
    path = os.environ.get("WEBHOOK_PATH", "check-availability")
    prefix = "webhook" if args.prod else "webhook-test"
    url = f"{base}/{prefix}/{path}"

    body = json.dumps({"date": args.date}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    print(f"POST {url}  body={body.decode()}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"FAIL: HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        return 1
    except Exception as e:  # connection refused, timeout, ...
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1

    print(f"HTTP {status}\n{raw}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("FAIL: reply is not JSON")
        return 1

    slots = data.get("slots") if isinstance(data, dict) else None
    if not isinstance(slots, list) or not all(isinstance(s, str) for s in slots):
        print('FAIL: expected {"slots": ["HH:MM", ...]}')
        return 1

    if args.expect is not None:
        expected = [] if args.expect.strip().lower() == "none" else [
            x.strip() for x in args.expect.split(",") if x.strip()
        ]
        if sorted(slots) != sorted(expected):
            print(f"FAIL: expected {sorted(expected)} but got {sorted(slots)}")
            return 1

    print(f"OK: {len(slots)} slot(s): {slots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
