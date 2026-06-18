import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
DATA_PATH = ROOT / "data.json"
STATE_PATH = ROOT / "state.json"

API = "https://api.themeparks.wiki/v1/entity/{park_id}/schedule/{year}/{month:02d}"


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def daterange_months(start_s, end_s):
    start = date.fromisoformat(start_s)
    end = date.fromisoformat(end_s)
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return months


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "disney-ll-watch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_pushover(title, message):
    token = os.environ.get("PUSHOVER_APP_TOKEN")
    user = os.environ.get("PUSHOVER_USER_KEY")
    if not token or not user:
        print("Pushover secrets not set; skipping notification")
        return

    data = urllib.parse.urlencode({
        "token": token,
        "user": user,
        "title": title,
        "message": message,
        "priority": 0,
    }).encode("utf-8")
    req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("Pushover:", resp.status, resp.read().decode("utf-8"))


def main():
    config = load_json(CONFIG_PATH, {})
    previous = load_json(STATE_PATH, {})
    watched = set(config.get("watched_rides", []))
    trip_start = config["trip_start"]
    trip_end = config["trip_end"]

    items = []
    errors = []

    for park_name, park_id in config["parks"].items():
        for year, month in daterange_months(trip_start, trip_end):
            url = API.format(park_id=park_id, year=year, month=month)
            try:
                payload = fetch_json(url)
            except Exception as e:
                errors.append(f"{park_name}: {e}")
                continue

            for day in payload.get("schedule", []):
                d = day.get("date")
                if day.get("type") != "OPERATING" or not d or d < trip_start or d > trip_end:
                    continue
                for purchase in day.get("purchases", []) or []:
                    if purchase.get("type") != "ATTRACTION":
                        continue
                    ride = purchase.get("name", "Unknown")
                    if watched and ride not in watched:
                        continue
                    price = purchase.get("price") or {}
                    item = {
                        "date": d,
                        "park": park_name,
                        "ride": ride,
                        "purchase_id": purchase.get("id"),
                        "available": bool(purchase.get("available")),
                        "price_amount": price.get("amount"),
                        "price_formatted": price.get("formatted"),
                        "source_url": url,
                    }
                    items.append(item)

    items.sort(key=lambda x: (x["date"], x["park"], x["ride"]))

    # Alerts: unavailable/unknown -> available, and optional price drops.
    current_state = {}
    for item in items:
        key = f'{item["date"]}|{item["park"]}|{item["ride"]}'
        current_state[key] = {
            "available": item["available"],
            "price_amount": item["price_amount"],
            "price_formatted": item["price_formatted"],
        }
        old = previous.get(key)
        if config.get("notify_on_available_flip", True) and item["available"] and (not old or old.get("available") is False):
            send_pushover(
                "Lightning Lane Available",
                f'{item["ride"]}\n{item["park"]} • {item["date"]}\nPrice: {item["price_formatted"] or "N/A"}'
            )
        if config.get("notify_on_price_drop", False) and old:
            old_price = old.get("price_amount")
            new_price = item.get("price_amount")
            drop = config.get("price_drop_amount_cents", 100)
            if isinstance(old_price, int) and isinstance(new_price, int) and new_price <= old_price - drop:
                send_pushover(
                    "Lightning Lane Price Drop",
                    f'{item["ride"]}\n{item["park"]} • {item["date"]}\n{old.get("price_formatted")} → {item["price_formatted"]}'
                )

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "trip_start": trip_start,
        "trip_end": trip_end,
        "errors": errors,
        "items": items,
    }
    DATA_PATH.write_text(json.dumps(out, indent=2) + "\n")
    STATE_PATH.write_text(json.dumps(current_state, indent=2) + "\n")
    print(f"Wrote {len(items)} items")
    if errors:
        print("Errors:", errors, file=sys.stderr)


if __name__ == "__main__":
    main()
