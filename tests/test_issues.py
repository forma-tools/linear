"""Tests for the `issues` command group."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from linear_cli.cli import app
from linear_cli.client import LinearAPIError, RateLimitError


def invoke(runner, *args):
    return runner.invoke(app, list(args))


def parse_json(result):
    return json.loads(result.stdout)


# ===========================================================================
# issues list
# ===========================================================================


def test_issues_list_json_envelope(runner, authed):
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert "meta" in data
    assert isinstance(data["data"], list)
    assert data["meta"]["count"] == len(data["data"])


def test_issues_list_default(runner, authed):
    result = invoke(runner, "issues", "list")
    assert result.exit_code == 0


def test_issues_list_limit_passed(runner, authed, mock_client):
    invoke(runner, "issues", "list", "--limit", "5", "--json")
    mock_client.list_issues.assert_called_once()
    call_kwargs = mock_client.list_issues.call_args[1]
    assert call_kwargs["limit"] == 5


def test_issues_list_team_filter(runner, authed, mock_client):
    invoke(runner, "issues", "list", "--team", "team-abc", "--json")
    call_kwargs = mock_client.list_issues.call_args[1]
    assert call_kwargs["team_id"] == "team-abc"


def test_issues_list_state_filter(runner, authed, mock_client):
    invoke(runner, "issues", "list", "--state", "In Progress", "--json")
    call_kwargs = mock_client.list_issues.call_args[1]
    assert call_kwargs["state_name"] == "In Progress"


def test_issues_list_assignee_filter(runner, authed, mock_client):
    invoke(runner, "issues", "list", "--assignee", "user-1", "--json")
    call_kwargs = mock_client.list_issues.call_args[1]
    assert call_kwargs["assignee_id"] == "user-1"


def test_issues_list_priority_filter(runner, authed, mock_client):
    invoke(runner, "issues", "list", "--priority", "2", "--json")
    call_kwargs = mock_client.list_issues.call_args[1]
    assert call_kwargs["priority"] == 2


def test_issues_list_fields_filtering(runner, authed):
    result = invoke(runner, "issues", "list", "--fields", "id,title", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "title"}


def test_issues_list_help_has_examples(runner):
    result = invoke(runner, "issues", "list", "--help")
    assert "Examples" in result.stdout or "--json" in result.stdout


def test_issues_list_api_error_not_found(runner, authed, mock_client):
    mock_client.list_issues.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 3
    data = parse_json(result)
    assert data["error"]["code"] == "not_found"


def test_issues_list_api_error_auth(runner, authed, mock_client):
    mock_client.list_issues.side_effect = LinearAPIError("Unauthorized", 401)
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 5
    data = parse_json(result)
    assert data["error"]["code"] == "forbidden"


def test_issues_list_rate_limited(runner, authed, mock_client):
    mock_client.list_issues.side_effect = RateLimitError("Rate limited", 400)
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 6
    data = parse_json(result)
    assert data["error"]["code"] == "rate_limited"


def test_issues_list_validation_error(runner, authed, mock_client):
    mock_client.list_issues.side_effect = LinearAPIError("Validation", 422)
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 4
    data = parse_json(result)
    assert data["error"]["code"] == "validation"


def test_issues_list_conflict_error(runner, authed, mock_client):
    mock_client.list_issues.side_effect = LinearAPIError("Conflict", 409)
    result = invoke(runner, "issues", "list", "--json")
    assert result.exit_code == 7
    data = parse_json(result)
    assert data["error"]["code"] == "conflict"


def test_issues_list_archived_flag(runner, authed, mock_client):
    invoke(runner, "issues", "list", "--archived", "--json")
    call_kwargs = mock_client.list_issues.call_args[1]
    assert call_kwargs["include_archived"] is True


# ===========================================================================
# issues get
# ===========================================================================


def test_issues_get_json(runner, authed):
    result = invoke(runner, "issues", "get", "LIN-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert data["data"]["identifier"] == "LIN-1"


def test_issues_get_fields(runner, authed):
    result = invoke(runner, "issues", "get", "LIN-1", "--fields", "id,title", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert set(data["data"].keys()) == {"id", "title"}


def test_issues_get_not_found(runner, authed, mock_client):
    mock_client.get_issue.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "issues", "get", "LIN-999", "--json")
    assert result.exit_code == 3


def test_issues_get_passes_id(runner, authed, mock_client):
    invoke(runner, "issues", "get", "LIN-42", "--json")
    mock_client.get_issue.assert_called_once_with("LIN-42")


def test_issues_get_default_output(runner, authed):
    result = invoke(runner, "issues", "get", "LIN-1")
    assert result.exit_code == 0


# ===========================================================================
# issues create
# ===========================================================================


def test_issues_create_json(runner, authed):
    result = invoke(runner, "issues", "create", "Fix bug", "--team", "team-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_issues_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "issues", "create", "Fix bug", "--team", "team-abc", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    assert data["payload"]["title"] == "Fix bug"
    assert data["payload"]["teamId"] == "team-abc"
    mock_client.create_issue.assert_not_called()


def test_issues_create_dry_run_json(runner, authed, mock_client):
    result = invoke(runner, "issues", "create", "Fix bug", "--team", "team-abc", "--dry-run", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True


def test_issues_create_invalid_team_id(runner, authed):
    result = invoke(runner, "issues", "create", "Fix bug", "--team", "", "--json")
    # invalid id exits 4
    assert result.exit_code == 4


def test_issues_create_with_priority(runner, authed, mock_client):
    invoke(runner, "issues", "create", "Fix bug", "--team", "team-1", "--priority", "1", "--json")
    call_kwargs = mock_client.create_issue.call_args[1]
    assert call_kwargs["priority"] == 1


def test_issues_create_with_labels(runner, authed, mock_client):
    invoke(runner, "issues", "create", "Fix bug", "--team", "team-1", "--labels", "lbl-1,lbl-2", "--json")
    call_kwargs = mock_client.create_issue.call_args[1]
    assert call_kwargs["label_ids"] == ["lbl-1", "lbl-2"]


def test_issues_create_invalid_json_body(runner, authed):
    result = invoke(runner, "issues", "create", "Fix bug", "--team", "team-1", "--body", "notjson", "--json")
    assert result.exit_code == 4
    data = parse_json(result)
    assert data["error"]["code"] == "validation"


def test_issues_create_api_error(runner, authed, mock_client):
    mock_client.create_issue.side_effect = LinearAPIError("Forbidden", 403)
    result = invoke(runner, "issues", "create", "Fix bug", "--team", "team-1", "--json")
    assert result.exit_code == 5


# ===========================================================================
# issues update
# ===========================================================================


def test_issues_update_json(runner, authed):
    result = invoke(runner, "issues", "update", "LIN-1", "--title", "New title", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_issues_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "issues", "update", "LIN-1", "--title", "New", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.update_issue.assert_not_called()


def test_issues_update_invalid_json_body(runner, authed):
    result = invoke(runner, "issues", "update", "LIN-1", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_issues_update_passes_priority(runner, authed, mock_client):
    invoke(runner, "issues", "update", "LIN-1", "--priority", "3", "--json")
    call_kwargs = mock_client.update_issue.call_args[1]
    assert call_kwargs["priority"] == 3


# ===========================================================================
# issues delete
# ===========================================================================


def test_issues_delete_with_yes_flag(runner, authed):
    result = invoke(runner, "issues", "delete", "LIN-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_issues_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "issues", "delete", "LIN-1", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.delete_issue.assert_not_called()


def test_issues_delete_id_in_response(runner, authed):
    result = invoke(runner, "issues", "delete", "LIN-1", "--yes", "--json")
    data = parse_json(result)
    assert data["data"]["id"] == "LIN-1"


# ===========================================================================
# issues archive / unarchive
# ===========================================================================


def test_issues_archive_json(runner, authed):
    result = invoke(runner, "issues", "archive", "LIN-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_issues_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "issues", "archive", "LIN-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_issue.assert_not_called()


def test_issues_unarchive_json(runner, authed):
    result = invoke(runner, "issues", "unarchive", "LIN-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["unarchived"] is True


# ===========================================================================
# issues search
# ===========================================================================


def test_issues_search_json(runner, authed):
    result = invoke(runner, "issues", "search", "login bug", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert isinstance(data["data"], list)


def test_issues_search_fields(runner, authed):
    result = invoke(runner, "issues", "search", "login", "--fields", "id,title", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "title"}


def test_issues_search_passes_query(runner, authed, mock_client):
    invoke(runner, "issues", "search", "my query", "--json")
    mock_client.search_issues.assert_called_once()
    assert mock_client.search_issues.call_args[0][0] == "my query"


def test_issues_search_limit(runner, authed, mock_client):
    invoke(runner, "issues", "search", "test", "--limit", "10", "--json")
    call_kwargs = mock_client.search_issues.call_args[1]
    assert call_kwargs["limit"] == 10


def test_issues_search_help(runner):
    result = invoke(runner, "issues", "search", "--help")
    assert result.exit_code == 0


# ===========================================================================
# issues add-label / remove-label
# ===========================================================================


def test_issues_add_label_json(runner, authed):
    result = invoke(runner, "issues", "add-label", "LIN-1", "lbl-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["success"] is True


def test_issues_add_label_dry_run(runner, authed, mock_client):
    result = invoke(runner, "issues", "add-label", "LIN-1", "lbl-abc", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.add_issue_label.assert_not_called()


def test_issues_add_label_invalid_label_id(runner, authed):
    result = invoke(runner, "issues", "add-label", "LIN-1", "", "--json")
    assert result.exit_code == 4


def test_issues_remove_label_json(runner, authed):
    result = invoke(runner, "issues", "remove-label", "LIN-1", "lbl-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["success"] is True


def test_issues_remove_label_dry_run(runner, authed, mock_client):
    result = invoke(runner, "issues", "remove-label", "LIN-1", "lbl-abc", "--dry-run")
    assert result.exit_code == 0
    mock_client.remove_issue_label.assert_not_called()
