import json
from datetime import datetime
from pathlib import Path

from courtreserve.models import OrganizationContext
from courtreserve.parsers import (
    parse_aspnet_date,
    parse_calendar_response,
    parse_detail_api_html,
    parse_detail_page,
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


def test_parse_detail_api_html_extracts_structured_fields() -> None:
    fallback = parse_detail_page(
        "<title>Event Details | powered by CourtReserve</title>",
        3683,
        "GTMYM5A368331",
        "https://app.courtreserve.com/Online/Events/Details/3683/GTMYM5A368331",
    )
    fragment = """
    <div data-testid="details-container">
      <span data-testid="event-type">Skill Development</span>
      <h4 data-testid="event-name">3.0 - 3.5 Singles Tactics (UTR 3.0-5.0)</h4>
      <span class="icon-title-row">
        <span data-testid="circle-icon"></span>
        <span data-testid="title-part">Full</span>
      </span>
      <span data-testid="date">Mon, Jun 15th</span>
      <input id="FirstEventDate" value="6/15/2026 6:30:00 PM" />
      <span data-testid="times">6:30p - 8p</span>
      <iframe id="eventDescriptionData" srcdoc="<div><p>Bring water.</p></div>"></iframe>
    </div>
    """

    details = parse_detail_api_html(fragment, fallback, "America/Los_Angeles")

    assert details.enhanced is True
    assert details.name == "3.0 - 3.5 Singles Tactics (UTR 3.0-5.0)"
    assert details.event_type == "Skill Development"
    assert details.availability == "Full"
    assert details.description == "Bring water."
    assert details.start == datetime.fromisoformat("2026-06-15T18:30:00-07:00")
    assert details.end == datetime.fromisoformat("2026-06-15T20:00:00-07:00")


def test_parse_detail_api_html_recurring_full_event_uses_button_and_note() -> None:
    fallback = parse_detail_page(
        "<title>Event Details | powered by CourtReserve</title>",
        13124,
        "QPKCJUC13124109",
        "https://app.courtreserve.com/Online/Events/Details/13124/QPKCJUC13124109",
    )
    fragment = """
    <div data-testid="details-container">
      <span data-testid="event-type">Leagues</span>
      <h4 data-testid="event-name">Beginner League (Tuesday/Thursday)</h4>
      <span data-testid="no-drop-in-date">Jun 2nd - Jun 25th (8 dates)</span>
      <span data-testid="no-drop-in-dates">6/2, 6/4, 6/9, 6/11, 6/16, 6/18, 6/23, 6/25</span>
      <span data-testid="occurence-time">6:00 PM - 8:00 PM</span>
      <input id="FirstEventDate" value="6/2/2026 6:00:00 PM" />
      <a data-testid="register-full-event-btn">Register for Full Event</a>
      <p data-testid="note">You will be charged the $105 at the start of the event.</p>
      <iframe id="eventDescriptionData" srcdoc="<div><p>League Season Is Here!</p></div>"></iframe>
    </div>
    """

    details = parse_detail_api_html(fragment, fallback, "America/New_York")

    assert details.enhanced is True
    assert details.name == "Beginner League (Tuesday/Thursday)"
    assert details.event_type == "Leagues"
    assert details.availability == "Register for Full Event"
    assert details.note == "You will be charged the $105 at the start of the event."
    assert details.description == "League Season Is Here!"
    assert details.start is None
    assert details.end is None
