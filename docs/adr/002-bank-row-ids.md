# ADR 002 — Bank row ids are frozen

Status: accepted (ticket 020)

**Decision.** A staged bank row's `external_id` is the only thing that recognises a row on a later
upload (`PendingBankRow` unique `(source, external_id, group)`, inserted with `ON CONFLICT DO
NOTHING`). The recipes:

- **Wise:** `"wise:" + TransferWise ID` (stripped).
- **Revolut** (no id in the export): `"rv:" + sha256` of these five values joined by `\x1f`, each
  in canonical parsed form, never raw text:
  1. `Completed Date` as `YYYY-MM-DDTHH:MM:SS` (missing seconds → `:00`; no time part →
     `T00:00:00`);
  2. `Amount` as signed integer cents (`-12.5` ≡ `-12.50`);
  3. `Currency` stripped and upper-cased;
  4. `Description` stripped, internal whitespace collapsed to one space (case kept);
  5. `Balance` as signed integer cents (`100` ≡ `100.00`).
  `Fee` is not part of the id.

Code: `importers/banks/revolut.py:row_id`, `importers/banks/wise.py:row_id`.

**Why.** Monthly exports overlap at the edges, and the same row must be recognised however the
bank formats it that day. The running balance tells apart two identical purchases in the same
second.

**Consequences.** **Changing either recipe re-stages every row ever imported** from that bank
(old ids no longer match, nothing is ever deleted). A change needs its own ticket with a migration
plan, never a quiet edit. Because a wrong first upload cannot be fixed by re-uploading (the
re-upload is skipped by id), every new export format is checked with
`stage_bank_file --dry-run` before anything is staged.
