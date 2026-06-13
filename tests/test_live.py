from datetime import date

import pytest

from courtreserve.client import CourtReserveClient
from courtreserve.service import filter_events


@pytest.mark.live
def test_live_skill_development_next_week() -> None:
    with CourtReserveClient() as client:
        context = client.bootstrap_organization(3683)
        events = client.list_events(context, date(2026, 6, 15), date(2026, 6, 21))
    matches = filter_events(events, event_types=["Skill Development"])
    assert matches
