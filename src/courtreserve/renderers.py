from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from .models import EventDetails, EventSummary, OrganizationContext


def json_text(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in value
        ]
    return json.dumps(value, indent=2, sort_keys=True)


def render_events(console: Console, events: list[EventSummary]) -> None:
    table = Table("START", "EVENT", "TYPE", "AVAILABILITY", "NUMBER")
    for event in events:
        table.add_row(
            event.start.strftime("%Y-%m-%d %I:%M %p %Z"),
            event.name,
            event.event_type,
            event.availability,
            event.number,
        )
    console.print(table)


def render_types(console: Console, values: list[str]) -> None:
    table = Table("EVENT TYPE")
    for value in values:
        table.add_row(value)
    console.print(table)


def render_organization(console: Console, context: OrganizationContext) -> None:
    table = Table(show_header=False)
    table.add_row("ID", str(context.org_id))
    table.add_row("Name", context.name)
    table.add_row("Timezone", context.timezone)
    table.add_row(
        "Calendar",
        f"{context.app_base_url}/Online/Calendar/Events/{context.org_id}/Month",
    )
    console.print(table)


def render_details(console: Console, details: EventDetails) -> None:
    table = Table(show_header=False)
    for label, value in (
        ("Name", details.name),
        ("Type", details.event_type),
        ("Start", details.start.isoformat() if details.start else None),
        ("End", details.end.isoformat() if details.end else None),
        ("Availability", details.availability),
        ("Description", details.description),
        ("Note", details.note),
        ("URL", details.details_url),
    ):
        if value:
            table.add_row(label, str(value))
    console.print(table)

