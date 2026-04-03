"""Tests for the `projects` command group."""

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
# projects list
# ===========================================================================


def test_projects_list_json_envelope(runner, authed):
    result = invoke(runner, "projects", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert "meta" in data
    assert isinstance(data["data"], list)


def test_projects_list_default(runner, authed):
    result = invoke(runner, "projects", "list")
    assert result.exit_code == 0


def test_projects_list_limit(runner, authed, mock_client):
    invoke(runner, "projects", "list", "--limit", "5", "--json")
    call_kwargs = mock_client.list_projects.call_args[1]
    assert call_kwargs["limit"] == 5


def test_projects_list_team_filter(runner, authed, mock_client):
    invoke(runner, "projects", "list", "--team", "team-abc", "--json")
    call_kwargs = mock_client.list_projects.call_args[1]
    assert call_kwargs["team_id"] == "team-abc"


def test_projects_list_state_filter(runner, authed, mock_client):
    invoke(runner, "projects", "list", "--state", "backlog", "--json")
    call_kwargs = mock_client.list_projects.call_args[1]
    assert call_kwargs["state"] == "backlog"


def test_projects_list_fields(runner, authed):
    result = invoke(runner, "projects", "list", "--fields", "id,name", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "name"}


def test_projects_list_api_error(runner, authed, mock_client):
    mock_client.list_projects.side_effect = LinearAPIError("Unauthorized", 401)
    result = invoke(runner, "projects", "list", "--json")
    assert result.exit_code == 5


def test_projects_list_archived(runner, authed, mock_client):
    invoke(runner, "projects", "list", "--archived", "--json")
    call_kwargs = mock_client.list_projects.call_args[1]
    assert call_kwargs["include_archived"] is True


def test_projects_list_help(runner):
    result = invoke(runner, "projects", "list", "--help")
    assert result.exit_code == 0


# ===========================================================================
# projects get
# ===========================================================================


def test_projects_get_json(runner, authed):
    result = invoke(runner, "projects", "get", "proj-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_projects_get_fields(runner, authed):
    result = invoke(runner, "projects", "get", "proj-abc", "--fields", "id,name", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert set(data["data"].keys()) == {"id", "name"}


def test_projects_get_not_found(runner, authed, mock_client):
    mock_client.get_project.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "projects", "get", "proj-bad", "--json")
    assert result.exit_code == 3
    data = parse_json(result)
    assert data["error"]["code"] == "not_found"


def test_projects_get_passes_id(runner, authed, mock_client):
    invoke(runner, "projects", "get", "proj-xyz", "--json")
    mock_client.get_project.assert_called_once_with("proj-xyz")


def test_projects_get_default_output(runner, authed):
    result = invoke(runner, "projects", "get", "proj-abc")
    assert result.exit_code == 0


# ===========================================================================
# projects create
# ===========================================================================


def test_projects_create_json(runner, authed):
    result = invoke(runner, "projects", "create", "My Project", "--teams", "team-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_projects_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "projects", "create", "My Project", "--teams", "team-1", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    assert data["payload"]["name"] == "My Project"
    mock_client.create_project.assert_not_called()


def test_projects_create_invalid_json_body(runner, authed):
    result = invoke(runner, "projects", "create", "My Project", "--teams", "team-1", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_projects_create_multiple_teams(runner, authed, mock_client):
    invoke(runner, "projects", "create", "My Project", "--teams", "team-1,team-2", "--json")
    call_kwargs = mock_client.create_project.call_args[1]
    assert call_kwargs["team_ids"] == ["team-1", "team-2"]


def test_projects_create_with_description(runner, authed, mock_client):
    invoke(runner, "projects", "create", "My Project", "--teams", "team-1", "--description", "Desc", "--json")
    call_kwargs = mock_client.create_project.call_args[1]
    assert call_kwargs["description"] == "Desc"


def test_projects_create_api_error(runner, authed, mock_client):
    mock_client.create_project.side_effect = LinearAPIError("Server error", 500)
    result = invoke(runner, "projects", "create", "My Project", "--teams", "team-1", "--json")
    assert result.exit_code == 1


# ===========================================================================
# projects update
# ===========================================================================


def test_projects_update_json(runner, authed):
    result = invoke(runner, "projects", "update", "proj-abc", "--name", "New Name", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_projects_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "projects", "update", "proj-abc", "--name", "New Name", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.update_project.assert_not_called()


def test_projects_update_invalid_json_body(runner, authed):
    result = invoke(runner, "projects", "update", "proj-abc", "--body", "notjson", "--json")
    assert result.exit_code == 4


# ===========================================================================
# projects delete
# ===========================================================================


def test_projects_delete_with_yes(runner, authed):
    result = invoke(runner, "projects", "delete", "proj-abc", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_projects_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "projects", "delete", "proj-abc", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.delete_project.assert_not_called()


# ===========================================================================
# projects archive / unarchive
# ===========================================================================


def test_projects_archive_json(runner, authed):
    result = invoke(runner, "projects", "archive", "proj-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_projects_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "projects", "archive", "proj-abc", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_project.assert_not_called()


def test_projects_unarchive_json(runner, authed):
    result = invoke(runner, "projects", "unarchive", "proj-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["unarchived"] is True


# ===========================================================================
# projects search
# ===========================================================================


def test_projects_search_json(runner, authed):
    result = invoke(runner, "projects", "search", "sprint", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_projects_search_fields(runner, authed):
    result = invoke(runner, "projects", "search", "sprint", "--fields", "id,name", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "name"}


def test_projects_search_passes_query(runner, authed, mock_client):
    invoke(runner, "projects", "search", "my project", "--json")
    mock_client.search_projects.assert_called_once()
    assert mock_client.search_projects.call_args[0][0] == "my project"
