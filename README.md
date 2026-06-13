# CourtReserve CLI

Read public CourtReserve event calendars from the terminal without login or browser automation.

```bash
uv sync
uv run courtreserve events --org 3683
uv run courtreserve event-types --org 3683
uv run courtreserve events --org 3683 \
  --start-date 2026-06-15 --end-date 2026-06-21 \
  --type "Skill Development"
```

Use `--json` for normalized machine-readable output. Date ranges are inclusive and limited
to 90 days. Without explicit dates, commands query today through 30 days ahead in the
organization's timezone.

This project uses undocumented public CourtReserve endpoints and may need updates when the
upstream site changes.

