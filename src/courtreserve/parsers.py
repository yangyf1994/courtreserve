from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .errors import UpstreamError
from .models import EventDetails, EventSummary, OrganizationContext

_ASPNET_DATE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")
_COST_TYPE = re.compile(r"CostTypeId:\s*['\"]([^'\"]+)['\"]")
_TIMEZONE = re.compile(r"(?:TimeZone:\s*['\"]|\"timezone\":\")([^'\"]+)")
_API_DETAILS = re.compile(r"url:\s*fixUrl\('([^']*EventsApi/ApiDetails[^']*)'\)")


def parse_aspnet_date(value: str, timezone: str) -> datetime:
    match = _ASPNET_DATE.match(value)
    if not match:
        raise UpstreamError(f"Unsupported CourtReserve date: {value!r}")
    timestamp = int(match.group(1)) / 1000
    return datetime.fromtimestamp(timestamp, tz=ZoneInfo(timezone))


def parse_organization_page(
    page: str, org_id: int, app_base_url: str = "https://app.courtreserve.com"
) -> OrganizationContext:
    soup = BeautifulSoup(page, "html.parser")
    metadata = soup.find(None, attrs={"org-initialized": "true"})
    name = metadata.get("org-name") if metadata else None
    timezone = metadata.get("org-timezone") if metadata else None
    events_base = metadata.get("org-api4url") if metadata else None
    if events_base:
        events_base = "https://events.courtreserve.com"

    if not name:
        portal_link = soup.find("a", href=f"/Online/Portal/Index/{org_id}")
        if portal_link:
            name = portal_link.get("title") or portal_link.get_text(" ", strip=True)
    if not timezone:
        timezone_match = _TIMEZONE.search(page)
        timezone = timezone_match.group(1) if timezone_match else None

    cost_match = _COST_TYPE.search(page)
    if not name or not timezone or not cost_match:
        raise UpstreamError("Could not discover organization metadata from calendar page")

    return OrganizationContext(
        org_id=org_id,
        name=str(name),
        timezone=str(timezone),
        cost_type_id=cost_match.group(1),
        app_base_url=app_base_url.rstrip("/"),
        events_base_url=str(events_base or "https://events.courtreserve.com").rstrip("/"),
    )


def parse_calendar_response(
    payload: dict[str, Any], context: OrganizationContext
) -> list[EventSummary]:
    if payload.get("Errors"):
        raise UpstreamError(f"CourtReserve calendar error: {payload['Errors']}")
    raw_events = payload.get("Data")
    if not isinstance(raw_events, list):
        raise UpstreamError("CourtReserve calendar response did not contain a Data array")

    events: list[EventSummary] = []
    for raw in raw_events:
        try:
            events.append(
                EventSummary(
                    org_id=context.org_id,
                    number=str(raw["Number"]),
                    uq_id=str(raw.get("UqId") or raw["Number"]),
                    event_id=int(raw["EventId"]),
                    reservation_id=int(raw["ReservationId"]),
                    name=str(raw.get("EventName") or raw.get("Title") or "").strip(),
                    event_type=str(raw.get("EventType") or "").strip(),
                    start=parse_aspnet_date(str(raw["Start"]), context.timezone),
                    end=parse_aspnet_date(str(raw["End"]), context.timezone),
                    capacity=raw.get("MaxMembersOnEvent"),
                    signed_members=raw.get("SignedMembers"),
                    waitlist_count=raw.get("WaitListCount"),
                    is_full=bool(raw.get("IsFull")),
                    registration_open=bool(raw.get("RegistrationOpen")),
                    allow_waitlist=bool(raw.get("AllowWaitList")),
                    in_past=bool(raw.get("InPast")),
                    slots_info=(str(raw["SlotsInfo"]).strip() if raw.get("SlotsInfo") else None),
                    note=(str(raw["EventNote"]).strip() if raw.get("EventNote") else None),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamError("CourtReserve returned an invalid event record") from exc
    return events


def extract_details_api_url(page: str, page_url: str) -> str | None:
    match = _API_DETAILS.search(page)
    if not match:
        return None
    return urljoin(page_url, html.unescape(match.group(1)))


def parse_detail_page(page: str, org_id: int, number: str, page_url: str) -> EventDetails:
    soup = BeautifulSoup(page, "html.parser")
    title = soup.find("h1") or soup.find("h2") or soup.find("title")
    name = title.get_text(" ", strip=True) if title else f"Event {number}"
    name = re.sub(r"\s*\|\s*powered by CourtReserve\s*$", "", name)
    description_node = soup.select_one(".event-description, [data-testid='event-description']")
    return EventDetails(
        org_id=org_id,
        number=number,
        name=name,
        description=description_node.get_text(" ", strip=True) if description_node else None,
        details_url=page_url,
        enhanced=False,
    )


def parse_detail_api(
    payload: Any, fallback: EventDetails, timezone: str
) -> EventDetails:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        raise UpstreamError("CourtReserve event details response was not an object")

    def first(*keys: str) -> Any:
        for key in keys:
            if data.get(key) is not None:
                return data[key]
        return None

    start_raw = first("Start", "EventStart", "start")
    end_raw = first("End", "EventEnd", "end")
    start = parse_flexible_datetime(start_raw, timezone)
    end = parse_flexible_datetime(end_raw, timezone)
    return fallback.model_copy(
        update={
            "name": str(first("EventName", "Title", "name") or fallback.name).strip(),
            "event_type": optional_text(first("EventType", "eventType")),
            "start": start,
            "end": end,
            "description": optional_text(first("Description", "description"))
            or fallback.description,
            "note": optional_text(first("EventNote", "note")),
            "availability": optional_text(first("SlotsInfo", "availability")),
            "enhanced": True,
        }
    )


def parse_flexible_datetime(value: Any, timezone: str) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if _ASPNET_DATE.match(text):
        return parse_aspnet_date(text, timezone)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.astimezone(ZoneInfo(timezone))


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def loads_json(response_text: str) -> Any:
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise UpstreamError("CourtReserve returned invalid JSON") from exc
