import pytest
from unittest.mock import patch
from typer.testing import CliRunner
from story_forecaster.cli import app

runner = CliRunner()

def test_doctor_command_success():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Story Forecaster System Health & Readiness Doctor" in result.output
    assert "Database (SQLite/ORM)" in result.output
    assert "Python Environment" in result.output
    assert "Target Corpus (Chapters)" in result.output
    assert "Configuration (settings.yaml)" in result.output
    assert "System check completed" in result.output

def test_doctor_command_probe_api():
    result = runner.invoke(app, ["doctor", "--probe-api"])
    assert result.exit_code == 0
    assert "LLM Provider Probe" in result.output
    assert "SKIPPED" in result.output

def test_doctor_command_failure_exit_code():
    with patch("story_forecaster.cli.SessionLocal", side_effect=RuntimeError("Simulated DB connection failure")):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "System health check failed" in result.output
        assert "FAILED" in result.output
