# Tickets

One file per ticket: `tickets/NNN-short-name.md`. The builder routine picks the
lowest-numbered ticket with `status: ready` whose `depends_on` tickets are all
`done`. Never edit a ticket's body after it is `ready`; add a new ticket instead.

## Statuses

| Status      | Meaning                                                              | Who sets it        |
|-------------|----------------------------------------------------------------------|--------------------|
| `draft`     | Being written; the builder ignores it                                | Kamran             |
| `ready`     | Can be built                                                         | Kamran             |
| `in-review` | A PR is open for it (draft = plan under review, ready = build under review) | Builder     |
| `blocked`   | Builder needs an answer; a GitHub issue `needs-kamran` names the question | Builder       |
| `done`      | PR merged into `develop`                                             | Builder, at merge  |

## Format

```markdown
---
id: 003
title: Short title
status: ready
risk: normal          # normal | risky  (risky = money, identity, data guarantee, migration)
depends_on: [001, 002]
pr:                   # filled by the builder
---

## Goal
What exists when this ticket is done, in plain language. 2–5 lines.

## Scope
- Bullet list of what to build.

## Out of scope
- What a reader might expect here and must NOT be built in this ticket.

## Acceptance
- Checkable statements. Each one maps to at least one test. Tests are named by the builder.

## Notes
Anything the builder must know: decisions already made, links to plan sections, gotchas.
```

Every ticket starts with a PLAN at `docs/specs/<id>.md` (current state, proposal, tests
incl. the key test, docs, out of scope, open questions), per the spec-driven-development
skill. A `risk: risky` ticket's plan also has edge cases and production checks. The
reviewer reviews the plan before any code is written.
