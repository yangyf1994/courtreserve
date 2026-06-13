from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import OrganizationContext


def split_by_month(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        last = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        chunk_end = min(last, end)
        ranges.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return ranges


def build_calendar_payload(
    context: OrganizationContext, start: date, end: date
) -> dict[str, str]:
    tz = ZoneInfo(context.timezone)
    start_dt = datetime.combine(start, time.min, tzinfo=tz)
    exclusive_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    selected = datetime.combine(start, time(hour=12), tzinfo=tz)

    body = {
        "startDate": start_dt.isoformat(),
        "end": exclusive_end.isoformat(),
        "Date": start_dt.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "orgId": str(context.org_id),
        "TimeZone": context.timezone,
        "KendoStart": {"Year": start.year, "Month": start.month, "Day": start.day},
        "KendoEnd": {
            "Year": exclusive_end.year,
            "Month": exclusive_end.month,
            "Day": exclusive_end.day,
        },
        "Categories": [],
        "EventTagIds": [],
        "CostTypeId": context.cost_type_id,
        "MemberId": "",
        "FamilyId": "",
        "FamilyMemberIds": "",
        "EventSessionIds": [],
        "ViewType": "Month",
        "MonthlySelectedDate": selected.isoformat(),
        "IsLeagueCalendar": "False",
        "IncludeLeagues": "False",
        "IncludeRoundRobins": "False",
    }
    import json

    return {"jsonData": json.dumps(body, separators=(",", ":"))}

