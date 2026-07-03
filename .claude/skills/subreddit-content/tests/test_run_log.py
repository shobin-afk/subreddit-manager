"""Tests for run_log — append/parse round-trip of structured events."""
from run_log import append_event, parse_log


def test_round_trip_simple(tmp_path):
    log = tmp_path / "run.log"
    append_event(log, phase="discovery", event="ok", candidates=42)
    events = parse_log(log)
    assert len(events) == 1
    assert events[0]["phase"] == "discovery"
    assert events[0]["event"] == "ok"
    assert events[0]["candidates"] == "42"
    assert "timestamp" in events[0]


def test_quotes_values_with_spaces(tmp_path):
    log = tmp_path / "run.log"
    append_event(log, phase="media", event="error", message="download failed hard")
    events = parse_log(log)
    assert events[0]["message"] == "download failed hard"


def test_appends_multiple_lines(tmp_path):
    log = tmp_path / "run.log"
    append_event(log, event="a")
    append_event(log, event="b")
    assert len(parse_log(log)) == 2
