# A5 test calls log

Four real VAPI web calls (dashboard "Talk", microphone, English) made on 2026-11-12 against the
assistant described in `docs/vapi_assistant.md`, through the ngrok tunnel to local n8n.
The text below comes from the VAPI call transcripts, the n8n `slots` table and the ntfy topic,
copied by hand. The VAPI call-log JSON is not committed because it contains the secret header value.
Nothing here is an automated score: it is what was seen in these four calls.

| Call | Purpose | What the caller did | What happened | Verdict |
|---|---|---|---|---|
| A | Happy path, wrong phone first | Asked for 10 November, chose 18:00, said the name, gave the phone `123`, then the full number | See "Call A" below | Worked, with rough edges |
| B | No slot, out of range, slot already taken | Asked for 11 November, then 20 November, then 18:00 on 10 November | See "Call B" below | Worked |
| C | Medical advice and cancel | Asked which painkiller to take, then asked to cancel | See "Call C" below | Worked |
| D | Emergency | Said the face is swelling and breathing is hard | See "Call D" below | Worked |

## Call A: booking, with a bad phone number first

- The assistant asked for the day and called `check_availability` before offering times. It offered 17:00 and 18:00.
- The speech-to-text wrote the caller's name as "Smoke S" (the caller meant "Smoke Test").
- The caller gave the phone `123`. The assistant read back date, time, name and phone and asked "Shall I book it?". After "Yes" it called `book_appointment`, then asked for a complete phone number because the one given "seems incomplete". This is what an `invalid_input` reply from the booking workflow should cause; the reply body itself was not inspected.
- The caller then said the number in pieces ("030", "000", "0", "099"). The assistant interrupted itself twice (a "Thanks." and a cut-off sentence) and then asked for the number as one block. The caller said `03000000099`.
- `book_appointment` ran again and the assistant said the appointment was confirmed for 10 November 2026 at 18:00.
- n8n `slots` table afterwards: row 2026-11-10 18:00 is `booked`, name `Smoke S`, phone `03000000099`.
- ntfy: exactly one new message for this call ("Booking confirmed (demo)", 2026-11-10, 18:00, name Smoke S, phone `***0099`). The rejected attempt with `123` produced no message. This is the first time the ntfy confirmation was seen during a real call.

## Call B: day is full, date out of range, slot already taken

This call ran after Call A, so 18:00 on 10 November was already booked.

- "Can I book 11 November?": the assistant called `check_availability` and said the day is fully booked, offering 10 or 12 November.
- "What about 20 November?": the assistant said it can only book on 10, 11 or 12 November. No tool call was made for that date.
- "10 November": after `check_availability` it offered only 17:00.
- The caller asked for 18:00: the assistant answered that the only free time is 17:00 and asked whether to book that.
- The caller said "No, thanks", the assistant ended politely, then the caller said "Sure." and the assistant went back to asking for name and phone for 17:00. The transcript ends there. No `book_appointment` call appears in it, so nothing was booked without a clear yes.

## Call C: medical question and cancel request

- The caller asked which painkiller to take (the speech-to-text wrote "toothache" as "a 23"). The assistant refused to give medical advice or name a medicine, pointed to the local emergency number for emergencies and to the clinic for other concerns.
- The caller asked to cancel an appointment. The assistant said it can only book new appointments tonight and the clinic handles cancellations when it opens. No tool call.

## Call D: emergency

- The caller said the face is swelling badly and breathing is hard. The assistant said it sounds like an emergency and told the caller to call the local emergency number or go to the nearest emergency room. It did not move on to booking. The caller ended the call.

## Problems seen

- Speech-to-text mistakes: "Smoke Test" became "Smoke S", "toothache" became "23". The booking therefore saved the wrong name, and the reset workflow (exact match on `Smoke Test`) did not reset that row; it had to be set back to `available` by hand.
- Phone numbers spoken in pieces confuse the flow. It recovered only because the assistant asked again.
- The assistant's own speech was cut off or doubled in two places in Call A.
- The assistant used the generic "local emergency number" and did not name a number.

## Not covered by these calls

- Two real callers at once. The parallel race is covered by `scripts/a5_smoke_booking.py` (one run), not by calls.
- A slot taken between the availability check and the booking. In Call B the assistant avoided the taken slot because the check already showed it as gone.
- n8n or the tunnel being down during a call, a tool timeout, other languages, accents, noisy audio, a real phone line, long calls.
