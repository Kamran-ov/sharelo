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

- Ticket 001 — plan review, head 2a9eeed
- Verdict: REVISE (two items: KEY atomicity test needs `transaction=True, serialized_rollback=True` so the red proof fails on the row-count assertion rather than on an aborted transaction; `IntegrityError` → `duplicate_external_id` translation must match the constraint name, not catch every `IntegrityError`). Decided: category depth guard in `save()`/`clean()` is a structural invariant, accepted as the one exception to rule 8; `IntegerField` cents, `currency_mismatch` in the service, unique `(source, external_id)` on `Settlement`, and the `RecurringRule` stub are all accepted.
- Worth remembering: a test that must observe rows left behind by a failed write cannot run inside the default test transaction (Postgres aborts it on the first error); mark it `transaction=True`, and add `serialized_rollback=True` or the teardown flush wipes data-migration rows for every later test.

- Ticket 001 — plan review, head 99ae72f
- Verdict: ACCEPT PLAN (previous REVISE items closed: KEY atomicity test and the update test run `transaction=True, serialized_rollback=True` with the reasons stated and the proof strips every atomic wrapper; `duplicate_external_id` is raised only for constraint `uniq_expense_source_external_id` via `diag.constraint_name`, the KEY test asserts the raw `IntegrityError`; depth walk bounded, `nulls_distinct=False` on Category, second delete keeps `deleted_at`)
- Worth remembering: any test that provokes a DB `IntegrityError` and then keeps querying under the default `django_db` mark must wrap each failing write in its own `transaction.atomic()` savepoint, or the next statement fails with `InternalError: current transaction is aborted` and the test goes red on an error rather than the property.

- Ticket 001 — result review, head 471f5d1
- Verdict: ACCEPT — merge (all fifteen plan-named tests listed and green, `36 passed`; KEY proof strips both `atomic()` wrappers and fails on the `== 0` row-count line at `test_ledger_expenses.py:132`, restored to green with clean status; second money-guard proof present; production-check numbers all match the plan; CI green on head; Docker path unverified in the cloud and accepted as for 000)
- Worth remembering: a one-line "stricter-simpler" replacement of a planned guard (here: parent-must-be-a-root instead of a bounded walk) is acceptable in a REPORT when it is called out and every case the plan's test names still holds; a tree-depth guard in `save()` only ever sees the row being saved, so re-parenting a node that already has children is a gap for whichever ticket adds category editing.

- Ticket 002 — plan review, head 4e0be97
- Verdict: ACCEPT PLAN (all Scope and Acceptance lines mapped to named tests with passing twins; KEY test `test_every_split_sums_to_total` fails on its own sum assertion when the leftover loop is removed; decided: percentages are integer basis points summing to exactly 10000, no parent-category fallback in `default_split_for`, `full_for_other` infers the other member only with two members)
- Worth remembering: when a money input arrives as "percent with 2 decimals", store and compute it as integer basis points (5000 = 50.00%) and convert at the API boundary once; a tolerance like ±0.005 in a ticket is a sign the input was imagined as decimal and should be re-read as an exact integer equality.

- Ticket 003 — plan review, head ddf3688
- Verdict: REVISE (two items: KEY `test_nets_sum_to_zero` red proof must name a mutation that keeps the sum at 0 but breaks the hand-computed numbers, so the red falls on the test's assertion and not on the service's `balance_drift` guard; the `balance_drift` refusal in both `simplify_debts` and `net_balances` needs a failing test each, paired with the existing passing cases). Decided: all members listed with 0, overpaying settlements allowed, drift raised not returned — all accepted as assumed.
- Worth remembering: when a service guards an invariant by raising (here: nets must sum to 0), a test named for that invariant can never see it violated — only the exception — so its KEY red proof must break a *different* observable (the numbers) while keeping the guard satisfied, and the guard itself needs its own refusal test that bypasses the service to provoke it.

- Ticket 003 — plan review, head 5423bfe
- Verdict: ACCEPT PLAN (previous REVISE items closed: KEY `test_nets_match_hand_computed_values` red proof reverses the settlement on both sides so the sum stays 0 and the dict equality is the red line; `balance_drift` refused in a pure `simplify_debts` case and a DB-bypass `ExpenseSplit.update` case, each with a passing twin; explicit `if`/`raise` guard; grep test also fails on `round(` and ` / `)
- Worth remembering: a source-grep money-trap test (` / `, `round(`) matches prose in docstrings and comments as readily as code, so the module's docstring must be written around it; the fix is the wording, never an exemption in the test.

- Ticket 003 — result review, head d1438a3
- Verdict: ACCEPT — merge (all sixteen plan-named tests listed and green, `68 passed`; KEY proof reverses the settlement on both sides and fails on the dict equality at `test_ledger_balances.py:73` with `test_nets_sum_to_zero` green in the same run, restored to clean status; DB-bypass drift asserts `code == "balance_drift"`; `test_deleted_expense_excluded` folded into the edit-and-delete test, called out, property still guarded; CI green on head)
- Worth remembering: a red proof's numbers can be audited without running anything — the difference between the expected dict and the failing dict must be exactly what the named mutation produces (here ±2×settlement on the two parties and 0 elsewhere); a REPORT whose numbers do not match its stated mutation is describing a run it did not do.
