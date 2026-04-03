"""Core CLI tests: version, help, auth commands, cache commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from linear_cli.cli import app
from linear_cli.client import LinearAPIError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def invoke(runner, *args, **kwargs):
    return runner.invoke(app, list(args), **kwargs)


def parse_json(result):
    return json.loads(result.stdout)


# ===========================================================================
# --version
# ===========================================================================


def test_version_flag(runner):
    result = invoke(runner, "--version")
    assert result.exit_code == 0


def test_version_short_flag(runner):
    result = invoke(runner, "-V")
    assert result.exit_code == 0


# ===========================================================================
# --help / no args
# ===========================================================================


def test_root_help(runner):
    result = invoke(runner, "--help")
    assert result.exit_code == 0
    assert "linear" in result.stdout.lower()


def test_no_args_shows_help(runner):
    result = invoke(runner)
    # Typer's no_args_is_help exits with 0 or 2 depending on version
    assert result.exit_code in (0, 2)


def test_auth_help(runner):
    result = invoke(runner, "auth", "--help")
    assert result.exit_code == 0
    assert "login" in result.stdout


def test_issues_help(runner):
    result = invoke(runner, "issues", "--help")
    assert result.exit_code == 0
    assert "list" in result.stdout


def test_projects_help(runner):
    result = invoke(runner, "projects", "--help")
    assert result.exit_code == 0


def test_teams_help(runner):
    result = invoke(runner, "teams", "--help")
    assert result.exit_code == 0


# ===========================================================================
# auth login
# ===========================================================================


def test_auth_login_with_key(runner):
    mock_viewer = {"id": "u1", "name": "Alice", "email": "a@b.com"}
    with (
        patch("linear_cli.cli.Client") as MockClient,
        patch("linear_cli.cli.save_api_key") as mock_save,
    ):
        MockClient.return_value.viewer.return_value = mock_viewer
        result = invoke(runner, "auth", "login", "--key", "lin_api_testkey")
    assert result.exit_code == 0
    mock_save.assert_called_once_with("lin_api_testkey")


def test_auth_login_json_output(runner):
    mock_viewer = {"id": "u1", "name": "Alice", "email": "a@b.com"}
    with (
        patch("linear_cli.cli.Client") as MockClient,
        patch("linear_cli.cli.save_api_key"),
    ):
        MockClient.return_value.viewer.return_value = mock_viewer
        result = invoke(runner, "auth", "login", "--key", "lin_api_testkey", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["authenticated"] is True
    assert "user" in data["data"]


def test_auth_login_invalid_key_returns_exit_2(runner):
    with patch("linear_cli.cli.Client") as MockClient:
        MockClient.return_value.viewer.side_effect = LinearAPIError("Unauthorized", 401)
        result = invoke(runner, "auth", "login", "--key", "lin_api_bad")
    assert result.exit_code == 2


def test_auth_login_empty_key_returns_exit_4(runner):
    result = invoke(runner, "auth", "login", "--key", "   ")
    assert result.exit_code == 4


def test_auth_login_empty_key_json(runner):
    result = invoke(runner, "auth", "login", "--key", "   ", "--json")
    assert result.exit_code == 4
    data = parse_json(result)
    assert data["error"]["code"] == "validation"


def test_auth_login_help_shows_examples(runner):
    result = invoke(runner, "auth", "login", "--help")
    assert "Examples" in result.stdout or "example" in result.stdout.lower() or "--key" in result.stdout


# ===========================================================================
# auth status
# ===========================================================================


def test_auth_status_authenticated(runner):
    mock_viewer = {"id": "u1", "name": "Alice", "email": "a@b.com"}
    with (
        patch("linear_cli.cli.get_api_key", return_value="lin_api_test"),
        patch("linear_cli.cli.get_auth_source", return_value="environment"),
        patch("linear_cli.cli.get_auth_status", return_value={"authenticated": True, "source": "environment", "keyring_available": False}),
        patch("linear_cli.cli.Client") as MockClient,
    ):
        MockClient.return_value.viewer.return_value = mock_viewer
        result = invoke(runner, "auth", "status")
    assert result.exit_code == 0


def test_auth_status_json(runner):
    mock_viewer = {"id": "u1", "name": "Alice", "email": "a@b.com"}
    with (
        patch("linear_cli.cli.get_api_key", return_value="lin_api_test"),
        patch("linear_cli.cli.get_auth_source", return_value="environment"),
        patch("linear_cli.cli.get_auth_status", return_value={"authenticated": True, "source": "environment", "keyring_available": False}),
        patch("linear_cli.cli.Client") as MockClient,
    ):
        MockClient.return_value.viewer.return_value = mock_viewer
        result = invoke(runner, "auth", "status", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert "authenticated" in data["data"]


def test_auth_status_unauthenticated(runner):
    with patch("linear_cli.cli.get_api_key", return_value=None):
        result = invoke(runner, "auth", "status")
    assert result.exit_code == 0


# ===========================================================================
# auth logout
# ===========================================================================


def test_auth_logout(runner):
    with patch("linear_cli.cli.delete_api_key") as mock_delete:
        result = invoke(runner, "auth", "logout")
    assert result.exit_code == 0
    mock_delete.assert_called_once()


def test_auth_logout_json(runner):
    with patch("linear_cli.cli.delete_api_key"):
        result = invoke(runner, "auth", "logout", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["authenticated"] is False


# ===========================================================================
# cache status
# ===========================================================================


def test_cache_status(runner):
    mock_stats = {"cache_dir": "/tmp/linear", "entries": 5, "active": 4, "expired": 1, "size_bytes": 1024}
    with patch("linear_cli.cli.ResponseCache") as MockCache:
        MockCache.return_value.stats.return_value = mock_stats
        result = invoke(runner, "cache", "status")
    assert result.exit_code == 0


def test_cache_status_json(runner):
    mock_stats = {"cache_dir": "/tmp/linear", "entries": 5, "active": 4, "expired": 1, "size_bytes": 1024}
    with patch("linear_cli.cli.ResponseCache") as MockCache:
        MockCache.return_value.stats.return_value = mock_stats
        result = invoke(runner, "cache", "status", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["entries"] == 5
    assert data["data"]["cache_dir"] == "/tmp/linear"


# ===========================================================================
# cache clear
# ===========================================================================


def test_cache_clear(runner):
    with patch("linear_cli.cli.ResponseCache") as MockCache:
        MockCache.return_value.clear.return_value = 3
        result = invoke(runner, "cache", "clear")
    assert result.exit_code == 0


def test_cache_clear_json(runner):
    with patch("linear_cli.cli.ResponseCache") as MockCache:
        MockCache.return_value.clear.return_value = 7
        result = invoke(runner, "cache", "clear", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["cleared"] == 7


# ===========================================================================
# auth required checks (exit code 2)
# ===========================================================================


def test_issues_list_requires_auth(runner, unauthed):
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 2
    data = parse_json(result)
    assert data["error"]["code"] == "auth_required"


def test_projects_list_requires_auth(runner, unauthed):
    result = invoke(runner, "projects", "list", "--json")
    assert result.exit_code == 2


def test_teams_list_requires_auth(runner, unauthed):
    result = invoke(runner, "teams", "list", "--json")
    assert result.exit_code == 2
