---
id: 020
title: Bank CSV import — Revolut and Wise parsers, dedupe, import batches
status: in-review
risk: risky
depends_on: [017]
pr:
---

## Goal
A month's CSV export from Revolut or Wise turns into a list of candidate transactions, with
rows already imported recognised and skipped. Nothing becomes an expense yet; the review list
(021) decides.

## Scope
- `imports/banks/` with one parser per bank and a common output type
  `BankRow(date, amount_cents, currency, description, merchant, external_id, raw)`.
  - Revolut (personal account CSV): columns read by header name, not position
    (`Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State,
    Balance`). Only `State = COMPLETED`, only money out; fee added to the amount.
  - Wise (statement CSV): columns by header name (`TransferWise ID`, `Date`, `Amount`,
    `Currency`, `Description`, `Merchant`, …). Only money out.
  - Amounts parsed as text to integer cents; never float.
  - `external_id`: Wise → the TransferWise ID; Revolut has no id → stable hash of
    (completed date, amount, currency, description, running balance).
  - Unknown header set → `LedgerError("unknown_bank_format")` naming the missing columns.
- `PendingBankRow` model: group, uploader member, source (`revolut`/`wise`), import batch,
  the BankRow fields, `status` (pending/shared/personal/skipped), unique (source, external_id,
  group).
- Service `stage_bank_file(group, member, file)` → detects the bank by header, parses, stores
  new rows as pending, counts duplicates as skipped, returns the batch.
- API: `POST groups/{id}/bank-imports/` (multipart), `GET groups/{id}/bank-imports/{batch}/`.

## Out of scope
- Review UI and shop rules (021), other banks, PDF statements.

## Acceptance
- Hand-written fixtures for both banks (anonymised, including a reversed/declined Revolut row, a
  fee, a top-up, a foreign-currency row, a header in a different column order).
- Uploading the same file twice: second batch has created 0, skipped N (KEY test: removing the
  unique key would double the rows).
- Two overlapping monthly files: overlap skipped, new rows created.
- Unknown CSV → 400 `unknown_bank_format` with the missing column names.
- No `float(` in `imports/banks` (grep test).

## Notes
- Kamran will check one real export of each bank after merge; header names above come from the
  banks' current exports and may need a follow-up if they differ. The REPORT must say so.
