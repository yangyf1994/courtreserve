import json
from datetime import date, time
from pathlib import Path

import pytest

from courtreserve.models import EventStatus, OrganizationContext
from courtreserve.parsers import parse_calendar_response
from courtreserve.service import event_types, filter_events, validate_range

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def events():
    context = OrganizationContext(
        org_id=3683,
        name="Basha Tennis",
        timezone="America/Los_Angeles",
        cost_type_id="16781",
    )
    return parse_calendar_response(
        json.loads((FIXTURES / "calendar.json").read_text()), context
    )


def test_filter_type_is_case_insensitive_exact(events) -> None:
    result = filter_events(events, event_types=["skill development"])
    assert [event.number for event in result] == ["SKILL001"]


def test_filter_status_and_time(events) -> None:
    assert [event.number for event in filter_events(events, status=EventStatus.OPEN)] == [
        "SKILL001"
    ]
    assert [
        event.number
        for event in filter_events(events, start_after=time(10), status=EventStatus.FULL)
    ] == ["FULL001"]
    assert [
        event.number for event in filter_events(events, status=EventStatus.WAITLIST)
    ] == ["FULL001"]


def test_event_types_trim_and_deduplicate(events) -> None:
    assert event_types(events) == ["Point Play", "Skill Development"]


def test_filter_type_ignores_trailing_punctuation(events) -> None:
    noisy = [
        events[0],
        events[1].model_copy(update={"event_type": "Skill Development."}),
    ]
    result = filter_events(noisy, event_types=["Skill Development"])
    assert [event.number for event in result] == ["SKILL001", "FULL001"]


def test_event_types_strip_trailing_punctuation(events) -> None:
    noisy = [
        events[0],
        events[1].model_copy(update={"event_type": "Skill Development."}),
    ]
    assert event_types(noisy) == ["Skill Development"]


def test_validate_range() -> None:
    validate_range(date(2026, 1, 1), date(2026, 3, 31))
    with pytest.raises(ValueError):
        validate_range(date(2026, 1, 1), date(2026, 4, 1))
