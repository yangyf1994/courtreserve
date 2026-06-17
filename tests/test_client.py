from datetime import date
from pathlib import Path

import httpx
import pytest

from courtreserve.client import CourtReserveClient
from courtreserve.errors import NotFoundError, UpstreamError

FIXTURES = Path(__file__).parent / "fixtures"


def test_client_bootstrap_and_list_events() -> None:
    organization = (FIXTURES / "organization.html").read_text()
    calendar = (FIXTURES / "calendar.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=organization)
        assert request.method == "POST"
        assert "jsonData=" in request.content.decode()
        return httpx.Response(200, text=calendar)

    with CourtReserveClient(transport=httpx.MockTransport(handler)) as client:
        context = client.bootstrap_organization(3683)
        events = client.list_events(
            context, date(2026, 6, 16), date(2026, 6, 17)
        )

    assert [event.number for event in events] == ["SKILL001", "FULL001"]


def test_client_bootstrap_resolves_organization_name_via_official_search() -> None:
    organization = (FIXTURES / "organization.html").read_text()
    official_results = {
        "results": [
            {
                "organizationId": 16979,
                "name": "Sisters Pickleball Club",
                "createAccountUrl": "https://app.courtreserve.com/Online/Account/Register/16979",
            }
        ]
    }
    calendar = (FIXTURES / "calendar.json").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "backend.courtreserve.com":
            assert request.method == "POST"
            assert request.url.path == "/api/public/search-organization"
            assert request.read().decode() == '{"searchTerm":"Sisters Pickleball Club"}'
            return httpx.Response(200, json=official_results)
        if request.url.path == "/Online/Calendar/Events/16979/Month":
            return httpx.Response(200, text=organization)
        assert request.url.path == "/Online/Calendar/ReadCalendarEvents/16979"
        assert request.method == "POST"
        assert "jsonData=" in request.content.decode()
        return httpx.Response(200, text=calendar)

    with CourtReserveClient(transport=httpx.MockTransport(handler)) as client:
        context = client.bootstrap_organization("Sisters Pickleball Club")
        events = client.list_events(context, date(2026, 6, 16), date(2026, 6, 17))

    assert context.org_id == 16979
    assert context.name == "Basha Tennis"
    assert [event.number for event in events] == ["SKILL001", "FULL001"]


def test_client_bootstrap_does_not_fall_back_when_official_search_fails() -> None:
    official_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal official_attempts
        if request.url.host == "backend.courtreserve.com":
            official_attempts += 1
            return httpx.Response(500, text="upstream failure")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with CourtReserveClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UpstreamError, match="Could not find a CourtReserve organization"):
            client.bootstrap_organization("Sisters Pickleball Club")

    assert official_attempts == 3


def test_get_event_details_raises_not_found_when_detail_api_404s() -> None:
    page = """
    <html>
      <head><title>Event Details | powered by CourtReserve</title></head>
      <body>
        <script>
          url: fixUrl('https://events.courtreserve.com/Online/EventsApi/ApiDetails?id=3683&amp;number=NOPE')
        </script>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Online/Calendar/Events/3683/Month":
            return httpx.Response(200, text=(FIXTURES / "organization.html").read_text())
        if request.url.path == "/Online/Events/Details/3683/NOPE":
            return httpx.Response(200, text=page)
        if request.url.path == "/Online/EventsApi/ApiDetails":
            return httpx.Response(
                200,
                text="""
                <section class="our-error bgc-fa">
                  <div class="error_page newsletter_widget">
                    <h4>Sorry, but the Event you are looking for has not been found</h4>
                  </div>
                </section>
                """,
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with CourtReserveClient(transport=httpx.MockTransport(handler)) as client:
        context = client.bootstrap_organization(3683)
        with pytest.raises(NotFoundError):
            client.get_event_details(context, "NOPE")
