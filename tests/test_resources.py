"""Tests for all remaining resource command groups.

Covers: cycles, labels, users, comments, documents, initiatives, roadmaps,
webhooks, states, customers, attachments, notifications, templates, favorites,
releases, organization, views, milestones, relations, memberships,
project-updates, emojis, integrations, audit.
"""

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
# cycles
# ===========================================================================


def test_cycles_list_json(runner, authed):
    result = invoke(runner, "cycles", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert "meta" in data


def test_cycles_list_team_filter(runner, authed, mock_client):
    invoke(runner, "cycles", "list", "--team", "team-1", "--json")
    call_kwargs = mock_client.list_cycles.call_args[1]
    assert call_kwargs["team_id"] == "team-1"


def test_cycles_list_help_examples(runner):
    result = invoke(runner, "cycles", "list", "--help")
    assert result.exit_code == 0
    assert "--team" in result.stdout


def test_cycles_get_json(runner, authed):
    result = invoke(runner, "cycles", "get", "cycle-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_cycles_get_fields(runner, authed):
    result = invoke(runner, "cycles", "get", "cycle-1", "--fields", "id,number", "--json")
    data = parse_json(result)
    assert set(data["data"].keys()) == {"id", "number"}


def test_cycles_get_not_found(runner, authed, mock_client):
    mock_client.get_cycle.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "cycles", "get", "cycle-bad", "--json")
    assert result.exit_code == 3


def test_cycles_create_json(runner, authed):
    result = invoke(runner, "cycles", "create", "team-1", "2024-01-01", "2024-01-14", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_cycles_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "cycles", "create", "team-1", "2024-01-01", "2024-01-14", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_cycle.assert_not_called()


def test_cycles_create_invalid_json_body(runner, authed):
    result = invoke(runner, "cycles", "create", "team-1", "2024-01-01", "2024-01-14", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_cycles_update_json(runner, authed):
    result = invoke(runner, "cycles", "update", "cycle-1", "--name", "New Sprint", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_cycles_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "cycles", "update", "cycle-1", "--name", "X", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.update_cycle.assert_not_called()


def test_cycles_archive_json(runner, authed):
    result = invoke(runner, "cycles", "archive", "cycle-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_cycles_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "cycles", "archive", "cycle-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_cycle.assert_not_called()


# ===========================================================================
# labels
# ===========================================================================


def test_labels_list_json(runner, authed):
    result = invoke(runner, "labels", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_labels_list_team_filter(runner, authed, mock_client):
    invoke(runner, "labels", "list", "--team", "team-1", "--json")
    call_kwargs = mock_client.list_labels.call_args[1]
    assert call_kwargs["team_id"] == "team-1"


def test_labels_list_help(runner):
    result = invoke(runner, "labels", "list", "--help")
    assert result.exit_code == 0


def test_labels_get_json(runner, authed):
    result = invoke(runner, "labels", "get", "label-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_labels_get_not_found(runner, authed, mock_client):
    mock_client.get_label.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "labels", "get", "label-bad", "--json")
    assert result.exit_code == 3


def test_labels_create_json(runner, authed):
    result = invoke(runner, "labels", "create", "bug", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_labels_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "labels", "create", "bug", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_label.assert_not_called()


def test_labels_update_json(runner, authed):
    result = invoke(runner, "labels", "update", "label-1", "--name", "feature", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_labels_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "labels", "update", "label-1", "--name", "x", "--dry-run")
    assert result.exit_code == 0
    mock_client.update_label.assert_not_called()


def test_labels_delete_with_yes(runner, authed):
    result = invoke(runner, "labels", "delete", "label-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_labels_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "labels", "delete", "label-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.delete_label.assert_not_called()


# ===========================================================================
# users
# ===========================================================================


def test_users_list_json(runner, authed):
    result = invoke(runner, "users", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_users_list_fields(runner, authed):
    result = invoke(runner, "users", "list", "--fields", "id,email", "--json")
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "email"}


def test_users_list_help(runner):
    result = invoke(runner, "users", "list", "--help")
    assert result.exit_code == 0


def test_users_get_json(runner, authed):
    result = invoke(runner, "users", "get", "user-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_users_get_not_found(runner, authed, mock_client):
    mock_client.get_user.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "users", "get", "user-bad", "--json")
    assert result.exit_code == 3


def test_users_me_json(runner, authed):
    result = invoke(runner, "users", "me", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_users_me_fields(runner, authed):
    result = invoke(runner, "users", "me", "--fields", "id,email", "--json")
    data = parse_json(result)
    assert set(data["data"].keys()) == {"id", "email"}


def test_users_update_json(runner, authed):
    result = invoke(runner, "users", "update", "user-1", "--name", "Bob", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_users_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "users", "update", "user-1", "--name", "Bob", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.update_user.assert_not_called()


def test_users_suspend_json(runner, authed):
    result = invoke(runner, "users", "suspend", "user-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["suspended"] is True


def test_users_suspend_dry_run(runner, authed, mock_client):
    result = invoke(runner, "users", "suspend", "user-abc", "--dry-run")
    assert result.exit_code == 0
    mock_client.suspend_user.assert_not_called()


def test_users_suspend_invalid_id(runner, authed):
    result = invoke(runner, "users", "suspend", "", "--json")
    assert result.exit_code == 4


def test_users_unsuspend_json(runner, authed):
    result = invoke(runner, "users", "unsuspend", "user-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["unsuspended"] is True


def test_users_unsuspend_dry_run(runner, authed, mock_client):
    result = invoke(runner, "users", "unsuspend", "user-abc", "--dry-run")
    assert result.exit_code == 0
    mock_client.unsuspend_user.assert_not_called()


# ===========================================================================
# comments
# ===========================================================================


def test_comments_list_json(runner, authed):
    result = invoke(runner, "comments", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_comments_list_issue_filter(runner, authed, mock_client):
    invoke(runner, "comments", "list", "--issue", "issue-1", "--json")
    call_kwargs = mock_client.list_comments.call_args[1]
    assert call_kwargs["issue_id"] == "issue-1"


def test_comments_list_help(runner):
    result = invoke(runner, "comments", "list", "--help")
    assert result.exit_code == 0


def test_comments_create_json(runner, authed):
    result = invoke(runner, "comments", "create", "issue-1", "Great work!", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_comments_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "comments", "create", "issue-1", "Hello", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_comment.assert_not_called()


def test_comments_create_invalid_json_body(runner, authed):
    result = invoke(runner, "comments", "create", "issue-1", "Hello", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_comments_update_json(runner, authed):
    result = invoke(runner, "comments", "update", "comment-1", "New text", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_comments_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "comments", "update", "comment-1", "New text", "--dry-run")
    assert result.exit_code == 0
    mock_client.update_comment.assert_not_called()


def test_comments_delete_with_yes(runner, authed):
    result = invoke(runner, "comments", "delete", "comment-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_comments_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "comments", "delete", "comment-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.delete_comment.assert_not_called()


def test_comments_resolve_json(runner, authed):
    result = invoke(runner, "comments", "resolve", "comment-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_comments_resolve_dry_run(runner, authed, mock_client):
    result = invoke(runner, "comments", "resolve", "comment-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.resolve_comment.assert_not_called()


def test_comments_unresolve_json(runner, authed):
    result = invoke(runner, "comments", "unresolve", "comment-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


# ===========================================================================
# documents
# ===========================================================================


def test_documents_list_json(runner, authed):
    result = invoke(runner, "documents", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_documents_list_help(runner):
    result = invoke(runner, "documents", "list", "--help")
    assert result.exit_code == 0


def test_documents_get_json(runner, authed):
    result = invoke(runner, "documents", "get", "doc-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_documents_get_not_found(runner, authed, mock_client):
    mock_client.get_document.side_effect = LinearAPIError("Not found", 404)
    result = invoke(runner, "documents", "get", "doc-bad", "--json")
    assert result.exit_code == 3


def test_documents_create_json(runner, authed):
    result = invoke(runner, "documents", "create", "My Doc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_documents_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "documents", "create", "My Doc", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_document.assert_not_called()


def test_documents_update_json(runner, authed):
    result = invoke(runner, "documents", "update", "doc-1", "--title", "New Title", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_documents_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "documents", "update", "doc-1", "--title", "X", "--dry-run")
    assert result.exit_code == 0
    mock_client.update_document.assert_not_called()


def test_documents_delete_with_yes(runner, authed):
    result = invoke(runner, "documents", "delete", "doc-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_documents_search_json(runner, authed):
    result = invoke(runner, "documents", "search", "architecture", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_documents_search_passes_query(runner, authed, mock_client):
    invoke(runner, "documents", "search", "design doc", "--json")
    assert mock_client.search_documents.call_args[0][0] == "design doc"


# ===========================================================================
# initiatives
# ===========================================================================


def test_initiatives_list_json(runner, authed):
    result = invoke(runner, "initiatives", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_initiatives_list_help(runner):
    result = invoke(runner, "initiatives", "list", "--help")
    assert result.exit_code == 0


def test_initiatives_get_json(runner, authed):
    result = invoke(runner, "initiatives", "get", "init-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_initiatives_create_json(runner, authed):
    result = invoke(runner, "initiatives", "create", "Big Initiative", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_initiatives_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "initiatives", "create", "Big Initiative", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_initiative.assert_not_called()


def test_initiatives_update_json(runner, authed):
    result = invoke(runner, "initiatives", "update", "init-1", "--name", "New Name", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_initiatives_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "initiatives", "update", "init-1", "--name", "X", "--dry-run")
    assert result.exit_code == 0
    mock_client.update_initiative.assert_not_called()


def test_initiatives_delete_with_yes(runner, authed):
    result = invoke(runner, "initiatives", "delete", "init-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_initiatives_archive_json(runner, authed):
    result = invoke(runner, "initiatives", "archive", "init-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_initiatives_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "initiatives", "archive", "init-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_initiative.assert_not_called()


def test_initiatives_unarchive_json(runner, authed):
    result = invoke(runner, "initiatives", "unarchive", "init-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["unarchived"] is True


# ===========================================================================
# roadmaps
# ===========================================================================


def test_roadmaps_list_json(runner, authed):
    result = invoke(runner, "roadmaps", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_roadmaps_list_help(runner):
    result = invoke(runner, "roadmaps", "list", "--help")
    assert result.exit_code == 0


def test_roadmaps_get_json(runner, authed):
    result = invoke(runner, "roadmaps", "get", "road-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_roadmaps_create_json(runner, authed):
    result = invoke(runner, "roadmaps", "create", "My Roadmap", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_roadmaps_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "roadmaps", "create", "My Roadmap", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_roadmap.assert_not_called()


def test_roadmaps_update_json(runner, authed):
    result = invoke(runner, "roadmaps", "update", "road-1", "--name", "Updated", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_roadmaps_delete_with_yes(runner, authed):
    result = invoke(runner, "roadmaps", "delete", "road-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_roadmaps_archive_json(runner, authed):
    result = invoke(runner, "roadmaps", "archive", "road-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_roadmaps_unarchive_json(runner, authed):
    result = invoke(runner, "roadmaps", "unarchive", "road-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["unarchived"] is True


# ===========================================================================
# webhooks
# ===========================================================================


def test_webhooks_list_json(runner, authed):
    result = invoke(runner, "webhooks", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_webhooks_list_help(runner):
    result = invoke(runner, "webhooks", "list", "--help")
    assert result.exit_code == 0


def test_webhooks_get_json(runner, authed):
    result = invoke(runner, "webhooks", "get", "hook-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_webhooks_create_json(runner, authed):
    result = invoke(runner, "webhooks", "create", "https://example.com/hook", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_webhooks_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "webhooks", "create", "https://example.com/hook", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_webhook.assert_not_called()


def test_webhooks_create_with_resource_types(runner, authed, mock_client):
    invoke(runner, "webhooks", "create", "https://ex.com/hook", "--resource-types", "Issue,Project", "--json")
    call_kwargs = mock_client.create_webhook.call_args[1]
    assert call_kwargs["resource_types"] == ["Issue", "Project"]


def test_webhooks_update_json(runner, authed):
    result = invoke(runner, "webhooks", "update", "hook-1", "--label", "New Label", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_webhooks_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "webhooks", "update", "hook-1", "--label", "X", "--dry-run")
    assert result.exit_code == 0
    mock_client.update_webhook.assert_not_called()


def test_webhooks_delete_with_yes(runner, authed):
    result = invoke(runner, "webhooks", "delete", "hook-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_webhooks_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "webhooks", "delete", "hook-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.delete_webhook.assert_not_called()


# ===========================================================================
# states
# ===========================================================================


def test_states_list_json(runner, authed):
    result = invoke(runner, "states", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_states_list_team_filter(runner, authed, mock_client):
    invoke(runner, "states", "list", "--team", "team-1", "--json")
    call_kwargs = mock_client.list_states.call_args[1]
    assert call_kwargs["team_id"] == "team-1"


def test_states_list_help(runner):
    result = invoke(runner, "states", "list", "--help")
    assert result.exit_code == 0


def test_states_create_json(runner, authed):
    result = invoke(runner, "states", "create", "Doing", "--team", "team-1", "--type", "started", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_states_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "states", "create", "Doing", "--team", "team-1", "--type", "started", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_state.assert_not_called()


def test_states_update_json(runner, authed):
    result = invoke(runner, "states", "update", "state-1", "--name", "In Review", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_states_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "states", "update", "state-1", "--name", "X", "--dry-run")
    assert result.exit_code == 0
    mock_client.update_state.assert_not_called()


def test_states_archive_json(runner, authed):
    result = invoke(runner, "states", "archive", "state-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_states_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "states", "archive", "state-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_state.assert_not_called()


# ===========================================================================
# customers
# ===========================================================================


def test_customers_list_json(runner, authed):
    result = invoke(runner, "customers", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_customers_list_help(runner):
    result = invoke(runner, "customers", "list", "--help")
    assert result.exit_code == 0


def test_customers_get_json(runner, authed):
    result = invoke(runner, "customers", "get", "cust-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_customers_create_json(runner, authed):
    result = invoke(runner, "customers", "create", "Acme Corp", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_customers_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "customers", "create", "Acme Corp", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_customer.assert_not_called()


def test_customers_create_with_domains(runner, authed, mock_client):
    invoke(runner, "customers", "create", "Acme", "--domains", "acme.com,acme.io", "--json")
    call_kwargs = mock_client.create_customer.call_args[1]
    assert call_kwargs["domains"] == ["acme.com", "acme.io"]


def test_customers_update_json(runner, authed):
    result = invoke(runner, "customers", "update", "cust-1", "--name", "Acme LLC", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_customers_delete_with_yes(runner, authed):
    result = invoke(runner, "customers", "delete", "cust-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


# ===========================================================================
# attachments
# ===========================================================================


def test_attachments_list_json(runner, authed):
    result = invoke(runner, "attachments", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_attachments_list_help(runner):
    result = invoke(runner, "attachments", "list", "--help")
    assert result.exit_code == 0


def test_attachments_get_json(runner, authed):
    result = invoke(runner, "attachments", "get", "attach-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_attachments_create_json(runner, authed):
    result = invoke(runner, "attachments", "create", "issue-1", "https://example.com/file.pdf", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_attachments_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "attachments", "create", "issue-1", "https://example.com/file.pdf", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_attachment.assert_not_called()


def test_attachments_delete_with_yes(runner, authed):
    result = invoke(runner, "attachments", "delete", "attach-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_attachments_link_url_json(runner, authed):
    result = invoke(runner, "attachments", "link-url", "issue-1", "https://github.com/org/repo/pull/42", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_attachments_link_url_dry_run(runner, authed, mock_client):
    result = invoke(runner, "attachments", "link-url", "issue-1", "https://github.com/pr/42", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.link_url_to_issue.assert_not_called()


# ===========================================================================
# notifications
# ===========================================================================


def test_notifications_list_json(runner, authed):
    result = invoke(runner, "notifications", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_notifications_list_help(runner):
    result = invoke(runner, "notifications", "list", "--help")
    assert result.exit_code == 0


def test_notifications_get_json(runner, authed):
    result = invoke(runner, "notifications", "get", "notif-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_notifications_archive_json(runner, authed):
    result = invoke(runner, "notifications", "archive", "notif-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_notifications_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "notifications", "archive", "notif-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_notification.assert_not_called()


def test_notifications_unarchive_json(runner, authed):
    result = invoke(runner, "notifications", "unarchive", "notif-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["unarchived"] is True


def test_notifications_mark_read_json(runner, authed):
    result = invoke(runner, "notifications", "mark-read", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["success"] is True


def test_notifications_mark_read_dry_run(runner, authed, mock_client):
    result = invoke(runner, "notifications", "mark-read", "--dry-run")
    assert result.exit_code == 0
    mock_client.mark_all_notifications_read.assert_not_called()


# ===========================================================================
# templates
# ===========================================================================


def test_templates_list_json(runner, authed):
    result = invoke(runner, "templates", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_templates_list_help(runner):
    result = invoke(runner, "templates", "list", "--help")
    assert result.exit_code == 0


def test_templates_get_json(runner, authed):
    result = invoke(runner, "templates", "get", "tmpl-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_templates_create_json(runner, authed):
    result = invoke(
        runner,
        "templates", "create", "Bug Report",
        "--type", "issue",
        "--data", '{"title": "Bug: "}',
        "--json",
    )
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_templates_create_invalid_data_json(runner, authed):
    result = invoke(
        runner,
        "templates", "create", "Bug Report",
        "--type", "issue",
        "--data", "notjson",
        "--json",
    )
    assert result.exit_code == 4


def test_templates_create_dry_run(runner, authed, mock_client):
    result = invoke(
        runner,
        "templates", "create", "Bug Report",
        "--type", "issue",
        "--data", '{"title": "Bug: "}',
        "--dry-run",
    )
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_template.assert_not_called()


def test_templates_update_json(runner, authed):
    result = invoke(runner, "templates", "update", "tmpl-1", "--name", "Updated", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_templates_delete_with_yes(runner, authed):
    result = invoke(runner, "templates", "delete", "tmpl-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


# ===========================================================================
# favorites
# ===========================================================================


def test_favorites_list_json(runner, authed):
    result = invoke(runner, "favorites", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data
    assert data["meta"]["count"] == len(data["data"])


def test_favorites_list_help(runner):
    result = invoke(runner, "favorites", "list", "--help")
    assert result.exit_code == 0


def test_favorites_create_json(runner, authed):
    result = invoke(runner, "favorites", "create", '{"issueId": "issue-1"}', "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_favorites_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "favorites", "create", '{"issueId": "issue-1"}', "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_favorite.assert_not_called()


def test_favorites_create_invalid_json(runner, authed):
    result = invoke(runner, "favorites", "create", "notjson", "--json")
    assert result.exit_code == 4


def test_favorites_delete_with_yes(runner, authed):
    result = invoke(runner, "favorites", "delete", "fav-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_favorites_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "favorites", "delete", "fav-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.delete_favorite.assert_not_called()


# ===========================================================================
# releases
# ===========================================================================


def test_releases_list_json(runner, authed):
    result = invoke(runner, "releases", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_releases_list_help(runner):
    result = invoke(runner, "releases", "list", "--help")
    assert result.exit_code == 0


def test_releases_create_json(runner, authed):
    result = invoke(runner, "releases", "create", "v1.0", "--body", '{"pipelineId": "pipe-1"}', "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_releases_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "releases", "create", "v1.0", "--body", '{"pipelineId": "p"}', "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_release.assert_not_called()


def test_releases_create_invalid_json_body(runner, authed):
    result = invoke(runner, "releases", "create", "v1.0", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_releases_update_json(runner, authed):
    result = invoke(runner, "releases", "update", "rel-1", "--body", '{"name": "v1.1"}', "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_releases_update_invalid_json(runner, authed):
    result = invoke(runner, "releases", "update", "rel-1", "--body", "notjson", "--json")
    assert result.exit_code == 4


def test_releases_delete_with_yes(runner, authed):
    result = invoke(runner, "releases", "delete", "rel-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_releases_archive_json(runner, authed):
    result = invoke(runner, "releases", "archive", "rel-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["archived"] is True


def test_releases_archive_dry_run(runner, authed, mock_client):
    result = invoke(runner, "releases", "archive", "rel-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.archive_release.assert_not_called()


# ===========================================================================
# organization
# ===========================================================================


def test_organization_get_json(runner, authed):
    result = invoke(runner, "organization", "get", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_organization_get_fields(runner, authed):
    result = invoke(runner, "organization", "get", "--fields", "id,name", "--json")
    data = parse_json(result)
    assert set(data["data"].keys()) == {"id", "name"}


def test_organization_get_help(runner):
    result = invoke(runner, "organization", "get", "--help")
    assert result.exit_code == 0


def test_organization_update_json(runner, authed):
    result = invoke(runner, "organization", "update", '{"name": "Acme Inc"}', "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_organization_update_dry_run(runner, authed, mock_client):
    result = invoke(runner, "organization", "update", '{"name": "Acme"}', "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.update_organization.assert_not_called()


def test_organization_update_invalid_json(runner, authed):
    result = invoke(runner, "organization", "update", "notjson", "--json")
    assert result.exit_code == 4


# ===========================================================================
# views
# ===========================================================================


def test_views_list_json(runner, authed):
    result = invoke(runner, "views", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_views_list_help(runner):
    result = invoke(runner, "views", "list", "--help")
    assert result.exit_code == 0


def test_views_get_json(runner, authed):
    result = invoke(runner, "views", "get", "view-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_views_create_json(runner, authed):
    result = invoke(runner, "views", "create", "My View", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_views_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "views", "create", "My View", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_view.assert_not_called()


def test_views_update_json(runner, authed):
    result = invoke(runner, "views", "update", "view-1", "--name", "Updated View", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_views_delete_with_yes(runner, authed):
    result = invoke(runner, "views", "delete", "view-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


# ===========================================================================
# milestones
# ===========================================================================


def test_milestones_list_json(runner, authed):
    result = invoke(runner, "milestones", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_milestones_list_project_filter(runner, authed, mock_client):
    invoke(runner, "milestones", "list", "--project", "proj-1", "--json")
    call_kwargs = mock_client.list_milestones.call_args[1]
    assert call_kwargs["project_id"] == "proj-1"


def test_milestones_list_help(runner):
    result = invoke(runner, "milestones", "list", "--help")
    assert result.exit_code == 0


def test_milestones_create_json(runner, authed):
    result = invoke(runner, "milestones", "create", "M1", "--project", "proj-1", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_milestones_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "milestones", "create", "M1", "--project", "proj-1", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_milestone.assert_not_called()


def test_milestones_update_json(runner, authed):
    result = invoke(runner, "milestones", "update", "ms-1", "--name", "M2", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_milestones_delete_with_yes(runner, authed):
    result = invoke(runner, "milestones", "delete", "ms-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


# ===========================================================================
# relations
# ===========================================================================


def test_relations_list_json(runner, authed):
    result = invoke(runner, "relations", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_relations_list_help(runner):
    result = invoke(runner, "relations", "list", "--help")
    assert result.exit_code == 0


def test_relations_create_json(runner, authed):
    result = invoke(runner, "relations", "create", "issue-1", "issue-2", "blocks", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_relations_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "relations", "create", "issue-1", "issue-2", "blocks", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_issue_relation.assert_not_called()


def test_relations_create_passes_type(runner, authed, mock_client):
    invoke(runner, "relations", "create", "issue-1", "issue-2", "duplicate", "--json")
    call_kwargs = mock_client.create_issue_relation.call_args[1]
    assert call_kwargs["type"] == "duplicate"


def test_relations_delete_with_yes(runner, authed):
    result = invoke(runner, "relations", "delete", "rel-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_relations_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "relations", "delete", "rel-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.delete_issue_relation.assert_not_called()


# ===========================================================================
# memberships
# ===========================================================================


def test_memberships_list_json(runner, authed):
    result = invoke(runner, "memberships", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_memberships_list_team_filter(runner, authed, mock_client):
    invoke(runner, "memberships", "list", "--team", "team-1", "--json")
    call_kwargs = mock_client.list_team_memberships.call_args[1]
    assert call_kwargs["team_id"] == "team-1"


def test_memberships_list_help(runner):
    result = invoke(runner, "memberships", "list", "--help")
    assert result.exit_code == 0


def test_memberships_create_json(runner, authed):
    result = invoke(runner, "memberships", "create", "team-abc", "user-abc", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_memberships_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "memberships", "create", "team-abc", "user-abc", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_team_membership.assert_not_called()


def test_memberships_create_invalid_team_id(runner, authed):
    result = invoke(runner, "memberships", "create", "", "user-abc", "--json")
    assert result.exit_code == 4


def test_memberships_delete_with_yes(runner, authed):
    result = invoke(runner, "memberships", "delete", "mem-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


# ===========================================================================
# project-updates
# ===========================================================================


def test_project_updates_list_json(runner, authed):
    result = invoke(runner, "project-updates", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_project_updates_list_project_filter(runner, authed, mock_client):
    invoke(runner, "project-updates", "list", "--project", "proj-1", "--json")
    call_kwargs = mock_client.list_project_updates.call_args[1]
    assert call_kwargs["project_id"] == "proj-1"


def test_project_updates_list_help(runner):
    result = invoke(runner, "project-updates", "list", "--help")
    assert result.exit_code == 0


def test_project_updates_create_json(runner, authed):
    result = invoke(runner, "project-updates", "create", "proj-1", "On track this week", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_project_updates_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "project-updates", "create", "proj-1", "Update text", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_project_update.assert_not_called()


def test_project_updates_create_with_health(runner, authed, mock_client):
    invoke(runner, "project-updates", "create", "proj-1", "Update text", "--health", "onTrack", "--json")
    call_kwargs = mock_client.create_project_update.call_args[1]
    assert call_kwargs["health"] == "onTrack"


def test_project_updates_delete_with_yes(runner, authed):
    result = invoke(runner, "project-updates", "delete", "upd-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


# ===========================================================================
# emojis
# ===========================================================================


def test_emojis_list_json(runner, authed):
    result = invoke(runner, "emojis", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_emojis_list_help(runner):
    result = invoke(runner, "emojis", "list", "--help")
    assert result.exit_code == 0


def test_emojis_create_json(runner, authed):
    result = invoke(runner, "emojis", "create", "fire", "https://example.com/fire.png", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_emojis_create_dry_run(runner, authed, mock_client):
    result = invoke(runner, "emojis", "create", "fire", "https://example.com/fire.png", "--dry-run")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["dry_run"] is True
    mock_client.create_emoji.assert_not_called()


def test_emojis_create_passes_name_url(runner, authed, mock_client):
    invoke(runner, "emojis", "create", "rocket", "https://cdn.example.com/rocket.png", "--json")
    call_kwargs = mock_client.create_emoji.call_args[1]
    assert call_kwargs["name"] == "rocket"
    assert call_kwargs["url"] == "https://cdn.example.com/rocket.png"


def test_emojis_delete_with_yes(runner, authed):
    result = invoke(runner, "emojis", "delete", "emoji-1", "--yes", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert data["data"]["deleted"] is True


def test_emojis_delete_dry_run(runner, authed, mock_client):
    result = invoke(runner, "emojis", "delete", "emoji-1", "--dry-run")
    assert result.exit_code == 0
    mock_client.delete_emoji.assert_not_called()


# ===========================================================================
# integrations
# ===========================================================================


def test_integrations_list_json(runner, authed):
    result = invoke(runner, "integrations", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_integrations_list_fields(runner, authed):
    result = invoke(runner, "integrations", "list", "--fields", "id,service", "--json")
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "service"}


def test_integrations_list_help(runner):
    result = invoke(runner, "integrations", "list", "--help")
    assert result.exit_code == 0


def test_integrations_list_api_error(runner, authed, mock_client):
    mock_client.list_integrations.side_effect = LinearAPIError("Forbidden", 403)
    result = invoke(runner, "integrations", "list", "--json")
    assert result.exit_code == 5


# ===========================================================================
# audit
# ===========================================================================


def test_audit_list_json(runner, authed):
    result = invoke(runner, "audit", "list", "--json")
    assert result.exit_code == 0
    data = parse_json(result)
    assert "data" in data


def test_audit_list_fields(runner, authed):
    result = invoke(runner, "audit", "list", "--fields", "id,type", "--json")
    data = parse_json(result)
    for item in data["data"]:
        assert set(item.keys()) == {"id", "type"}


def test_audit_list_help(runner):
    result = invoke(runner, "audit", "list", "--help")
    assert result.exit_code == 0


def test_audit_list_limit(runner, authed, mock_client):
    invoke(runner, "audit", "list", "--limit", "10", "--json")
    call_kwargs = mock_client.list_audit_entries.call_args[1]
    assert call_kwargs["limit"] == 10


def test_audit_list_api_error(runner, authed, mock_client):
    mock_client.list_audit_entries.side_effect = LinearAPIError("Forbidden", 403)
    result = invoke(runner, "audit", "list", "--json")
    assert result.exit_code == 5
