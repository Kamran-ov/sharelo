# Review log

One entry per review verdict, newest last. The Reviewer reads this first on every run.


- Ticket 000 — plan review, head 13bff39
- Verdict: REVISE (two items: `DATABASE_URL` must survive the setup script being executed rather than sourced; key-test red proof must reach the vendor assertion, not the parser refusal)
- Worth remembering: a setup script's `export` never reaches the session shell, so anything the cloud session needs must have a Makefile default or live in a file, not only in an exported variable. Also: this routine runs under the PR author's account, so GitHub refuses request-changes/approve; verdicts arrive as COMMENT reviews whose body starts with REVISE / ACCEPT.

- Ticket 000 — plan review, head 54bd81a
- Verdict: ACCEPT PLAN (previous REVISE items closed: setup script run not sourced with a Makefile `DATABASE_URL` default; key-test red proof reaches the vendor assertion and a refused connection; settings.json wording matches develop)
- Worth remembering: a key-test red proof must fail on the property's own assertion, not on an earlier guard (parser refusal, collection error); when a guard sits in front of the property, temporarily lift the guard for the proof and restore it, and say so in the REPORT.

- Ticket 000 — result review, head 0149c58
- Verdict: ACCEPT — merge (all plan-named tests listed with run summaries; key-test proof reaches the vendor assertion and a refused connection, restored to green; CI green on head; Docker paths unverified in the cloud and accepted as documentation-only for this ticket)
- Worth remembering: a REPORT passes when each claim carries its own evidence (command, the failing line with file:line, the restore check, the green summary) rather than a narrative; "not verified" is acceptable only when the ticket's Acceptance asks for documentation, not execution, of that path.
