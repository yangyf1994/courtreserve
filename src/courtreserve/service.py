from __future__ import annotations

import re
from datetime import date, time

from .client import CourtReserveClient
from .models import EventStatus, EventSummary, OrganizationContext


def normalize_event_type_key(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip()).casefold()
    return re.sub(r"^[^\w]+|[^\w]+$", "", collapsed)


def normalize_event_type_label(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip())
    return re.sub(r"^[^\w]+|[^\w]+$", "", collapsed)


def filter_events(
    events: list[EventSummary],
    *,
    name: str | None = None,
    event_types: list[str] | None = None,
    status: EventStatus = EventStatus.ANY,
    start_after: time | None = None,
    start_before: time | None = None,
) -> list[EventSummary]:
    type_keys = {
        normalize_event_type_key(value)
        for value in event_types or []
        if normalize_event_type_key(value)
    }
    name_key = name.casefold() if name else None
    result: list[EventSummary] = []
    for event in events:
        if name_key and name_key not in event.name.casefold():
            continue
        if type_keys and normalize_event_type_key(event.event_type) not in type_keys:
            continue
        if status == EventStatus.OPEN and (
            event.in_past or event.is_full or not event.registration_open
        ):
            continue
        if status == EventStatus.FULL and not event.is_full:
            continue
        if status == EventStatus.WAITLIST and not (event.is_full and event.allow_waitlist):
            continue
        local_start = event.start.timetz().replace(tzinfo=None)
        if start_after and local_start < start_after:
            continue
        if start_before and local_start > start_before:
            continue
        result.append(event)
    return sorted(result, key=lambda item: (item.start, item.name.casefold(), item.number))


def event_types(events: list[EventSummary]) -> list[str]:
    unique: dict[str, str] = {}
    for event in events:
        value = normalize_event_type_label(event.event_type)
        if value:
            unique.setdefault(normalize_event_type_key(value), value)
    return sorted(unique.values(), key=str.casefold)


def validate_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")
    if (end - start).days + 1 > 90:
        raise ValueError("Date range cannot exceed 90 inclusive days")


def resolve_context_and_events(
    client: CourtReserveClient, org_id: int | str, start: date, end: date
) -> tuple[OrganizationContext, list[EventSummary]]:
    context = client.bootstrap_organization(org_id)
    return context, client.list_events(context, start, end)
