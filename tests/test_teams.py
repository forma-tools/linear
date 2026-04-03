"""Tests for the `teams` command group."""

from __future__ import annotations

import json

import pytest

from linear_cli.cli import app
from linear_cli.client import LinearAPIError


def invoke(runner, *args):
    return runner.invoke(app, list(args))


def parse_json(result):
    return json.loads(result.stdout)


# ===========================================================================
# teams list
# ===========================================================================


def test_teams_list_json_envelope(runner, authed):
    result = invoke(runner, "teams", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert "meta" in data
    assert isinstance(data["data"], list)


def test_teams_list_default(runner, authed):
    result = invoke(runner, "teams", "list")
    assert result.exit_code == 0


def test_teams_list_limit(runner, authed, mock_client):
    invoke(runner, "teams", "list", "--limit", "5", "--json")
    call_kwargs = mock_client.list_teams.call_args[1]
    assert call_kwargs["limit"] == 5


def test_teams_list_fields(runner, authed):
    result = invoke(runner, "teams", "list", "--fields", "id,key", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "key"}


def test_teams_list_help_has_examples(runner):
    result = invoke(runner, "teams", "list", "--help")
    assert result.exit_code == 0
    assert "--json" in result.stdout


def test_teams_list_api_error(runner, authed, mock_client):
    mock_client.list_teams.side_effect = LinearAPIError("Unauthorized", 401)
    result = invoke(runner, "teams", "list", "--json")
    assert result.exit_code == 5


def test_teams_list_archived(runner, authed, mock_client):
    invoke(runner, "teams", "list", "--archived", "--json")
    call_kwargs = mock_client.list_teams.call_args[1]
    assert call_kwargs["include_archived"] is True


# ===========================================================================
# teams get
# ===========================================================================


def test_teams_get_json(runner, authed):
    result = invoke(runner, "teams", "get", "team-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_teams_get_fields(runner, authed):
    result = invoke(runner, "teams", "get", "team-abc", "--fields", "id,name,key", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert set(data["data"].keys()) == {"id", "name", "key"}


def test_teams_get_not_found(runner, authed, mock_client):
    mock_client.get_team.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "teams", "get", "team-bad", "--json")
    assert result.exit_code == 3
    data = parse_json(result)
    assert data["error"]["code"] == "not_found"


def test_teams_get_passes_id(runner, authed, mock_client):
    invoke(runner, "teams", "get", "team-xyz", "--json")
    mock_client.get_team.assert_called_once_with("team-xyz")


def test_teams_get_default_output(runner, authed):
    result = invoke(runner, "teams", "get", "team-abc")
    assert result.exit_code == 0


# ===========================================================================
# teams create
# ===========================================================================


def test_teams_create_json(runner, authed):
    result = invoke(runner, "teams", "create", "My Team", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_teams_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "teams", "create", "My Team", "--key", "MT", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    assert data["payload"]["name"] == "My Team"
    mock_client.create_team.assert_not_called()


def test_teams_create_with_key(runner, authed, mock_client):
    invoke(runner, "teams", "create", "My Team", "--key", "MT", "--json")
    call_kwargs = mock_client.create_team.call_args[1]
    assert call_kwargs["key"] == "MT"


def test_teams_create_with_description(runner, authed, mock_client):
    invoke(runner, "teams", "create", "My Team", "--description", "Eng team", "--json")
    call_kwargs = mock_client.create_team.call_args[1]
    assert call_kwargs["description"] == "Eng team"


def test_teams_create_private(runner, authed, mock_client):
    invoke(runner, "teams", "create", "Secret Team", "--private", "--json")
    call_kwargs = mock_client.create_team.call_args[1]
    assert call_kwargs["private"] is True


def test_teams_create_invalid_json_body(runner, authed):
    result = invoke(runner, "teams", "create", "My Team", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_teams_create_api_error(runner, authed, mock_client):
    mock_client.create_team.side_effect = LinearAPIError("Server error", 500)
    result = invoke(runner, "teams", "create", "My Team", "--json")
    assert result.exit_code == 1


# ===========================================================================
# teams update
# ===========================================================================


def test_teams_update_json(runner, authed):
    result = invoke(runner, "teams", "update", "team-abc", "--name", "New Name", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_teams_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "teams", "update", "team-abc", "--name", "New Name", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.update_team.assert_not_called()


def test_teams_update_passes_id(runner, authed, mock_client):
    invoke(runner, "teams", "update", "team-xyz", "--name", "X", "--json")
    call_args = mock_client.update_team.call_args
    assert call_args[0][0] == "team-xyz"


def test_teams_update_invalid_json_body(runner, authed):
    result = invoke(runner, "teams", "update", "team-abc", "--body", "notjson", "--json")
    assert result.exit_code == 4


# ===========================================================================
# teams delete
# ===========================================================================


def test_teams_delete_with_yes(runner, authed):
    result = invoke(runner, "teams", "delete", "team-abc", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True
    assert data["data"]["id"] == "team-abc"


def test_teams_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "teams", "delete", "team-abc", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.delete_team.assert_not_called()


def test_teams_delete_not_found(runner, authed, mock_client):
    mock_client.delete_team.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "teams", "delete", "team-bad", "--yes", "--json")
    assert result.exit_code == 3
