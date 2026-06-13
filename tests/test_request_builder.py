import json
from datetime import date

from courtreserve.models import OrganizationContext
from courtreserve.request_builder import build_calendar_payload, split_by_month


def context() -> OrganizationContext:
    return OrganizationContext(
        org_id=3683,
        name="Basha Tennis",
        timezone="America/Los_Angeles",
        cost_type_id="16781",
    )


def test_split_by_month() -> None:
    assert split_by_month(date(2026, 6, 29), date(2026, 7, 2)) == [
        (date(2026, 6, 29), date(2026, 6, 30)),
        (date(2026, 7, 1), date(2026, 7, 2)),
    ]


def test_build_calendar_payload_uses_exclusive_end() -> None:
    payload = json.loads(
        build_calendar_payload(context(), date(2026, 6, 15), date(2026, 6, 21))[
            "jsonData"
        ]
    )
    assert payload["orgId"] == "3683"
    assert payload["KendoStart"] == {"Year": 2026, "Month": 6, "Day": 15}
    assert payload["KendoEnd"] == {"Year": 2026, "Month": 6, "Day": 22}

