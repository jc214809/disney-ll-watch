import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
DATA_PATH = ROOT / "data.json"
STATE_PATH = ROOT / "state.json"

API_BASE = "https://api.themeparks.wiki/v1/entity/{park_id}/schedule/{year}/{month:02d}"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def ride_display_name(purchase_name):
    prefix = "Lightning Lane for "
    if purchase_name.startswith(prefix):
        return purchase_name[len(prefix):]
    return purchase_name


def is_watched(ride_name, watched):
    if not watched:
        return True
    rn = ride_name.lower()
    return any(w.lower() in rn or rn in w.lower() for w in watched)


def fetch_month(park_id, year, month):
    url = API_BASE.format(park_id=park_id, year=year, month=month)
    resp = requests.get(url, timeout=30, headers={"User-Agent": "disney-ll-watch/1.0"})
    resp.raise_for_status()
    return resp.json(), url


def extract_items(config):
    start = parse_date(config["trip_start"])
    end = parse_date(config["trip_end"])
    watched = config.get("watched_rides", [])
    months = sorted({(start.year, start.month), (end.year, end.month)})

    items = []
    errors = []

    for park in config.get("parks", []):
        park_name = park["name"]
        park_id = park["id"]
        for year, month in months:
            try:
                payload, source_url = fetch_month(park_id, year, month)
            except Exception as exc:
                errors.append({"park": park_name, "month": f"{year}-{month:02d}", "error": str(exc)})
                continue

            for entry in payload.get("schedule", []):
                if entry.get("type") != "OPERATING":
                    continue
                entry_date_raw = entry.get("date")
                if not entry_date_raw:
                    continue
                entry_date = parse_date(entry_date_raw)
                if entry_date < start or entry_date > end:
                    continue

                for purchase in entry.get("purchases", []) or []:
                    if purchase.get("type") != "ATTRACTION":
                        continue
                    raw_name = purchase.get("name", "Unknown Attraction")
                    ride = ride_display_name(raw_name)
                    if not is_watched(ride, watched):
                        continue

                    price = purchase.get("price") or {}
                    items.append({
                        "date": entry_date_raw,
                        "park": park_name,
                        "ride": ride,
                        "purchase_id": purchase.get("id"),
                        "name": raw_name,
                        "available": bool(purchase.get("available")),
                        "price_amount": price.get("amount"),
                        "price_formatted": price.get("formatted"),
                        "currency": price.get("currency", "USD"),
                        "source_url": source_url,
                    })

    items.sort(key=lambda x: (x["date"], x["park"], x["ride"]))
    return items, errors


def item_key(item):
    return f'{item["date"]}|{item["park"]}|{item["ride"]}'


def send_pushover(title, message):
    token = os.environ.get("PUSHOVER_APP_TOKEN")
    user = os.environ.get("PUSHOVER_USER_KEY")
    if not token or not user:
        print("Pushover secrets not set; skipping notification")
        return False

    data = {
        "token": token,
        "user": user,
        "title": title,
        "message": message,
        "priority": 0,
    }
    resp = requests.post(PUSHOVER_URL, data=data, timeout=30)
    resp.raise_for_status()
    return True


def build_alerts(config, items, old_state):
    alerts = []
    notify_on_available = config.get("notify_on_available", True)
    notify_on_sold_out = config.get("notify_on_sold_out", True)
    notify_on_price_drop = config.get("notify_on_price_drop", False)
    drop_threshold = int(round(float(config.get("price_drop_threshold_dollars", 2)) * 100))

    for item in items:
        key = item_key(item)
        old = old_state.get(key)
        now_available = bool(item.get("available"))
        old_available = bool(old.get("available")) if isinstance(old, dict) else None

        if notify_on_available and old is not None and old_available is False and now_available is True:
            alerts.append({
                "title": "Lightning Lane Available",
                "message": f'{item["ride"]}\n{item["park"]} on {item["date"]}\nPrice: {item.get("price_formatted") or "unknown"}',
            })

        if notify_on_sold_out and old is not None and old_available is True and now_available is False:
            alerts.append({
                "title": "Lightning Lane Sold Out",
                "message": f'{item["ride"]}\n{item["park"]} on {item["date"]}',
            })

        if notify_on_price_drop and old is not None:
            old_price = old.get("price_amount")
            new_price = item.get("price_amount")
            if isinstance(old_price, int) and isinstance(new_price, int) and old_price - new_price >= drop_threshold:
                alerts.append({
                    "title": "Lightning Lane Price Drop",
                    "message": f'{item["ride"]}\n{item["park"]} on {item["date"]}\n{old.get("price_formatted")} → {item.get("price_formatted")}',
                })

    return alerts


def main():
    config = load_json(CONFIG_PATH, {})
    if not config:
        print("Missing config.json", file=sys.stderr)
        return 1

    old_state = load_json(STATE_PATH, {})
    items, errors = extract_items(config)
    alerts = build_alerts(config, items, old_state)

    for alert in alerts:
        print(f'Sending alert: {alert["title"]} - {alert["message"]}')
        try:
            send_pushover(alert["title"], alert["message"])
        except Exception as exc:
            errors.append({"pushover": alert, "error": str(exc)})

    new_state = {
        item_key(item): {
            "available": item.get("available"),
            "price_amount": item.get("price_amount"),
            "price_formatted": item.get("price_formatted"),
            "seen_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        for item in items
    }

    write_json(STATE_PATH, new_state)
    write_json(DATA_PATH, {
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "trip_start": config.get("trip_start"),
        "trip_end": config.get("trip_end"),
        "items": items,
        "errors": errors,
    })

    print(f"Updated {len(items)} Lightning Lane Single Pass records; {len(alerts)} alerts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
