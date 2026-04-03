"""Shared fixtures for Linear CLI tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    """Typer CliRunner with mix_stderr disabled so stdout is clean."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Isolate cache per-test so caching does not bleed between test invocations.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Redirect LINEAR_CACHE_DIR to a per-test temp directory."""
    monkeypatch.setenv("LINEAR_CACHE_DIR", str(tmp_path / "linear_cache"))


# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------


def make_issue(**kwargs) -> dict:
    defaults = {
        "id": "issue-abc123",
        "identifier": "LIN-1",
        "title": "Fix login bug",
        "description": "Users cannot log in.",
        "priority": 2,
        "priorityLabel": "Medium",
        "state": {"id": "state-1", "name": "In Progress", "type": "started", "color": "#ff0"},
        "assignee": {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        "team": {"id": "team-1", "name": "Engineering", "key": "ENG"},
        "project": {"id": "proj-1", "name": "Q4 Sprint"},
        "cycle": None,
        "labels": {"nodes": []},
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "completedAt": None,
        "canceledAt": None,
        "dueDate": None,
        "url": "https://linear.app/team/issue/LIN-1",
        "branchName": "eng-1-fix-login-bug",
        "parent": None,
    }
    defaults.update(kwargs)
    return defaults


def make_project(**kwargs) -> dict:
    defaults = {
        "id": "proj-abc123",
        "name": "Q4 Sprint",
        "slugId": "q4-sprint",
        "description": "Quarter 4 sprint project",
        "state": "started",
        "priority": 1,
        "progress": 0.5,
        "scope": 10,
        "startDate": "2024-01-01",
        "targetDate": "2024-03-31",
        "lead": {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        "status": {"id": "status-1", "name": "On Track", "color": "#green"},
        "teams": {"nodes": [{"id": "team-1", "name": "Engineering", "key": "ENG"}]},
        "members": {"nodes": []},
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "completedAt": None,
        "canceledAt": None,
        "archivedAt": None,
        "url": "https://linear.app/team/project/q4-sprint",
    }
    defaults.update(kwargs)
    return defaults


def make_team(**kwargs) -> dict:
    defaults = {
        "id": "team-abc123",
        "name": "Engineering",
        "key": "ENG",
        "description": "The engineering team",
        "issueCount": 42,
        "private": False,
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
    }
    defaults.update(kwargs)
    return defaults


def make_user(**kwargs) -> dict:
    defaults = {
        "id": "user-abc123",
        "name": "Alice Smith",
        "displayName": "Alice",
        "email": "alice@example.com",
        "active": True,
        "admin": False,
        "avatarUrl": None,
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "organization": {"id": "org-1", "name": "Acme Inc", "urlKey": "acme"},
    }
    defaults.update(kwargs)
    return defaults


def make_cycle(**kwargs) -> dict:
    defaults = {
        "id": "cycle-abc123",
        "number": 5,
        "name": "Sprint 5",
        "startsAt": "2024-01-01T00:00:00Z",
        "endsAt": "2024-01-14T00:00:00Z",
        "team": {"id": "team-1", "key": "ENG"},
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
    }
    defaults.update(kwargs)
    return defaults


def make_label(**kwargs) -> dict:
    defaults = {
        "id": "label-abc123",
        "name": "bug",
        "color": "#ff0000",
        "description": "Something is broken",
        "team": {"id": "team-1", "key": "ENG"},
    }
    defaults.update(kwargs)
    return defaults


def make_comment(**kwargs) -> dict:
    defaults = {
        "id": "comment-abc123",
        "body": "This is a comment.",
        "user": {"id": "user-1", "name": "Alice"},
        "createdAt": "2024-01-01T00:00:00Z",
        "updatedAt": "2024-01-02T00:00:00Z",
        "url": "https://linear.app/team/issue/LIN-1#comment-abc123",
    }
    defaults.update(kwargs)
    return defaults


def make_page_info(**kwargs) -> dict:
    defaults = {"hasNextPage": False, "endCursor": None}
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Authenticated mock client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """Return a MagicMock that mimics the Client class."""
    client = MagicMock()
    client.list_issues.return_value = ([make_issue()], make_page_info())
    client.get_issue.return_value = make_issue()
    client.create_issue.return_value = make_issue()
    client.update_issue.return_value = make_issue()
    client.delete_issue.return_value = True
    client.archive_issue.return_value = True
    client.unarchive_issue.return_value = True
    client.search_issues.return_value = ([make_issue()], make_page_info())
    client.add_issue_label.return_value = True
    client.remove_issue_label.return_value = True
    client.batch_create_issues.return_value = [make_issue()]
    client.batch_update_issues.return_value = True
    client.list_projects.return_value = ([make_project()], make_page_info())
    client.get_project.return_value = make_project()
    client.create_project.return_value = make_project()
    client.update_project.return_value = make_project()
    client.delete_project.return_value = True
    client.archive_project.return_value = True
    client.unarchive_project.return_value = True
    client.search_projects.return_value = ([make_project()], make_page_info())
    client.list_teams.return_value = ([make_team()], make_page_info())
    client.get_team.return_value = make_team()
    client.create_team.return_value = make_team()
    client.update_team.return_value = make_team()
    client.delete_team.return_value = True
    client.list_cycles.return_value = ([make_cycle()], make_page_info())
    client.get_cycle.return_value = make_cycle()
    client.create_cycle.return_value = make_cycle()
    client.update_cycle.return_value = make_cycle()
    client.archive_cycle.return_value = True
    client.list_labels.return_value = ([make_label()], make_page_info())
    client.get_label.return_value = make_label()
    client.create_label.return_value = make_label()
    client.update_label.return_value = make_label()
    client.delete_label.return_value = True
    client.list_users.return_value = ([make_user()], make_page_info())
    client.get_user.return_value = make_user()
    client.viewer.return_value = make_user()
    client.update_user.return_value = make_user()
    client.suspend_user.return_value = True
    client.unsuspend_user.return_value = True
    client.list_comments.return_value = ([make_comment()], make_page_info())
    client.create_comment.return_value = make_comment()
    client.update_comment.return_value = make_comment()
    client.delete_comment.return_value = True
    client.resolve_comment.return_value = make_comment()
    client.unresolve_comment.return_value = make_comment()
    doc = {"id": "doc-1", "title": "My Doc", "content": "Content here", "url": "https://linear.app/doc/1"}
    client.list_documents.return_value = ([doc], make_page_info())
    client.get_document.return_value = doc
    client.create_document.return_value = doc
    client.update_document.return_value = doc
    client.delete_document.return_value = True
    client.search_documents.return_value = ([doc], make_page_info())
    initiative = {"id": "init-1", "name": "Initiative A", "status": "planned", "description": "", "owner": None, "targetDate": None}
    client.list_initiatives.return_value = ([initiative], make_page_info())
    client.get_initiative.return_value = initiative
    client.create_initiative.return_value = initiative
    client.update_initiative.return_value = initiative
    client.delete_initiative.return_value = True
    client.archive_initiative.return_value = True
    client.unarchive_initiative.return_value = True
    roadmap = {"id": "road-1", "name": "Roadmap A", "description": "", "owner": None, "updatedAt": "2024-01-01T00:00:00Z"}
    client.list_roadmaps.return_value = ([roadmap], make_page_info())
    client.get_roadmap.return_value = roadmap
    client.create_roadmap.return_value = roadmap
    client.update_roadmap.return_value = roadmap
    client.delete_roadmap.return_value = True
    client.archive_roadmap.return_value = True
    client.unarchive_roadmap.return_value = True
    webhook = {"id": "hook-1", "url": "https://example.com/hook", "label": "My Hook", "enabled": True, "team": None}
    client.list_webhooks.return_value = ([webhook], make_page_info())
    client.get_webhook.return_value = webhook
    client.create_webhook.return_value = webhook
    client.update_webhook.return_value = webhook
    client.delete_webhook.return_value = True
    state = {"id": "state-1", "name": "In Progress", "type": "started", "color": "#ff0", "team": {"key": "ENG"}}
    client.list_states.return_value = ([state], make_page_info())
    client.create_state.return_value = state
    client.update_state.return_value = state
    client.archive_state.return_value = True
    customer = {"id": "cust-1", "name": "Acme", "domains": ["acme.com"], "owner": None}
    client.list_customers.return_value = ([customer], make_page_info())
    client.get_customer.return_value = customer
    client.create_customer.return_value = customer
    client.update_customer.return_value = customer
    client.delete_customer.return_value = True
    attachment = {"id": "attach-1", "title": "PR #42", "url": "https://github.com/org/repo/pull/42", "sourceType": "github", "issue": {"identifier": "LIN-1"}}
    client.list_attachments.return_value = ([attachment], make_page_info())
    client.get_attachment.return_value = attachment
    client.create_attachment.return_value = attachment
    client.delete_attachment.return_value = True
    client.link_url_to_issue.return_value = attachment
    notif = {"id": "notif-1", "type": "issueAssignedToYou", "readAt": None, "createdAt": "2024-01-01T00:00:00Z"}
    client.list_notifications.return_value = ([notif], make_page_info())
    client.get_notification.return_value = notif
    client.archive_notification.return_value = True
    client.unarchive_notification.return_value = True
    client.mark_all_notifications_read.return_value = True
    template = {"id": "tmpl-1", "name": "Bug report", "type": "issue", "team": {"key": "ENG"}}
    client.list_templates.return_value = ([template], make_page_info())
    client.get_template.return_value = template
    client.create_template.return_value = template
    client.update_template.return_value = template
    client.delete_template.return_value = True
    favorite = {"id": "fav-1", "type": "issue", "issue": {"identifier": "LIN-1"}}
    client.list_favorites.return_value = [favorite]
    client.create_favorite.return_value = favorite
    client.delete_favorite.return_value = True
    release = {"id": "rel-1", "name": "v1.0", "status": "released", "createdAt": "2024-01-01T00:00:00Z"}
    client.list_releases.return_value = ([release], make_page_info())
    client.create_release.return_value = release
    client.update_release.return_value = release
    client.delete_release.return_value = True
    client.archive_release.return_value = True
    org = {"id": "org-1", "name": "Acme Inc", "urlKey": "acme", "userCount": 10, "subscription": {"type": "business", "seats": 20}}
    client.get_organization.return_value = org
    client.update_organization.return_value = org
    view = {"id": "view-1", "name": "My View", "shared": True, "owner": {"name": "Alice"}, "team": {"key": "ENG"}}
    client.list_views.return_value = ([view], make_page_info())
    client.get_view.return_value = view
    client.create_view.return_value = view
    client.update_view.return_value = view
    client.delete_view.return_value = True
    milestone = {"id": "ms-1", "name": "M1", "project": {"name": "Q4 Sprint"}, "targetDate": "2024-03-01"}
    client.list_milestones.return_value = ([milestone], make_page_info())
    client.create_milestone.return_value = milestone
    client.update_milestone.return_value = milestone
    client.delete_milestone.return_value = True
    relation = {"id": "rel-1", "type": "blocks", "issue": {"identifier": "LIN-1"}, "relatedIssue": {"identifier": "LIN-2"}}
    client.list_issue_relations.return_value = ([relation], make_page_info())
    client.create_issue_relation.return_value = relation
    client.delete_issue_relation.return_value = True
    membership = {"id": "mem-1", "user": {"name": "Alice"}, "team": {"key": "ENG"}, "owner": False}
    client.list_team_memberships.return_value = ([membership], make_page_info())
    client.create_team_membership.return_value = membership
    client.delete_team_membership.return_value = True
    update = {"id": "upd-1", "project": {"name": "Q4 Sprint"}, "health": "onTrack", "user": {"name": "Alice"}, "createdAt": "2024-01-01T00:00:00Z"}
    client.list_project_updates.return_value = ([update], make_page_info())
    client.create_project_update.return_value = update
    client.delete_project_update.return_value = True
    emoji = {"id": "emoji-1", "name": "fire", "url": "https://example.com/fire.png", "creator": {"name": "Alice"}}
    client.list_emojis.return_value = ([emoji], make_page_info())
    client.create_emoji.return_value = emoji
    client.delete_emoji.return_value = True
    integration = {"id": "integ-1", "service": "github", "team": {"key": "ENG"}, "createdAt": "2024-01-01T00:00:00Z"}
    client.list_integrations.return_value = ([integration], make_page_info())
    audit_entry = {"id": "audit-1", "type": "Issue.create", "actor": {"name": "Alice"}, "createdAt": "2024-01-01T00:00:00Z"}
    client.list_audit_entries.return_value = ([audit_entry], make_page_info())
    return client


@pytest.fixture
def authed(mock_client):
    """Patch Client and get_api_key so commands run as authenticated."""
    with (
        patch("linear_cli.cli.Client", return_value=mock_client),
        patch("linear_cli.cli.get_api_key", return_value="lin_api_test123"),
        patch("linear_cli.cli.get_auth_status", return_value={"authenticated": True, "source": "environment", "keyring_available": False}),
        patch("linear_cli.cli.get_auth_source", return_value="environment"),
    ):
        yield mock_client


@pytest.fixture
def unauthed():
    """Patch get_api_key to return None (unauthenticated)."""
    with patch("linear_cli.cli.get_api_key", return_value=None):
        yield
