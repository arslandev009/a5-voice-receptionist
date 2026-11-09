# A5 Voice Receptionist: setup, run and test

This file explains how the project is put together and how to run it on Windows.
Everything below was actually run while building the project, except where a
section says "not tested".

## What is in the repo

| Path | What it is |
|---|---|
| `docker-compose.yml` | Runs n8n 2.46.6 in Docker on port 5678 (data kept in the `n8n_data` volume) |
| `.env.example` | Names of the two secrets. The real `.env` is git-ignored |
| `data/slots_seed.csv` | Fictional appointment slots for 10, 11 and 12 November 2026 |
| `workflows/*.json` | Exports of the four n8n workflows (documentation, see "Not tested") |
| `ngrok-policy.yml` | ngrok rule: only `/webhook/vapi-tools` is forwarded, every other path gets 404 |
| `scripts/a5_smoke_webhook.py` | Checks `check-availability` values per date |
| `scripts/a5_smoke_booking.py` | Checks booking: validation, double booking, parallel race |
| `scripts/a5_smoke_vapi_adapter.py` | Checks the VAPI adapter and the shared secret |
| `docs/vapi_assistant.md` | Assistant prompt, tools and credential settings for the VAPI dashboard |

## How one call flows

1. A caller talks to the VAPI assistant. Speech is turned into text, the model answers.
2. When the model needs data it calls a tool (`check_availability` or `book_appointment`).
   VAPI sends a `tool-calls` message over HTTPS to the ngrok address, with the header `x-a5-secret`.
3. ngrok forwards only `/webhook/vapi-tools` to local n8n port 5678 and answers 404 for anything else.
4. n8n workflow `a5-vapi-tools` checks the header (403 if wrong), parses the tool calls,
   calls the matching local webhook, and wraps the result as `{"results":[{"toolCallId","result"}]}`.
5. `a5-check-availability` returns `{"slots":["17:00",...]}` for a date.
   `a5-book-appointment` validates the input, then runs one update on the `slots` data table
   that only matches a row with `status = available`. It answers `booked: true`,
   or `booked: false` with `slot_unavailable` or `invalid_input`.
6. The assistant reads the result to the caller.

The two raw webhooks have no password. They are meant to be reached only from
local n8n and from the smoke scripts on localhost, never through the tunnel.

## The four n8n workflows

- `a5-check-availability`: Webhook (POST, path `check-availability`) -> Get row(s) on `slots`
  (`date` equals the request date, `status` equals `available`, Must Match: All Conditions,
  Always Output Data on) -> Code (filters again by date and status, sorts the times) -> Respond to Webhook.
- `a5-book-appointment`: Webhook (POST, path `book-appointment`) -> Code `Validate`
  (date `YYYY-MM-DD`, time `HH:MM`, name 1 to 60 characters, phone 7 to 20 characters of digits, plus, minus, space)
  -> If -> Update row(s) on `slots` (match `date`, `time`, `status = available`; set `status = booked`,
  `patient_name`, `phone`; Always Output Data on) -> Code `Result`; the false branch goes to Code `InvalidReply`;
  both end in one Respond to Webhook.
- `a5-vapi-tools`: Webhook (POST, path `vapi-tools`, Authentication: Header Auth) -> Code `Parse`
  -> HTTP Request (POST to `http://localhost:5678/webhook/<route>`, On Error: continue) -> Code `Wrap`
  -> Respond to Webhook. Unknown tool names give `{"error":"unknown_tool"}`; a message that is not a
  tool call gets `{"results":[]}`.
- `a5-reset-smoke-slots`: Manual Trigger -> Update row(s) where `patient_name` equals `Smoke Test`
  (exact match, case-sensitive) -> sets `status = available`. It does not clear name or phone.
  Never published; run it by hand with Execute workflow.

## Setup from scratch

Needs: Windows, Docker Desktop, Python 3 (the scripts use only the standard library),
a free ngrok account with a static domain, a VAPI account with credits.

1. Project folder, virtual environment, secrets (the `.env` is never committed):

```powershell
cd "E:\Mission 5 AI\ai-studio-scaffold\ai-studio\projects\a5-voice-receptionist"
python -m venv .venv
.\.venv\Scripts\Activate.ps1

if (-not (Test-Path .env)) {
  $key = python -c "import secrets; print(secrets.token_hex(32))"
  Set-Content -Path .env -Value "N8N_ENCRYPTION_KEY=$key" -Encoding ascii
}
if (-not (Select-String -Path .env -Pattern '^A5_VAPI_SECRET=' -Quiet)) {
  $s = python -c "import secrets; print(secrets.token_urlsafe(32))"
  Add-Content -Path .env -Value "A5_VAPI_SECRET=$s" -Encoding ascii
}
```

2. Start n8n and wait about a minute, then open http://localhost:5678 and create the owner account:

```powershell
docker compose up -d
docker compose ps
```

3. In n8n create the data table `slots` with "Import CSV" from `data/slots_seed.csv`.
   Set the column `date` to **String** (n8n guesses Datetime, which causes timezone surprises).
   The other columns stay String.

4. Build the four workflows as described above (the JSON files in `workflows/` show the exact nodes).
   For `a5-vapi-tools` create a Header Auth credential named `a5-vapi-secret`: Name `x-a5-secret`,
   Value = the `A5_VAPI_SECRET` from `.env`. Publish `a5-check-availability`, `a5-book-appointment`
   and `a5-vapi-tools`. Do not publish the reset workflow.

5. Load the secret into the shell and run the local checks (the scripts only print pass or fail, not the secret):

```powershell
$s = ((Select-String -Path .env -Pattern '^A5_VAPI_SECRET=').Line).Split('=',2)[1]
$env:A5_VAPI_SECRET = $s
Remove-Item Env:N8N_BASE -ErrorAction SilentlyContinue

python scripts\a5_smoke_webhook.py --prod --date 2026-11-10 --expect "17:00,18:00"
python scripts\a5_smoke_webhook.py --prod --date 2026-11-11 --expect none
python scripts\a5_smoke_webhook.py --prod --date 2026-11-12 --expect "17:30,18:00"
python scripts\a5_smoke_vapi_adapter.py
```

6. Expose n8n with ngrok (use ngrok 3.39 or newer, older 3.3.1 has no `--url`). Keep this window open:

```powershell
ngrok http 5678 --url https://<your-ngrok-domain> --traffic-policy-file ngrok-policy.yml
```

   Check the tunnel with the adapter test (booking is not reachable through the tunnel, by design):

```powershell
$env:N8N_BASE = "https://<your-ngrok-domain>"
python scripts\a5_smoke_vapi_adapter.py
```

7. In the VAPI dashboard create the custom credential, the two tools and the assistant as written in
   `docs/vapi_assistant.md`. The credential token is the `A5_VAPI_SECRET` value.

8. Talk to the assistant from the dashboard. Give the name `Smoke Test` exactly, so the reset workflow can find the row.

## Tests and what they change

| Command | Checks | Changes data |
|---|---|---|
| `a5_smoke_webhook.py --prod --date D --expect "t1,t2"` (or `--expect none`) | Slots returned for date D | No |
| `a5_smoke_booking.py` | Validation, booking, double booking, parallel race | Yes: books 2026-11-10 17:00 and 2026-11-12 17:30 as `Smoke Test` |
| `a5_smoke_vapi_adapter.py` | Secret required, tool-call formats, unknown tool, several calls | No |

`a5_smoke_booking.py` and `a5_smoke_webhook.py` call the raw webhooks, so run them against localhost only.
After a booking test or a call, run `a5-reset-smoke-slots` in n8n, then re-run the three date checks above.

## After a PC restart

1. Start Docker Desktop, then `docker compose up -d`.
2. Wait 30 to 60 seconds. Right after a restart n8n answers 404 for webhooks until they are registered.
3. Start ngrok again with the command from step 6.

## What went wrong before (and why)

- 404 `Cannot POST /webhook/...` right after a restart: n8n had not registered webhooks yet, wait and retry.
- 502 from ngrok: the n8n container was not running.
- 403 on `/webhook/vapi-tools`: wrong or missing `x-a5-secret`. The VAPI dashboard "Test Tool" runs in the
  browser and does not send the credential header, so it always gets 403; use a real call.
- A booking saved as `Smoke test` (lowercase t) is not found by the reset workflow.
- The VAPI call log file contains the `x-a5-secret` value in plain text. Do not share or commit it.

## Verification status

Checked:

- All three scripts against local n8n; the adapter script also through the ngrok tunnel.
- One real VAPI web call (dashboard Talk, 2026-11-07): both tools got HTTP 200 and the header was accepted;
  the booking for 2026-11-10 17:00 succeeded.

Not tested:

- Importing `workflows/*.json` into a fresh n8n. The exports mention the data table and the credential by
  internal id, so after an import you probably need to re-select `slots` in the data-table nodes and
  re-attach the credential. The owner label in the exports was replaced by `Personal` by hand.
- More than one real call, other languages, noisy audio, a real phone number.
- Running on anything other than Windows with Docker Desktop.
- Secret rotation after the first call (the new VAPI token has not been used in a call).
