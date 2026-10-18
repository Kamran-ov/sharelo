# ADR 001 — One origin: Django serves the SPA

Status: accepted (ticket 015)

**Decision.** Django serves the built frontend. whitenoise answers real files (`sw.js`, manifest, icons,
assets) from `FRONTEND_DIST`; a catch-all `SpaIndexView`, appended last and excluding `api`, `admin`
and `static`, answers every other path with `index.html`.

**Why.** Session and CSRF cookies are same-origin, so there is no CORS and no cross-site cookie setting;
one container to run on a laptop and behind a tunnel; the service worker's scope is the whole app.

**Rejected.** An nginx container in front: a second image and config for no behaviour we need yet.
Revisit at the hosting step if a CDN is wanted.

**Consequences.** Navigations are never answered from cache (the shell is not precached); `/api/` is never
cached, so no authenticated response survives logout. Offline shows `offline.html` and nothing else.
