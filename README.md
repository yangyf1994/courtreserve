# CourtReserve CLI

CourtReserve's calendar UI is painful to scan and even worse to filter. This CLI gives you a fast, terminal-first way to find the right organization, surface the events that matter, and inspect details without fighting the website.

Use it when you want to:

- search organizations by natural language instead of hunting for ids
- filter events by name, type, status, and time
- inspect public event details from the terminal
- feed clean JSON into scripts, harnesses, or agents

## Install

For end users, the normal way to consume this kind of Python CLI is to install the tool once and run `courtreserve` directly.

```bash
pipx install courtreserve-cli
courtreserve --help
```

`uv` is still a good fit for local development and agent harnesses. From this repo, use:

```bash
uv sync
uv run courtreserve events --org 3683
uv run courtreserve event-types --org 3683
uv run courtreserve events --org 3683 \
  --start-date 2026-06-15 --end-date 2026-06-21 \
  --type "Skill Development"
```

## Search with natural language

`--org` accepts either a numeric organization id or a plain organization name. The client resolves names through CourtReserve's official search endpoint, so you can search the way people actually talk.

```bash
uv run courtreserve organization --org "Sisters Pickleball Club"
uv run courtreserve events --org "Sisters Pickleball Club" --type "Skill Development"
uv run courtreserve events --org "Sisters Pickleball Club" --name "Open Play" --status open
```

## Usage

Use `--json` for normalized machine-readable output. Date ranges are inclusive and limited to
90 days. Without explicit dates, commands query today through 30 days ahead in the
organization's timezone.

Common commands:

```bash
uv run courtreserve organization --org 3683
uv run courtreserve events --org 3683 --start-date 2026-06-15 --end-date 2026-06-21
uv run courtreserve events --org 3683 --type "Skill Development" --start-after 08:00 --start-before 12:00
uv run courtreserve event --org 3683 SKILL001
uv run courtreserve event https://app.courtreserve.com/Online/Events/Details/3683/SKILL001
```

## Install Guide For Agents

1. Start from the repository root.
2. Run `uv sync`.
3. Invoke the CLI with `uv run courtreserve ...`.
4. Pass `--json` when the harness needs structured output.
5. Verify changes with `UV_CACHE_DIR=/private/tmp/courtreserve-uv-cache uv run pytest`.

## Publishing

Python CLIs like this are usually published to PyPI as wheels and source distributions. Once published, the common install paths are `pipx install courtreserve-cli`, `uv tool install courtreserve-cli`, or `pip install courtreserve-cli`.

This project uses undocumented public CourtReserve endpoints and may need updates when the
upstream site changes.
