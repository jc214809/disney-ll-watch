import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update  # noqa: E402


def make_item(**overrides):
    item = {
        "date": "2026-10-21",
        "park": "EPCOT",
        "ride": "Guardians of the Galaxy: Cosmic Rewind",
        "available": True,
        "price_amount": 2000,
        "price_formatted": "$20.00",
    }
    item.update(overrides)
    return item


def old_entry(**overrides):
    entry = {"available": True, "price_amount": 2000, "price_formatted": "$20.00"}
    entry.update(overrides)
    return entry


# ---- helpers ---------------------------------------------------------------

def test_ride_display_name_strips_prefix():
    assert update.ride_display_name("Lightning Lane for TRON") == "TRON"
    assert update.ride_display_name("TRON") == "TRON"


def test_is_watched_empty_list_watches_everything():
    assert update.is_watched("Anything", [])


def test_is_watched_matches_substring_case_insensitive():
    assert update.is_watched("Avatar Flight of Passage", ["avatar flight"])
    assert not update.is_watched("Space Mountain", ["Avatar Flight of Passage"])


def test_load_json_missing_file_returns_default(tmp_path):
    assert update.load_json(tmp_path / "nope.json", {"d": 1}) == {"d": 1}


def test_load_json_bad_json_returns_default(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert update.load_json(p, {}) == {}


# ---- build_alerts ----------------------------------------------------------

def test_no_alerts_on_first_run():
    item = make_item()
    assert update.build_alerts({}, [item], {}) == []


def test_alert_when_becomes_available():
    item = make_item(available=True)
    state = {update.item_key(item): old_entry(available=False)}
    alerts = update.build_alerts({}, [item], state)
    assert [a["title"] for a in alerts] == ["Lightning Lane Available"]


def test_alert_when_sold_out():
    item = make_item(available=False)
    state = {update.item_key(item): old_entry(available=True)}
    alerts = update.build_alerts({}, [item], state)
    assert [a["title"] for a in alerts] == ["Lightning Lane Sold Out"]


def test_no_alert_when_unchanged():
    item = make_item()
    state = {update.item_key(item): old_entry()}
    assert update.build_alerts({}, [item], state) == []


def test_alert_flags_can_be_disabled():
    config = {"notify_on_available": False, "notify_on_sold_out": False}
    up = make_item(available=True)
    down = make_item(ride="Other", available=False)
    state = {
        update.item_key(up): old_entry(available=False),
        update.item_key(down): old_entry(available=True),
    }
    assert update.build_alerts(config, [up, down], state) == []


def test_price_drop_alert_respects_threshold():
    config = {"notify_on_price_drop": True, "price_drop_threshold_dollars": 2}
    item = make_item(price_amount=1700, price_formatted="$17.00")
    state = {update.item_key(item): old_entry(price_amount=2000)}
    alerts = update.build_alerts(config, [item], state)
    assert [a["title"] for a in alerts] == ["Lightning Lane Price Drop"]

    small = make_item(price_amount=1900, price_formatted="$19.00")
    state = {update.item_key(small): old_entry(price_amount=2000)}
    assert update.build_alerts(config, [small], state) == []


def test_price_drop_ignores_missing_prices():
    config = {"notify_on_price_drop": True}
    item = make_item(price_amount=None)
    state = {update.item_key(item): old_entry(price_amount=2000)}
    assert update.build_alerts(config, [item], state) == []
    state = {update.item_key(item): old_entry(price_amount=None)}
    assert update.build_alerts(config, [make_item()], state) == []


def test_malformed_old_state_entry_does_not_crash():
    item = make_item()
    state = {update.item_key(item): "garbage"}
    # old is not None but not a dict: availability alerts must not fire
    assert update.build_alerts({"notify_on_price_drop": False}, [item], state) == []


# ---- extract_items ---------------------------------------------------------

CONFIG = {
    "trip_start": "2026-10-21",
    "trip_end": "2026-10-25",
    "parks": [{"name": "EPCOT", "id": "park-1"}],
    "watched_rides": ["Cosmic Rewind"],
}


def schedule(*entries):
    return {"schedule": list(entries)}


def operating(date, purchases):
    return {"type": "OPERATING", "date": date, "purchases": purchases}


def purchase(name="Lightning Lane for Guardians of the Galaxy: Cosmic Rewind", **kw):
    p = {"type": "ATTRACTION", "id": "p1", "name": name, "available": True,
         "price": {"amount": 2000, "formatted": "$20.00", "currency": "USD"}}
    p.update(kw)
    return p


def test_extract_items_happy_path(monkeypatch):
    payload = schedule(operating("2026-10-22", [purchase()]))
    monkeypatch.setattr(update, "fetch_month", lambda *a: (payload, "http://x"))
    items, errors = update.extract_items(CONFIG)
    assert errors == []
    assert len(items) == 1
    assert items[0]["ride"] == "Guardians of the Galaxy: Cosmic Rewind"
    assert items[0]["price_amount"] == 2000


def test_extract_items_filters_date_type_and_unwatched(monkeypatch):
    payload = schedule(
        operating("2026-10-20", [purchase()]),                        # before trip
        operating("2026-10-26", [purchase()]),                        # after trip
        {"type": "CLOSED", "date": "2026-10-22", "purchases": [purchase()]},
        operating("2026-10-22", [purchase(name="Lightning Lane for Space Mountain")]),
        operating("2026-10-22", [purchase(type="PACKAGE")]),
    )
    monkeypatch.setattr(update, "fetch_month", lambda *a: (payload, "http://x"))
    items, errors = update.extract_items(CONFIG)
    assert items == [] and errors == []


def test_extract_items_tolerates_missing_fields(monkeypatch):
    payload = schedule(
        {"type": "OPERATING"},                                        # no date
        operating("2026-10-22", None),                                # purchases null
        operating("2026-10-22", [purchase(price=None, available=None)]),
    )
    monkeypatch.setattr(update, "fetch_month", lambda *a: (payload, "http://x"))
    items, errors = update.extract_items(CONFIG)
    assert len(items) == 1
    assert items[0]["available"] is False
    assert items[0]["price_amount"] is None


def test_extract_items_records_fetch_errors(monkeypatch):
    def boom(*a):
        raise RuntimeError("503")
    monkeypatch.setattr(update, "fetch_month", boom)
    items, errors = update.extract_items(CONFIG)
    assert items == []
    assert errors == [{"park": "EPCOT", "month": "2026-10", "error": "503"}]


def test_extract_items_payload_without_schedule(monkeypatch):
    monkeypatch.setattr(update, "fetch_month", lambda *a: ({}, "http://x"))
    assert update.extract_items(CONFIG) == ([], [])


# ---- send_pushover ---------------------------------------------------------

def test_send_pushover_skips_without_secrets(monkeypatch):
    monkeypatch.delenv("PUSHOVER_APP_TOKEN", raising=False)
    monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
    monkeypatch.setattr(update.requests, "post",
                        lambda *a, **k: pytest.fail("should not post"))
    assert update.send_pushover("t", "m") is False


def test_send_pushover_posts_when_configured(monkeypatch):
    monkeypatch.setenv("PUSHOVER_APP_TOKEN", "tok")
    monkeypatch.setenv("PUSHOVER_USER_KEY", "usr")
    calls = []

    class Resp:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(update.requests, "post",
                        lambda url, **k: calls.append((url, k)) or Resp())
    assert update.send_pushover("t", "m") is True
    assert calls[0][1]["data"]["token"] == "tok"


# ---- main ------------------------------------------------------------------

def test_main_writes_data_and_state_and_survives_pushover_failure(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(CONFIG))
    monkeypatch.setattr(update, "CONFIG_PATH", cfg)
    monkeypatch.setattr(update, "DATA_PATH", tmp_path / "data.json")
    monkeypatch.setattr(update, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(update, "DOWN_STATE_PATH", tmp_path / "down_state.json")
    monkeypatch.setattr(update, "fetch_live", lambda park_id: {"liveData": []})

    item_payload = schedule(operating("2026-10-22", [purchase(available=True)]))
    monkeypatch.setattr(update, "fetch_month", lambda *a: (item_payload, "http://x"))

    # Prior state says sold out -> triggers an "Available" alert; Pushover fails.
    key = "2026-10-22|EPCOT|Guardians of the Galaxy: Cosmic Rewind"
    (tmp_path / "state.json").write_text(json.dumps({key: old_entry(available=False)}))

    def fail(*a, **k):
        raise RuntimeError("pushover down")
    monkeypatch.setattr(update, "send_pushover", fail)

    assert update.main() == 0
    data = json.loads((tmp_path / "data.json").read_text())
    state = json.loads((tmp_path / "state.json").read_text())
    assert len(data["items"]) == 1
    assert data["errors"][0]["error"] == "pushover down"
    assert state[key]["available"] is True


# ---- down rides ------------------------------------------------------------

def live_payload(*rides):
    return {"liveData": [
        {"id": i, "name": n, "entityType": t, "status": st} for i, n, t, st in rides
    ]}


def test_fetch_down_rides_filters_to_down_attractions(monkeypatch):
    monkeypatch.setattr(update, "fetch_live", lambda pid: live_payload(
        ("a", "Space Mountain", "ATTRACTION", "DOWN"),
        ("b", "Dumbo", "ATTRACTION", "OPERATING"),
        ("c", "Some Show", "SHOW", "DOWN"),
    ))
    down, fetched, errors = update.fetch_down_rides({"parks": [{"name": "MK", "id": "x"}]})
    assert down == {"a": {"name": "Space Mountain", "park": "MK"}}
    assert fetched == {"MK"} and errors == []


def test_fetch_down_rides_records_errors(monkeypatch):
    def boom(pid):
        raise RuntimeError("nope")
    monkeypatch.setattr(update, "fetch_live", boom)
    down, fetched, errors = update.fetch_down_rides({"parks": [{"name": "MK", "id": "x"}]})
    assert down == {} and fetched == set() and errors[0]["error"] == "nope"


def test_down_alerts_first_run_sends_nothing():
    down = {"a": {"name": "Space Mountain", "park": "MK"}}
    alerts, state = update.build_down_alerts({}, down, {"MK"}, None)
    assert alerts == [] and state == down


def test_down_alerts_only_for_newly_down():
    old = {"a": {"name": "Space Mountain", "park": "MK"}}
    down = {**old, "b": {"name": "Dumbo", "park": "MK"}}
    alerts, state = update.build_down_alerts({}, down, {"MK"}, old)
    assert [a["message"] for a in alerts] == ["Dumbo\nMK"]
    assert set(state) == {"a", "b"}


def test_down_alerts_ride_back_up_then_down_again_realerts():
    old = {}
    down = {"a": {"name": "Space Mountain", "park": "MK"}}
    alerts, _ = update.build_down_alerts({}, down, {"MK"}, old)
    assert len(alerts) == 1


def test_down_alerts_failed_park_keeps_previous_state():
    old = {"a": {"name": "Space Mountain", "park": "MK"}}
    alerts, state = update.build_down_alerts({}, {}, set(), old)
    assert alerts == [] and "a" in state


def test_down_alerts_respects_config_toggle():
    down = {"a": {"name": "Space Mountain", "park": "MK"}}
    alerts, state = update.build_down_alerts({"notify_on_ride_down": False}, down, {"MK"}, {})
    assert alerts == [] and state == down


def test_in_trip_window_is_inclusive():
    cfg = {"trip_start": "2026-10-21", "trip_end": "2026-10-25"}
    d = update.date
    assert update.in_trip_window(cfg, d(2026, 10, 21))
    assert update.in_trip_window(cfg, d(2026, 10, 25))
    assert not update.in_trip_window(cfg, d(2026, 10, 20))
    assert not update.in_trip_window(cfg, d(2026, 10, 26))


def test_main_skips_down_check_outside_trip_and_resets_baseline(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({**CONFIG, "trip_start": "2020-01-01", "trip_end": "2020-01-02"}))
    monkeypatch.setattr(update, "CONFIG_PATH", cfg)
    monkeypatch.setattr(update, "DATA_PATH", tmp_path / "data.json")
    monkeypatch.setattr(update, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(update, "DOWN_STATE_PATH", tmp_path / "down_state.json")
    monkeypatch.setattr(update, "fetch_month", lambda *a: ({}, "http://x"))
    monkeypatch.setattr(update, "fetch_live", lambda pid: {"liveData": [
        {"id": "a", "name": "Space Mountain", "entityType": "ATTRACTION", "status": "DOWN"}]})
    monkeypatch.setattr(update, "send_pushover", lambda *a: pytest.fail("no alert outside trip"))
    (tmp_path / "down_state.json").write_text(json.dumps({}))
    assert update.main() == 0
    assert update.load_json(tmp_path / "down_state.json", "missing") is None


def test_main_fails_without_config(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "CONFIG_PATH", tmp_path / "missing.json")
    assert update.main() == 1
