from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .errors import NotFoundError, UpstreamError
from .models import EventDetails, EventSummary, OrganizationContext

_ASPNET_DATE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")
_COST_TYPE = re.compile(r"CostTypeId:\s*['\"]([^'\"]+)['\"]")
_TIMEZONE = re.compile(r"(?:TimeZone:\s*['\"]|\"timezone\":\")([^'\"]+)")
_API_DETAILS = re.compile(r"url:\s*fixUrl\('([^']*EventsApi/ApiDetails[^']*)'\)")


def _clean_event_title(value: str) -> str:
    return re.sub(r"\s*\|\s*powered by CourtReserve\s*$", "", value).strip()


def _normalize_clock_text(value: str) -> str:
    compact = re.sub(r"\s+", "", value).upper()
    compact = re.sub(r"(?<=\d)(A|P)$", r"\1M", compact)
    return compact


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
    name = _clean_event_title(name)
    description_node = soup.select_one(".event-description, [data-testid='event-description']")
    return EventDetails(
        org_id=org_id,
        number=number,
        name=name,
        description=description_node.get_text(" ", strip=True) if description_node else None,
        details_url=page_url,
        enhanced=False,
    )


def parse_detail_api_html(fragment: str, fallback: EventDetails, timezone: str) -> EventDetails:
    soup = BeautifulSoup(fragment, "html.parser")
    if is_not_found_detail_html(soup):
        raise NotFoundError(f"CourtReserve event not found: {fallback.org_id}/{fallback.number}")
    name_node = soup.select_one("[data-testid='event-name']")
    type_node = soup.select_one("[data-testid='event-type']")
    availability = parse_detail_html_availability(soup)
    description_frame = soup.select_one("iframe#eventDescriptionData")
    note_node = soup.select_one("[data-testid='note']")
    description: str | None = None
    if description_frame and description_frame.has_attr("srcdoc"):
        description_doc = BeautifulSoup(description_frame["srcdoc"], "html.parser")
        description = description_doc.get_text(" ", strip=True) or None

    start = parse_detail_html_start(soup, timezone)
    end = parse_detail_html_end(soup, start, timezone)

    return fallback.model_copy(
        update={
            "name": _clean_event_title(
                name_node.get_text(" ", strip=True) if name_node else fallback.name
            ),
            "event_type": optional_text(type_node.get_text(" ", strip=True) if type_node else None),
            "start": start or fallback.start,
            "end": end or fallback.end,
            "description": description or fallback.description,
            "note": optional_text(note_node.get_text(" ", strip=True) if note_node else None),
            "availability": availability,
            "enhanced": True,
        }
    )


def parse_detail_html_start(soup: BeautifulSoup, timezone: str) -> datetime | None:
    if soup.select_one("[data-testid='no-drop-in-date']") or soup.select_one(
        "[data-testid='no-drop-in-dates']"
    ):
        return None
    date_node = soup.select_one("[data-testid='date']")
    time_node = soup.select_one("[data-testid='times']")
    if date_node and time_node:
        date_text = date_node.get_text(" ", strip=True)
        range_text = time_node.get_text(" ", strip=True)
        if date_text and range_text:
            start_text = range_text.split("-", 1)[0].strip()
            start_text = _normalize_clock_text(start_text)
            cleaned_date = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_text)
            for fmt in (
                "%a, %b %d %Y %I:%M%p",
                "%A, %b %d %Y %I:%M%p",
                "%a, %b %d %Y %I%p",
                "%A, %b %d %Y %I%p",
            ):
                try:
                    parsed = datetime.strptime(
                        f"{cleaned_date} {datetime.now().year} {start_text}", fmt
                    )
                    return parsed.replace(tzinfo=ZoneInfo(timezone))
                except ValueError:
                    continue
    first_event_date = soup.select_one("input#FirstEventDate")
    if first_event_date and first_event_date.has_attr("value"):
        value = str(first_event_date["value"]).strip()
        if value:
            try:
                parsed = datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p")
                return parsed.replace(tzinfo=ZoneInfo(timezone))
            except ValueError:
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d %I:%M:%S %p")
                    return parsed.replace(tzinfo=ZoneInfo(timezone))
                except ValueError:
                    pass
    return None


def parse_detail_html_end(
    soup: BeautifulSoup, start: datetime | None, timezone: str
) -> datetime | None:
    if start is None:
        return None
    time_node = soup.select_one("[data-testid='times']")
    if not time_node:
        return None
    range_text = time_node.get_text(" ", strip=True)
    parts = [value.strip() for value in range_text.split("-", 1)]
    if len(parts) != 2 or not parts[1]:
        return None
    end_text = _normalize_clock_text(parts[1])
    end_clock = None
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            end_clock = datetime.strptime(end_text, fmt).time()
            break
        except ValueError:
            continue
    if end_clock is None:
        return None
    return start.replace(
        hour=end_clock.hour,
        minute=end_clock.minute,
        second=0,
        microsecond=0,
        tzinfo=ZoneInfo(timezone),
    )


def parse_detail_html_availability(soup: BeautifulSoup) -> str | None:
    circle_icon = soup.select_one("[data-testid='circle-icon']")
    if circle_icon is not None:
        row = circle_icon.find_parent(class_="icon-title-row")
        if row is not None:
            availability_row = row.select_one("[data-testid='title-part']")
            if availability_row:
                return optional_text(availability_row.get_text(" ", strip=True))

    action_button = soup.select_one(
        "[data-testid='register-full-event-btn'], "
        "[data-testid='join-waitlisted-btn'], "
        "[data-testid='register-btn']"
    )
    if action_button:
        return optional_text(action_button.get_text(" ", strip=True))

    return None


def is_not_found_detail_html(soup: BeautifulSoup) -> bool:
    error_page = soup.select_one(".error_page")
    if error_page is None:
        return False
    message = error_page.get_text(" ", strip=True).casefold()
    return "not been found" in message


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
