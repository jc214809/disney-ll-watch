# Disney Lightning Lane Watch

Real-time Individual Lightning Lane availability dashboard for Walt Disney World. Shows live ILL prices, standby wait times, and return windows for today using the ThemeParks Wiki WebSocket API. Future trip dates show schedule data fetched every 5 minutes via GitHub Actions.

**Live site:** https://jc214809.github.io/disney-ll-watch/

---

## How It Works

### Today tab — live via WebSocket
1. On load, seeds today's data immediately from the ThemeParks REST API (no key needed).
2. Connects to a Cloudflare Worker proxy (`wss://disney-ll-ws-proxy.disney-ll-watch.workers.dev`) which forwards the connection to `wss://ws.themeparks.wiki/v1/live` with the `X-API-Key` header. The browser can't send custom headers in a native WebSocket, so the proxy is required.
3. Incoming `livedata` events are filtered to the 5 tracked ILL attractions and the UI updates in real time.
4. A `● Live` / `● Connecting…` / `● Reconnecting…` indicator shows WebSocket state.

### Future date tabs — scheduled REST pulls
- GitHub Actions fetches the ThemeParks schedule API every 5 minutes and writes `data.json` + `state.json` to an orphan `data` branch.
- The browser fetches that `data.json` for future dates.
- Pushover alerts fire when a watched ride changes availability or price.

### Tracked attractions
| Ride | Park |
|---|---|
| TRON Lightcycle / Run | Magic Kingdom |
| Seven Dwarfs Mine Train | Magic Kingdom |
| Guardians of the Galaxy: Cosmic Rewind | EPCOT |
| Star Wars: Rise of the Resistance | Hollywood Studios |
| Avatar Flight of Passage | Animal Kingdom |

---

## Architecture

```
Browser
  └── fetches data.json from GitHub (data branch) — future dates
  └── seeds today via REST  https://api.themeparks.wiki/v1/entity/{id}/live
  └── WebSocket → Cloudflare Worker → wss://ws.themeparks.wiki/v1/live
                                           (X-API-Key header added by worker)

GitHub Actions (every 5 min)
  └── scripts/update.py → data.json + state.json → push to data branch
```

---

## First-Time Setup

### 1. Fork / create the repo
Push all files to a GitHub repo. Enable GitHub Pages from the `main` branch root.

### 2. Add GitHub Actions secrets
In repo Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `PUSHOVER_APP_TOKEN` | Your Pushover app token |
| `PUSHOVER_USER_KEY` | Your Pushover user key |

### 3. Deploy the Cloudflare Worker proxy
The worker lives in `worker/index.js`. It proxies WebSocket connections from the browser to ThemeParks, adding the API key header server-side.

```bash
npm install -g wrangler
wrangler login

cd worker
wrangler deploy
# Cloudflare prints your worker URL, e.g. disney-ll-watch.workers.dev

wrangler secret put THEMEPARKS_API_KEY
# paste your ThemeParks API key (starts with tpw_)
```

Get a free ThemeParks API key at https://api.themeparks.wiki.

### 4. Update the worker URL in index.html
After deploy, confirm line ~351 in `index.html` matches your worker URL:
```js
const WS_URL = 'wss://disney-ll-watch.workers.dev';
```

### 5. Trigger the first data pull
Go to Actions → Update Lightning Lane Data → Run workflow. This populates `data.json` on the `data` branch so future date tabs have data.

---

## Config

Edit `config.json` on `main`:

```json
{
  "trip_start": "2026-08-30",
  "trip_end": "2026-09-08",
  "parks": [ ... ],
  "watched_rides": [ "Avatar Flight of Passage", ... ],
  "notify_on_available": true,
  "notify_on_sold_out": true,
  "notify_on_price_drop": false,
  "price_drop_threshold_dollars": 2
}
```

`watched_rides` filters both the future-date schedule data and the today live view. Alerts fire on state changes — the first run won't spam you for already-available rides.

---

## Secrets summary

| Where | What | How |
|---|---|---|
| Cloudflare Worker secret store | ThemeParks API key | `wrangler secret put THEMEPARKS_API_KEY` |
| GitHub Actions secrets | Pushover tokens | Repo Settings → Secrets |

The ThemeParks API key never appears in the repo or in browser network traffic.

---

## Running locally

```bash
python3 -m http.server 8743 --directory .
# open http://localhost:8743
```

The WebSocket will connect through the deployed Cloudflare Worker as normal. The REST seed calls work without any key.

---

## Updating the worker

```bash
cd worker
wrangler deploy
```

Secrets persist across deploys — no need to re-set `THEMEPARKS_API_KEY` unless the key changes.
