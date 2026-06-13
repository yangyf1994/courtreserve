from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import typer
from rich.console import Console

from . import __version__
from .client import CourtReserveClient
from .errors import CourtReserveError
from .models import EventStatus, OrganizationContext
from .renderers import (
    json_text,
    render_details,
    render_events,
    render_organization,
    render_types,
)
from .service import event_types, filter_events, validate_range

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
console = Console()
error_console = Console(stderr=True)
_EVENT_URL = re.compile(r"^/Online/Events/Details/(\d+)/([^/?#]+)")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    version: bool = typer.Option(
        False, "--version", callback=version_callback, is_eager=True
    ),
) -> None:
    """Read public CourtReserve event calendars."""
    del version
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(message)s",
    )


def date_range(
    client: CourtReserveClient,
    org: int,
    start_date_value: str | None,
    end_date_value: str | None,
) -> tuple[OrganizationContext, date, date]:
    if (start_date_value is None) != (end_date_value is None):
        raise typer.BadParameter("--start-date and --end-date must be supplied together")
    context = client.bootstrap_organization(org)
    if start_date_value is None:
        start_date = datetime.now(ZoneInfo(context.timezone)).date()
        end_date = start_date + timedelta(days=30)
    else:
        start_date = parse_date(start_date_value, "--start-date")
        assert end_date_value is not None
        end_date = parse_date(end_date_value, "--end-date")
    try:
        validate_range(start_date, end_date)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return context, start_date, end_date


def parse_date(value: str, option: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option} must use YYYY-MM-DD") from exc


def parse_clock(value: str | None, option: str) -> time | None:
    if value is None:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option} must use HH:MM") from exc


@app.command("organization")
def organization_command(
    org: int = typer.Option(..., "--org", min=1),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show public organization metadata."""
    with CourtReserveClient() as client:
        context = client.bootstrap_organization(org)
    if as_json:
        console.print(json_text(context))
    else:
        render_organization(console, context)


@app.command("events")
def events_command(
    org: int = typer.Option(..., "--org", min=1),
    start_date: str | None = typer.Option(None, "--start-date"),
    end_date: str | None = typer.Option(None, "--end-date"),
    name: str | None = typer.Option(None, "--name"),
    event_type: str | None = typer.Option(None, "--type"),
    status: EventStatus = typer.Option(EventStatus.ANY, "--status"),
    start_after: str | None = typer.Option(None, "--start-after"),
    start_before: str | None = typer.Option(None, "--start-before"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List and filter public events."""
    after = parse_clock(start_after, "--start-after")
    before = parse_clock(start_before, "--start-before")
    with CourtReserveClient() as client:
        context, start, end = date_range(client, org, start_date, end_date)
        events = client.list_events(context, start, end)
    filtered = filter_events(
        events,
        name=name,
        event_types=event_type.split(",") if event_type else None,
        status=status,
        start_after=after,
        start_before=before,
    )
    if as_json:
        console.print(json_text(filtered))
    else:
        render_events(console, filtered)


@app.command("event-types")
def event_types_command(
    org: int = typer.Option(..., "--org", min=1),
    start_date: str | None = typer.Option(None, "--start-date"),
    end_date: str | None = typer.Option(None, "--end-date"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List event types observed in a date range."""
    with CourtReserveClient() as client:
        context, start, end = date_range(client, org, start_date, end_date)
        values = event_types(client.list_events(context, start, end))
    if as_json:
        console.print(json_text(values))
    else:
        render_types(console, values)


@app.command("event")
def event_command(
    identifier: str = typer.Argument(..., help="Event Number or full event details URL"),
    org: int | None = typer.Option(None, "--org", min=1),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect one public event."""
    parsed_org, number = parse_event_identifier(identifier)
    if parsed_org is not None:
        if org is not None and org != parsed_org:
            raise typer.BadParameter("--org conflicts with the organization in the URL")
        org = parsed_org
    if org is None:
        raise typer.BadParameter("--org is required when passing an event Number")

    with CourtReserveClient() as client:
        context = client.bootstrap_organization(org)
        details, degraded = client.get_event_details(context, number)
    if degraded:
        error_console.print(
            "Warning: enhanced event details were unavailable; showing public page data."
        )
    if as_json:
        console.print(json_text(details))
    else:
        render_details(console, details)


def parse_event_identifier(identifier: str) -> tuple[int | None, str]:
    parsed = urlparse(identifier)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc.endswith(
            "courtreserve.com"
        ):
            raise typer.BadParameter("Event URL must be hosted by courtreserve.com")
        match = _EVENT_URL.match(parsed.path)
        if not match:
            raise typer.BadParameter("Unsupported CourtReserve event URL")
        return int(match.group(1)), match.group(2)
    if "/" in identifier or not identifier.strip():
        raise typer.BadParameter("Invalid event Number")
    return None, identifier.strip()


def run() -> None:
    try:
        app()
    except CourtReserveError as exc:
        error_console.print(f"Error: {exc}")
        raise SystemExit(4) from None


if __name__ == "__main__":
    run()
