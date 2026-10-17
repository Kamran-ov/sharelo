# Household expenses app — plan

Oct 12, 2026 · Kamran Huseynov

Source of truth for the plan. Tickets in `tickets/` implement it step by step.

## Goal and scope

Replace Splitwise (about €48 a year) with our own web app that costs about €13 a year, mostly the domain.

- **For us first:** shared household expenses, who owes whom, and clear analytics of where money goes.
- **Faster than Splitwise:** adding an expense takes two taps; bank exports come in as a whole month at once.
- **Open source later:** anyone can use it for trips or shared homes; ads are a possible later idea, not a goal.
- **Phase 2, separate:** a pantry and meal-planning module.

## Key decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Build vs fork | Own app, not a Spliit fork | Python comfort, own repo and stars, full control |
| Access | Profiles sign in with Google or email and password; trip guests join by link and pick a name | The app must know you are the same person in every group; Google is one tap; email and password covers people without Google. Password reset comes with the email service at release. Guests need nothing |
| Currency | One currency per group, set at creation | Like Splitwise; debts never mix currencies |
| Foreign expenses | Original amount kept, converted to the group currency at that day's rate | Rates stored once a day against EUR (ECB); any pair is derived through EUR |
| Recurring amounts | Fixed per rule; users edit the rule when a price changes | The app can't know a price changed; variable bills like electricity stay manual |
| Mobile | Web app that installs to the home screen (PWA), no native app | One codebase, zero app-store cost |
| Hosting | Free tier server or free tunnel for testing; buy the domain only once it works | Target about €13 a year in total |

## How it works

(Diagram: three inputs — manual entry, bank import, Splitwise history — feed one core engine; outputs are balances and analytics. Pantry/meals is a later separate module.)

Every input becomes the same kind of expense record, so balances and analytics never care where an expense came from.

## Features

**Groups and people**

- A profile signs in with Google or with email and password, and has one main group (Home), which both partners can share as their main group.
- Any group you create or join with your profile becomes a sub-group linked to your main group automatically. You can unlink one, for example a work trip.
- Linking is per person: if you join a friend's trip, it feeds your Home, and the friend's own main group if they have a profile.
- Trip guests without a profile open the group link and pick a name. Their shares never appear in anyone's Home analytics.
- Balances stay inside each group. Between two linked profiles, a "Move to Home" button moves a leftover trip debt into the main group as one visible entry on each side, for example "Rome trip: €200 moved to Home".

**Adding an expense (two taps)**

- Amount, description, category, date.
- "Who paid" is one tap: Me or the other person.
- "Who it's for" is one tap: 50/50, Only payer (personal), All the other, or Custom % with one slider.
- More people or exact amounts sit under an "Advanced" option.
- Each category remembers its default split, so Groceries is always 50/50 unless changed.
- Personal expenses don't affect balances but still count in that person's analytics.

**Categories (two levels)**

- Main types with sub-categories, copied from Splitwise's structure, for example Food and drink with Groceries, Dining out, Liquor.
- Five years of Splitwise history then maps one to one on import.
- Users can rename or add categories later.

**Recurring expenses**

- A rule holds amount, payer, split, category, and frequency (monthly on day N, or yearly on a date).
- A daily job creates the expense when it's due.
- A recurring page lets you edit the amount, pause, or skip one occurrence.

**Bank import (Revolut, Wise first)**

- Upload the month's CSV; already-imported rows are skipped automatically.
- A review list needs one tap per row: shared, personal, or skip, with the category pre-filled.
- Shop rules remember choices, for example "Esselunga = Groceries, 50/50".
- More banks later, on request.

**Splitwise history import**

- A one-off import of all five years through Splitwise's free API, with exact paid and owed amounts per person.
- Safe to re-run: nothing duplicates.

**Balances and settle up**

- Who owes whom, per group, in the group currency.
- Recording a payment between people brings balances back to zero.
- With three or more people, debts are simplified to the fewest transfers.

**Analytics**

- Spending per person and per category over time, counting each person's own share.
- Home analytics include every linked sub-group, converted to Home's currency at each expense's date.
- A switch shows trips either as one line per trip ("Rome trip: you €920, wife €780") or spread into their categories.
- Drill down from main type to sub-category, and from all trips to one trip.
- The detailed chart design is decided later, before that build step.

## Data model

Expenses are the source of truth: balances are always calculated from them, never stored. All money is stored as whole cents.

| Table | Holds |
| --- | --- |
| Profile | Google identity, name, main group |
| Group | Name, currency, share link token |
| Member | Name, group, optional profile (empty for guests) |
| Group link | Profile, sub-group, main group, active |
| Expense | Description, amount, original amount + currency, rate used, date, category, split type, source, external id, import batch, recurring rule |
| Expense payer | Who paid how much (one or more members) |
| Expense split | Who owes how much |
| Settlement | A payment from one member to another; a "Move to Home" pair is linked to its twin |
| Category | Name, parent category (two levels) |
| Category default | Default split per category, per group |
| Recurring rule | Amount, payer, split, category, frequency, next date, paused |
| Shop rule | Merchant text to category and split |
| Import batch | Source, file or API, rows seen, created, skipped |
| Exchange rate | Date, currency, rate against EUR |

Source is manual, splitwise, revolut, or wise. The pair (source, external id) is unique, which is what stops duplicate imports.

## Build order and stack

We can drop Splitwise after step 3; each step ends with passing tests before the next starts.

1. **Core engine:** profiles, groups and linked sub-groups, two-level categories, expenses, payers, splits and presets, settlements and Move to Home, balances, debt simplification, currency conversion. Tests only, no screens.
2. **Recurring rules:** the rules and the daily job that creates due expenses.
3. **Web app:** Google or email-and-password sign-in, main group, create or join a group by link (guests by name), add an expense in two taps, expense list, balances, settle up, recurring page. Works on phone and installs to the home screen.
4. **Splitwise history import:** five years through the API.
5. **Bank import:** Revolut and Wise CSV, review list, shop rules.
6. **Analytics:** chart design agreed first, then built.
7. **Release:** hosting, domain, email service (Brevo free tier) for password reset and email verification, README, open-source licence, listing on alternative-app directories.
8. **Later:** pantry and meals module.

**Stack:** Django + Django REST Framework (backend), Vite + TypeScript (frontend, installable PWA), PostgreSQL, Docker Compose; pytest and vitest. Built with the spec-driven development light track. Developed in WSL; tested on phone through a Cloudflare tunnel.

**How we build (automated loop on Claude Routines, Max plan):**

- Tickets live in a `tickets/` folder with a status: ready, in-review, blocked, done.
- A builder routine runs hourly: it fixes PRs with requested changes first, otherwise builds the next ready ticket with tests and opens a PR.
- A reviewer routine (Fable 5.1, fresh session, no build context) starts on every PR opened or updated, reviews against the ticket spec, and either merges into `develop` or requests changes.
- A blocked ticket becomes a GitHub issue labeled `needs-operator`; the builder moves on to independent tickets.
- Kamran tests `develop` visually and merges `develop` into `main` when happy.

## Out of scope and open points

Not in the first version: native mobile apps, sending any email before the release step, banks other than Revolut and Wise, ads, the pantry module.

- [ ] App name (needed before buying the domain)
- [ ] Analytics chart design (before step 6)
- [ ] Rare currencies the ECB doesn't publish: a manual rate on the expense
- [ ] Where to host for real (before step 7)
