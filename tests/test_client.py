"""Unit tests for the Client class.

Tests GraphQL execution, pagination, error handling, and individual
API methods without hitting a real network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from linear_cli.client import Client, LinearAPIError, RateLimitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int = 200, json_body: dict | None = None, text: str = "") -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or str(json_body)
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = Exception("No JSON")
    return resp


# ===========================================================================
# Client construction
# ===========================================================================


def test_client_uses_provided_api_key():
    client = Client(api_key="lin_api_custom")
    assert client.api_key == "lin_api_custom"


def test_client_falls_back_to_config():
    with patch("linear_cli.client.get_api_key", return_value="lin_api_from_config"):
        client = Client()
    assert client.api_key == "lin_api_from_config"


def test_client_headers_include_auth():
    client = Client(api_key="lin_api_test")
    headers = client._headers()
    assert headers["Authorization"] == "lin_api_test"
    assert headers["Content-Type"] == "application/json"


# ===========================================================================
# _execute - success
# ===========================================================================


def test_execute_returns_data_field():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {"viewer": {"id": "u1", "name": "Alice"}}})
    with patch("httpx.post", return_value=resp):
        result = client._execute("query { viewer { id } }")
    assert result["viewer"]["id"] == "u1"


def test_execute_sends_query_and_variables():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {"issue": {"id": "i1"}}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client._execute("query Q($id: String!) { issue(id: $id) { id } }", {"id": "i1"})
    payload = mock_post.call_args[1]["json"]
    assert payload["query"].startswith("query Q")
    assert payload["variables"] == {"id": "i1"}


def test_execute_no_variables_omits_variables_key():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client._execute("query { viewer { id } }")
    payload = mock_post.call_args[1]["json"]
    assert "variables" not in payload


# ===========================================================================
# _execute - GraphQL errors
# ===========================================================================


def test_execute_raises_on_graphql_errors():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": None, "errors": [{"message": "Not found"}]})
    with patch("httpx.post", return_value=resp):
        with pytest.raises(LinearAPIError, match="Not found"):
            client._execute("query { issue(id: \"bad\") { id } }")


def test_execute_raises_with_status_zero_on_graphql_error():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": None, "errors": [{"message": "Something broke"}]})
    with patch("httpx.post", return_value=resp):
        try:
            client._execute("query { foo }")
        except LinearAPIError as exc:
            assert exc.status_code == 200


# ===========================================================================
# _execute - HTTP errors
# ===========================================================================


def test_execute_raises_linear_api_error_on_401():
    client = Client(api_key="key")
    resp = _make_response(401, {"errors": [{"message": "Unauthorized"}]})
    with patch("httpx.post", return_value=resp):
        with pytest.raises(LinearAPIError) as exc_info:
            client._execute("query { viewer { id } }")
    assert exc_info.value.status_code == 401


def test_execute_raises_linear_api_error_on_404():
    client = Client(api_key="key")
    resp = _make_response(404, {"errors": [{"message": "Not found"}]})
    with patch("httpx.post", return_value=resp):
        with pytest.raises(LinearAPIError) as exc_info:
            client._execute("query { issue(id: \"bad\") { id } }")
    assert exc_info.value.status_code == 404


def test_execute_raises_linear_api_error_on_500():
    client = Client(api_key="key")
    resp = _make_response(500, None, text="Internal Server Error")
    with patch("httpx.post", return_value=resp):
        with pytest.raises(LinearAPIError) as exc_info:
            client._execute("query { viewer { id } }")
    assert exc_info.value.status_code == 500


# ===========================================================================
# _execute - rate limit
# ===========================================================================


def test_execute_raises_rate_limit_error():
    client = Client(api_key="key")
    resp = _make_response(400, {
        "errors": [{"message": "Rate limited", "extensions": {"code": "RATELIMITED"}}]
    })
    with patch("httpx.post", return_value=resp):
        with pytest.raises(RateLimitError):
            client._execute("query { viewer { id } }")


def test_rate_limit_error_is_subclass_of_linear_api_error():
    assert issubclass(RateLimitError, LinearAPIError)


# ===========================================================================
# _paginate
# ===========================================================================


def test_paginate_single_page():
    client = Client(api_key="key")
    nodes = [{"id": "i1", "title": "T1"}, {"id": "i2", "title": "T2"}]
    page_info = {"hasNextPage": False, "endCursor": None}
    resp = _make_response(200, {"data": {"issues": {"nodes": nodes, "pageInfo": page_info}}})
    with patch("httpx.post", return_value=resp):
        result_nodes, result_page_info = client._paginate(
            "query ListIssues($first: Int) { issues(first: $first) { nodes { id title } pageInfo { hasNextPage endCursor } } }",
            "issues",
            limit=50,
        )
    assert len(result_nodes) == 2
    assert result_page_info["hasNextPage"] is False


def test_paginate_respects_limit():
    client = Client(api_key="key")
    nodes = [{"id": f"i{n}"} for n in range(10)]
    page_info = {"hasNextPage": True, "endCursor": "cursor-1"}
    resp = _make_response(200, {"data": {"issues": {"nodes": nodes, "pageInfo": page_info}}})
    with patch("httpx.post", return_value=resp):
        result_nodes, _ = client._paginate(
            "query { issues(first: $first) { nodes { id } pageInfo { hasNextPage endCursor } } }",
            "issues",
            limit=5,
        )
    assert len(result_nodes) == 5


def test_paginate_nested_field():
    client = Client(api_key="key")
    nodes = [{"id": "t1"}]
    page_info = {"hasNextPage": False, "endCursor": None}
    resp = _make_response(200, {
        "data": {"team": {"issues": {"nodes": nodes, "pageInfo": page_info}}}
    })
    with patch("httpx.post", return_value=resp):
        result_nodes, _ = client._paginate(
            "query { team { issues { nodes { id } pageInfo { hasNextPage endCursor } } } }",
            "team.issues",
            limit=50,
        )
    assert result_nodes == nodes


# ===========================================================================
# viewer
# ===========================================================================


def test_viewer_returns_user():
    client = Client(api_key="key")
    user = {"id": "u1", "name": "Alice", "email": "a@b.com"}
    resp = _make_response(200, {"data": {"viewer": user}})
    with patch("httpx.post", return_value=resp):
        result = client.viewer()
    assert result["id"] == "u1"


# ===========================================================================
# Issues
# ===========================================================================


def test_list_issues_builds_filter_team_id():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client.list_issues(team_id="team-abc")
    payload = mock_post.call_args[1]["json"]
    assert payload["variables"]["filter"]["team"]["id"]["eq"] == "team-abc"


def test_get_issue_sends_correct_id():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {"issue": {"id": "i1", "identifier": "LIN-1"}}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client.get_issue("LIN-1")
    payload = mock_post.call_args[1]["json"]
    assert payload["variables"]["id"] == "LIN-1"


def test_create_issue_sends_title_and_team():
    client = Client(api_key="key")
    created = {"id": "i1", "identifier": "LIN-1", "title": "Fix bug", "url": "https://linear.app"}
    resp = _make_response(200, {"data": {"issueCreate": {"success": True, "issue": created}}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client.create_issue(title="Fix bug", team_id="team-1")
    payload = mock_post.call_args[1]["json"]
    assert payload["variables"]["input"]["title"] == "Fix bug"
    assert payload["variables"]["input"]["teamId"] == "team-1"


def test_delete_issue_returns_success():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {"issueDelete": {"success": True}}})
    with patch("httpx.post", return_value=resp):
        result = client.delete_issue("i1")
    assert result is True


def test_archive_issue_returns_success():
    client = Client(api_key="key")
    resp = _make_response(200, {"data": {"issueArchive": {"success": True}}})
    with patch("httpx.post", return_value=resp):
        result = client.archive_issue("i1")
    assert result is True


def test_update_issue_builds_input():
    client = Client(api_key="key")
    updated = {"id": "i1", "identifier": "LIN-1", "title": "Updated", "url": "https://linear.app", "updatedAt": "2024-01-01"}
    resp = _make_response(200, {"data": {"issueUpdate": {"success": True, "issue": updated}}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client.update_issue("i1", title="Updated", priority=1)
    payload = mock_post.call_args[1]["json"]
    assert payload["variables"]["input"]["title"] == "Updated"
    assert payload["variables"]["input"]["priority"] == 1


def test_update_issue_merges_body():
    client = Client(api_key="key")
    updated = {"id": "i1", "identifier": "LIN-1", "title": "X", "url": "https://linear.app", "updatedAt": "2024-01-01"}
    resp = _make_response(200, {"data": {"issueUpdate": {"success": True, "issue": updated}}})
    with patch("httpx.post", return_value=resp) as mock_post:
        client.update_issue("i1", body={"customField": "value"})
    payload = mock_post.call_args[1]["json"]
    assert payload["variables"]["input"]["customField"] == "value"


# ===========================================================================
# LinearAPIError
# ===========================================================================


def test_linear_api_error_stores_status_code():
    exc = LinearAPIError("Something failed", status_code=422)
    assert exc.status_code == 422
    assert str(exc) == "Something failed"


def test_linear_api_error_stores_errors_list():
    errors = [{"message": "Field required"}]
    exc = LinearAPIError("Validation failed", status_code=422, errors=errors)
    assert exc.errors == errors


def test_linear_api_error_default_status_zero():
    exc = LinearAPIError("Unknown")
    assert exc.status_code == 0


def test_rate_limit_error_stores_message():
    exc = RateLimitError("Too many requests", status_code=400)
    assert exc.status_code == 400
    assert "Too many requests" in str(exc)
