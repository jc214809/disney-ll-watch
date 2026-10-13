# disney-ll-watch

Static dashboard for Walt Disney World Individual Lightning Lane (ILL) availability, plus a scheduled updater that sends Pushover alerts. Hosted on GitHub Pages (`main` branch root).

## Commands
- Serve locally: `python3 -m http.server 8743 --directory .` → http://localhost:8743 (or VS Code "Serve + Open in Chrome")
- Tests: `pip install -r requirements-dev.txt && python3 -m pytest -q tests`
- Run updater locally: `python3 scripts/update.py` (writes `data.json` + `state.json` in repo root — do not commit them to main, and do not gitignore them: CI `git add`s them for the data branch; Pushover skipped without `PUSHOVER_APP_TOKEN`/`PUSHOVER_USER_KEY`)
- Deploy worker (WebSocket mode only): `cd worker && wrangler deploy`

## File map
- `index.html` — whole frontend (inline JS/CSS). Today tab = live; other tabs = `data.json` from the `data` branch.
- `config.json` — trip dates, parks, watched rides, alert toggles. **Update trip dates for each trip** or the updater has nothing to fetch.
- `scripts/update.py` — pulls ThemeParks schedule API, diffs against `state.json`, sends Pushover alerts, writes `data.json`.
- `.github/workflows/update.yml` — `workflow_dispatch` only; triggered by external cron via the GitHub API. Pushes `data.json`/`state.json` to the orphan `data` branch (force push).
- `worker/` — Cloudflare Worker WebSocket proxy (adds `X-API-Key`). Only used when `USE_WEBSOCKET = true`.
- `tests/test_update.py` — pytest suite for `scripts/update.py` (network and Pushover mocked).

## Key patterns / gotchas
- `USE_WEBSOCKET` (index.html) defaults to `false`: Today refreshes by polling the keyless REST endpoint every 60s (5 requests/poll/tab, paused when tab hidden). No ThemeParks API key is available, so don't enable WebSocket mode unless one is set on the Worker.
- Status line `#ws-status` shows polling freshness/failures; `seedToday()` returns the failure count.
- Alerts fire only on state changes versus `state.json`; first run (no state) sends nothing.
- `data` branch is force-pushed by CI — never commit to it by hand.
- Future tabs are capped at 6 days ahead.
- No JS tests; frontend changes must be checked in a browser.
- Known nit: `scripts/update.py` uses deprecated `datetime.utcnow()`.
