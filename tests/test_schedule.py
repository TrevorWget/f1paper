from datetime import datetime, timedelta, timezone

from f1paper.schedule import (
    Roster,
    build_weekend_from_race_dict,
    is_active,
    match_roster_in_text,
)

SAMPLE_RACE = {
    "season": "2026",
    "round": "5",
    "raceName": "Miami Grand Prix",
    "Circuit": {
        "circuitName": "Miami International Autodrome",
        "Location": {"country": "USA"},
    },
    "date": "2026-05-03",
    "time": "20:00:00Z",
    "FirstPractice": {"date": "2026-05-01", "time": "16:30:00Z"},
    "SecondPractice": {"date": "2026-05-01", "time": "20:00:00Z"},
    "Qualifying": {"date": "2026-05-02", "time": "20:00:00Z"},
}


def test_build_weekend_from_race_dict_window():
    weekend = build_weekend_from_race_dict(SAMPLE_RACE, buffer_days=1)

    assert weekend.race_name == "Miami Grand Prix"
    assert weekend.season == "2026"
    # window starts at the earliest session (FirstPractice)
    assert weekend.window_start == datetime(2026, 5, 1, 16, 30, tzinfo=timezone.utc)
    # window ends race day + 1 day buffer
    assert weekend.window_end == datetime(2026, 5, 4, 20, 0, tzinfo=timezone.utc)


def test_is_active_inside_and_outside_window():
    weekend = build_weekend_from_race_dict(SAMPLE_RACE, buffer_days=1)

    during = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    before = weekend.window_start - timedelta(days=2)
    after = weekend.window_end + timedelta(days=2)

    assert is_active(weekend, during) is True
    assert is_active(weekend, before) is False
    assert is_active(weekend, after) is False


def test_build_weekend_handles_missing_session_data():
    minimal = {
        "season": "2026",
        "round": "1",
        "raceName": "Australian Grand Prix",
        "Circuit": {"circuitName": "Albert Park", "Location": {"country": "Australia"}},
        "date": "2026-03-08",
        "time": "05:00:00Z",
    }
    weekend = build_weekend_from_race_dict(minimal, buffer_days=1)
    assert weekend.window_start == datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc)
    assert weekend.window_end == datetime(2026, 3, 9, 5, 0, tzinfo=timezone.utc)


def test_match_roster_in_text_finds_team_and_driver_and_infers_team():
    roster = Roster(
        constructors={"mercedes": "Mercedes", "ferrari": "Ferrari"},
        drivers={
            "hamilton": {"name": "Lewis Hamilton", "team": "ferrari"},
            "russell": {"name": "George Russell", "team": "mercedes"},
        },
    )

    teams, drivers = match_roster_in_text(
        "Lewis Hamilton (GBR) Ferrari at the Miami Grand Prix", roster
    )

    assert drivers == ["hamilton"]
    assert "ferrari" in teams


def test_match_roster_in_text_no_match():
    roster = Roster(constructors={"mercedes": "Mercedes"}, drivers={})
    teams, drivers = match_roster_in_text("A general paddock photo", roster)
    assert teams == []
    assert drivers == []
