import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from courtreserve.cli import app, parse_event_identifier, run
from courtreserve.errors import UpstreamError

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_parse_event_identifier() -> None:
    assert parse_event_identifier("ABC123") == (None, "ABC123")
    assert parse_event_identifier(
        "https://app.courtreserve.com/Online/Events/Details/3683/ABC123"
    ) == (3683, "ABC123")


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "event-types" in result.stdout
    assert "organization" in result.stdout


def test_fixture_is_valid_json() -> None:
    assert len(json.loads((FIXTURES / "calendar.json").read_text())["Data"]) == 2


def test_run_converts_expected_errors_to_exit_code() -> None:
    with patch("courtreserve.cli.app", side_effect=UpstreamError("offline")):
        with pytest.raises(SystemExit) as exc:
            run()
    assert exc.value.code == 4
