import time

import pytest

from scheduler import parse_when


def test_parse_in_hours():
    ts = parse_when(in_="2h")
    assert abs(ts - (time.time() + 7200)) < 5


def test_parse_in_minutes():
    ts = parse_when(in_="30m")
    assert abs(ts - (time.time() + 1800)) < 5


def test_parse_at_full_date():
    ts = parse_when(at="2030-01-02 09:30")
    assert ts > time.time()


def test_parse_at_time_only_is_future():
    ts = parse_when(at="00:00")
    assert ts > time.time()


def test_invalid_raises():
    with pytest.raises(ValueError):
        parse_when(at="not-a-date")
    with pytest.raises(ValueError):
        parse_when(in_="2x")
    with pytest.raises(ValueError):
        parse_when()
