---
name: courtreserve-cli
description: Use this skill when working with the CourtReserve CLI in this repo: documenting usage, showing examples, or running the terminal client against public CourtReserve calendars and events.
---

# CourtReserve CLI

## When To Use

Use this skill when the user asks about the CourtReserve terminal client, needs README or usage docs updated, or wants examples for querying public CourtReserve organizations and events.

## Core Facts

- The CLI exists because the CourtReserve website calendar view is hard to scan and filter.
- `--org` accepts either a numeric organization id or a plain organization name.
- Organization names are resolved through CourtReserve's official search endpoint.
- Use `--json` when a harness needs structured output.
- Date ranges are inclusive and limited to 90 days.
- Without explicit dates, event commands query today through 30 days ahead in the organization's timezone.

## Usage Pattern

Prefer these commands when showing examples or validating behavior:

```bash
uv sync
uv run courtreserve organization --org "Sisters Pickleball Club"
uv run courtreserve events --org "Sisters Pickleball Club" --type "Skill Development"
uv run courtreserve event --org 3683 SKILL001
```

## Agent Setup

- Work from the repository root.
- Run the CLI with `uv run courtreserve ...`.
- Use `--json` for machine consumption.
- Verify changes with `UV_CACHE_DIR=/private/tmp/courtreserve-uv-cache uv run pytest`.
