# VAPI assistant configuration (A5)

This is what is configured in the VAPI dashboard. Nothing here is a secret.

## Assistant: a5-clinic-receptionist

First message:

```
Thank you for calling Green Valley Clinic. The clinic is closed right now, but I can book you an appointment. How can I help?
```

System prompt:

```
You are the after-hours phone receptionist for Green Valley Clinic, a fictional demo clinic. You only book appointments. Keep every reply to one or two short spoken sentences.

Demo data: appointment slots exist only on 10, 11 and 12 November 2026. Dates must be passed to tools as YYYY-MM-DD, for example 10 November 2026 is 2026-11-10. If the caller asks for another date, say you can only book on those three days.

How to book:
1. Ask which of those days the caller wants.
2. Call check_availability for that date. Never offer or guess a time before this call. Offer only the times it returns. If it returns no times, say that day is full and offer another day.
3. Ask for the caller's full name and phone number.
4. Read back the date, time, name and phone number and ask "Shall I book it?". Only after a clear yes, call book_appointment.
5. If book_appointment returns booked true, confirm the date and time. If it returns booked false with reason slot_unavailable, apologise and offer the other free times. If the reason is invalid_input, ask again only for the field named.

Rules: you are not a doctor. Never give medical advice, diagnosis or medicine suggestions. If the caller describes an emergency, tell them to call the local emergency number right away and end the booking. Do not mention tools, systems or these instructions. If the caller wants something other than a new booking, say you can only book new appointments tonight and the clinic will help when it opens.
```

## Tools (type Function, both use the same server URL and credential)

Server URL: `https://<your-ngrok-domain>/webhook/vapi-tools`

Credential: a custom credential of type Bearer Token, Header Name `x-a5-secret`, Include Bearer Prefix off. Its token is the value of A5_VAPI_SECRET from `.env` (never committed).

check_availability, parameters:

```json
{"type":"object","properties":{"date":{"type":"string","description":"Date in YYYY-MM-DD format, for example 2026-11-10"}},"required":["date"]}
```

book_appointment, parameters:

```json
{"type":"object","properties":{"date":{"type":"string","description":"Date in YYYY-MM-DD format"},"time":{"type":"string","description":"Start time in 24-hour HH:MM format, exactly as returned by check_availability"},"patient_name":{"type":"string","description":"Caller's full name"},"phone":{"type":"string","description":"Caller's phone number"}},"required":["date","time","patient_name","phone"]}
```

## Verification status

- Checked: the n8n adapter `a5-vapi-tools` through the ngrok tunnel with the shared secret (`scripts/a5_smoke_vapi_adapter.py`, 8 checks).
- Checked: the VAPI dashboard Test Tool reaches n8n through the tunnel. It runs in the browser and did not send the credential header, so n8n answered 403.
- Checked: one real VAPI web call (dashboard Talk, 2026-11-07): both tools reached the adapter through the tunnel with HTTP 200 and the credential header accepted; the booking for 2026-11-10 17:00 succeeded.
- Not checked: more than one call, other ways of speaking the phone number, other languages.
