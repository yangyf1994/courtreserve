import json
from datetime import datetime
from pathlib import Path

from courtreserve.models import OrganizationContext
from courtreserve.parsers import (
    parse_aspnet_date,
    parse_calendar_response,
    parse_organization_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_organization_page() -> None:
    context = parse_organization_page(
        (FIXTURES / "organization.html").read_text(), 3683
    )
    assert context.name == "Basha Tennis"
    assert context.timezone == "America/Los_Angeles"
    assert context.cost_type_id == "16781"


def test_parse_organization_from_calendar_layout() -> None:
    context = parse_organization_page(
        (FIXTURES / "calendar_page.html").read_text(), 3683
    )
    assert context.name == "Basha Tennis"
    assert context.timezone == "America/Los_Angeles"


def test_parse_aspnet_date_uses_organization_timezone() -> None:
    parsed = parse_aspnet_date("/Date(1781629200000)/", "America/Los_Angeles")
    assert parsed == datetime.fromisoformat("2026-06-16T10:00:00-07:00")


def test_parse_calendar_response_normalizes_events() -> None:
    context = OrganizationContext(
        org_id=3683,
        name="Basha Tennis",
        timezone="America/Los_Angeles",
        cost_type_id="16781",
    )
    payload = json.loads((FIXTURES / "calendar.json").read_text())
    events = parse_calendar_response(payload, context)
    assert len(events) == 2
    assert events[0].event_type == "Skill Development"
    assert events[0].spots_remaining == 2
    assert events[1].availability == "Waitlist"
