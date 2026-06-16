# CourtReserve CLI

Read public CourtReserve event calendars from the terminal, with natural-language organization lookup and filters that are actually usable.

CourtReserve's calendar UI is difficult to scan when you only care about a subset of events. This project gives you a small read-only CLI for finding organizations, listing upcoming events, filtering by type or status, and inspecting event details without browser automation or login.

> [!NOTE]
> `--org` accepts either a numeric organization ID or a plain organization name. Organization names are resolved through CourtReserve's official public search endpoint, so you can query clubs the way people actually talk about them.

> [!WARNING]
> This project uses undocumented public CourtReserve endpoints. Upstream changes can break the CLI, and users should respect CourtReserve's terms and rate limits.

## Features

- Search organizations by name or use a known numeric ID.
- Query clubs in natural language and filter events down to the ones you actually care about.
- List events over a date range and filter by event name, type, status, or start time.
- Inspect a single event by event number or full CourtReserve event URL.
- Emit normalized JSON for scripts, agents, and other automation.
- Stay read-only: no login, no browser automation, no account actions.
- Work across CourtReserve clubs that expose public calendar data.

## Quick Start

### Run from source

```bash
uv sync
uv run courtreserve --help
uv run courtreserve events --org "Sisters Pickleball Club"
```

### Install as a local CLI

If you want a persistent `courtreserve` command on your machine today, install from the checkout:

```bash
pipx install .
courtreserve --help
```

When this project is published to PyPI, the normal install flow will be:

```bash
pipx install courtreserve-cli
```

## Common Commands

### Show organization metadata

```bash
uv run courtreserve organization --org "Sisters Pickleball Club"
uv run courtreserve organization --org 3683
```

### List events

```bash
uv run courtreserve events --org 3683
uv run courtreserve events --org "Sisters Pickleball Club" \
  --start-date 2026-06-15 --end-date 2026-06-21
```

### Filter events

```bash
uv run courtreserve events --org 3683 --type "Skill Development"
uv run courtreserve events --org 3683 --name "Open Play" --status open
uv run courtreserve events --org 3683 --start-after 08:00 --start-before 12:00
```

Supported `--status` values:

- `any`
- `open`
- `full`
- `waitlist`

### Inspect one event

```bash
uv run courtreserve event --org 3683 SKILL001
uv run courtreserve event \
  https://app.courtreserve.com/Online/Events/Details/3683/SKILL001
```

### Emit JSON

```bash
uv run courtreserve events --org 3683 --json
uv run courtreserve event --org 3683 SKILL001 --json
```

## How It Works

The CLI builds on public CourtReserve calendar and event pages plus the associated XHR endpoints those pages already use. Internally it:

- resolves a club name in natural language to an organization ID
- loads organization metadata, including timezone
- fetches calendar event payloads in month-sized chunks
- normalizes the results into structured models for terminal or JSON output

Date ranges are inclusive and capped at 90 days. If you do not pass explicit dates, event queries default to today through 30 days ahead in the organization's local timezone.

## Development

### Environment

```bash
uv sync
```

### Tests

```bash
UV_CACHE_DIR=/private/tmp/courtreserve-uv-cache uv run pytest
```

There is also a small live test that exercises the public endpoints directly:

```bash
UV_CACHE_DIR=/private/tmp/courtreserve-uv-cache uv run pytest -m live
```

## Agent Usage

For harnesses and other automation:

- run commands with `uv run courtreserve ...`
- pass `--json` when structured output is needed
- prefer organization names when the caller does not already know the numeric ID
- assume no authenticated session is required
- use it for any CourtReserve club with a public calendar surface

## Publishing

This project is packaged as a standard Python CLI with a `courtreserve` console entry point. The expected public distribution target is PyPI, with end-user installs via `pipx`, `uv tool`, or `pip`.
