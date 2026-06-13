from datetime import date
from pathlib import Path

import httpx

from courtreserve.client import CourtReserveClient

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
