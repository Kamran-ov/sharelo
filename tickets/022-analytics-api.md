---
id: 022
title: Analytics API (data only, charts later)
status: ready
risk: normal
depends_on: [017]
pr:
---

## Goal
The numbers behind the future dashboard are available over the API for a group and for Home,
so the chart step (design first) only has to draw them.

## Scope
- `GET groups/{id}/analytics/?from&to&by=member|category|month|member_category&level=1|2`
  → calls `services/analytics.py` (005).
- `GET home/analytics/?from&to&by=...&trips=lines|spread` → calls `services/home.py` (008) for the
  caller's main group; 404 when the caller has no main group. `GET home/analytics/trip/{group_id}/`
  → `home_trip_breakdown`.
- Response shape: `{currency, from, to, rows: [{key, label, cents}]}`; nested for
  member_category. Labels resolved server-side (member names, category names, trip names).
- Defaults: current calendar month; max range 5 years.
- Guests: allowed on group analytics, never on Home analytics.
- OpenAPI schema regenerated.

## Out of scope
- Any chart or page (design is agreed first, per the plan).

## Acceptance
- Each endpoint returns the same numbers as the service on a shared fixture.
- Home analytics for a guest session → 401; outsider on group analytics → 404.
- Query count per request bounded (asserted).
- KEY test: `trips=lines` vs `spread` totals are equal and differ in rows.
