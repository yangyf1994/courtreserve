from datetime import date
from pathlib import Path

import httpx
import pytest

from courtreserve.client import CourtReserveClient
from courtreserve.errors import UpstreamError

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
