"""Linear GraphQL API client."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .config import API_URL, get_api_key


class LinearAPIError(Exception):
    """Linear API error with status code and response."""

    def __init__(self, message: str, status_code: int = 0, errors: list | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []


class RateLimitError(LinearAPIError):
    """Rate limit exceeded."""

    pass


class Client:
    """GraphQL client for Linear API."""

    TIMEOUT = 30

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key()

    def _headers(self) -> dict:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    def _execute(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query/mutation."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = httpx.post(
            API_URL,
            headers=self._headers(),
            json=payload,
            timeout=self.TIMEOUT,
        )

        if response.status_code == 400:
            try:
                body = response.json()
                errors = body.get("errors", [])
                if errors and errors[0].get("extensions", {}).get("code") == "RATELIMITED":
                    raise RateLimitError(
                        errors[0].get("message", "Rate limited"),
                        status_code=400,
                        errors=errors,
                    )
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

        if response.status_code >= 400:
            try:
                body = response.json()
                errors = body.get("errors", [])
                message = errors[0]["message"] if errors else response.text
            except Exception:
                message = response.text
            raise LinearAPIError(message, response.status_code)

        body = response.json()
        if "errors" in body:
            errors = body["errors"]
            message = errors[0].get("message", "Unknown error")
            raise LinearAPIError(message, response.status_code, errors)

        return body.get("data", {})

    def _paginate(
        self,
        query: str,
        field: str,
        variables: dict | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """Execute a paginated query, returning (nodes, pageInfo).

        Supports Relay-style cursor pagination with first/after.
        """
        variables = dict(variables or {})
        all_nodes: list[dict] = []
        page_info: dict = {}

        while True:
            variables["first"] = min(limit - len(all_nodes), 50) if not fetch_all else 50
            data = self._execute(query, variables)

            # Navigate to the connection field (supports nested like team.issues)
            result = data
            for part in field.split("."):
                result = result.get(part, {})

            nodes = result.get("nodes", [])
            page_info = result.get("pageInfo", {})

            all_nodes.extend(nodes)

            if fetch_all and page_info.get("hasNextPage") and page_info.get("endCursor"):
                variables["after"] = page_info["endCursor"]
            elif not fetch_all and len(all_nodes) >= limit:
                break
            elif not page_info.get("hasNextPage"):
                break
            else:
                variables["after"] = page_info["endCursor"]

        if not fetch_all:
            all_nodes = all_nodes[:limit]

        return all_nodes, page_info

    def _bool_mutation(self, mutation_name: str, id_value: str) -> bool:
        """Execute a simple boolean mutation (delete/archive/unarchive)."""
        query = f"""
    mutation Op($id: String!) {{
        {mutation_name}(id: $id) {{ success }}
    }}
    """
        return self._execute(query, {"id": id_value})[mutation_name]["success"]

    # =========================================================================
    # Viewer
    # =========================================================================

    def viewer(self) -> dict:
        """Get the authenticated user."""
        query = """
        query {
            viewer {
                id name displayName email active admin
                avatarUrl createdAt updatedAt
                organization { id name urlKey }
            }
        }
        """
        return self._execute(query)["viewer"]

    # =========================================================================
    # Issues
    # =========================================================================

    def list_issues(
        self,
        team_id: str | None = None,
        assignee_id: str | None = None,
        state_name: str | None = None,
        state_type: str | None = None,
        label_name: str | None = None,
        priority: int | None = None,
        project_id: str | None = None,
        cycle_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        after: str | None = None,
        include_archived: bool = False,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List issues with filtering."""
        query = """
        query ListIssues($first: Int, $after: String, $filter: IssueFilter,
                         $includeArchived: Boolean) {
            issues(first: $first, after: $after, filter: $filter,
                   includeArchived: $includeArchived, orderBy: updatedAt) {
                nodes {
                    id identifier title priority priorityLabel
                    estimate sortOrder
                    state { id name type color }
                    assignee { id name email }
                    team { id name key }
                    project { id name }
                    cycle { id name number }
                    labels { nodes { id name color } }
                    createdAt updatedAt completedAt canceledAt
                    dueDate url branchName
                    parent { id identifier }
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        filter_obj: dict[str, Any] = {}
        if team_id:
            filter_obj["team"] = {"id": {"eq": team_id}}
        if assignee_id:
            filter_obj["assignee"] = {"id": {"eq": assignee_id}}
        if state_name:
            filter_obj["state"] = {"name": {"eqIgnoreCase": state_name}}
        if state_type:
            filter_obj["state"] = {"type": {"eq": state_type}}
        if label_name:
            filter_obj["labels"] = {"some": {"name": {"eqIgnoreCase": label_name}}}
        if priority is not None:
            filter_obj["priority"] = {"eq": priority}
        if project_id:
            filter_obj["project"] = {"id": {"eq": project_id}}
        if cycle_id:
            filter_obj["cycle"] = {"id": {"eq": cycle_id}}

        variables: dict[str, Any] = {"includeArchived": include_archived}
        if filter_obj:
            variables["filter"] = filter_obj
        if after:
            variables["after"] = after

        if search:
            return self.search_issues(search, limit=limit, include_archived=include_archived)

        return self._paginate(query, "issues", variables, limit=limit, fetch_all=fetch_all)

    def get_issue(self, issue_id: str) -> dict:
        """Get a single issue by ID or identifier (e.g., 'LIN-123')."""
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id identifier title description priority priorityLabel
                estimate sortOrder boardOrder subIssueSortOrder
                state { id name type color }
                assignee { id name email }
                creator { id name email }
                team { id name key }
                project { id name }
                cycle { id name number }
                parent { id identifier title }
                labels { nodes { id name color } }
                children { nodes { id identifier title state { name } } }
                relations { nodes { id type relatedIssue { id identifier title } } }
                attachments { nodes { id title url sourceType } }
                comments { nodes { id body user { name } createdAt } }
                createdAt updatedAt completedAt canceledAt archivedAt
                dueDate slaStartedAt slaBreachesAt
                url branchName
                previousIdentifiers
            }
        }
        """
        return self._execute(query, {"id": issue_id})["issue"]

    def create_issue(
        self,
        title: str,
        team_id: str,
        description: str | None = None,
        assignee_id: str | None = None,
        state_id: str | None = None,
        priority: int | None = None,
        label_ids: list[str] | None = None,
        project_id: str | None = None,
        cycle_id: str | None = None,
        parent_id: str | None = None,
        estimate: int | None = None,
        due_date: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create an issue."""
        query = """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id identifier title url
                    state { name }
                    assignee { name }
                    team { key }
                    createdAt
                }
            }
        }
        """
        input_data: dict[str, Any] = {"title": title, "teamId": team_id}
        if description is not None:
            input_data["description"] = description
        if assignee_id:
            input_data["assigneeId"] = assignee_id
        if state_id:
            input_data["stateId"] = state_id
        if priority is not None:
            input_data["priority"] = priority
        if label_ids:
            input_data["labelIds"] = label_ids
        if project_id:
            input_data["projectId"] = project_id
        if cycle_id:
            input_data["cycleId"] = cycle_id
        if parent_id:
            input_data["parentId"] = parent_id
        if estimate is not None:
            input_data["estimate"] = estimate
        if due_date:
            input_data["dueDate"] = due_date

        if body:
            input_data.update(body)

        result = self._execute(query, {"input": input_data})
        return result["issueCreate"]["issue"]

    def update_issue(self, issue_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update an issue."""
        query = """
        mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id identifier title url
                    state { name }
                    assignee { name }
                    updatedAt
                }
            }
        }
        """
        input_data = {}
        field_map = {
            "title": "title",
            "description": "description",
            "assignee_id": "assigneeId",
            "state_id": "stateId",
            "priority": "priority",
            "project_id": "projectId",
            "cycle_id": "cycleId",
            "parent_id": "parentId",
            "estimate": "estimate",
            "due_date": "dueDate",
            "label_ids": "labelIds",
        }
        for py_key, gql_key in field_map.items():
            if py_key in kwargs and kwargs[py_key] is not None:
                input_data[gql_key] = kwargs[py_key]

        if body:
            input_data.update(body)

        result = self._execute(query, {"id": issue_id, "input": input_data})
        return result["issueUpdate"]["issue"]

    def delete_issue(self, issue_id: str) -> bool:
        """Delete a issue."""
        return self._bool_mutation("issueDelete", issue_id)

    def archive_issue(self, issue_id: str) -> bool:
        """Archive a issue."""
        return self._bool_mutation("issueArchive", issue_id)

    def unarchive_issue(self, issue_id: str) -> bool:
        """Unarchive a issue."""
        return self._bool_mutation("issueUnarchive", issue_id)

    def search_issues(
        self,
        query_text: str,
        limit: int = 50,
        include_archived: bool = False,
    ) -> tuple[list[dict], dict]:
        """Search issues by text."""
        query = """
        query SearchIssues($term: String!, $first: Int, $includeArchived: Boolean) {
            searchIssues(term: $term, first: $first, includeArchived: $includeArchived) {
                nodes {
                    id identifier title priority priorityLabel
                    state { id name type color }
                    assignee { id name email }
                    team { id name key }
                    project { id name }
                    labels { nodes { id name color } }
                    createdAt updatedAt url
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables = {
            "term": query_text,
            "first": min(limit, 50),
            "includeArchived": include_archived,
        }
        data = self._execute(query, variables)
        result = data["searchIssues"]
        return result.get("nodes", []), result.get("pageInfo", {})

    def add_issue_label(self, issue_id: str, label_id: str) -> bool:
        """Add a label to an issue."""
        query = """
        mutation IssueAddLabel($id: String!, $labelId: String!) {
            issueAddLabel(id: $id, labelId: $labelId) { success }
        }
        """
        return self._execute(query, {"id": issue_id, "labelId": label_id})["issueAddLabel"][
            "success"
        ]

    def remove_issue_label(self, issue_id: str, label_id: str) -> bool:
        """Remove a label from an issue."""
        query = """
        mutation IssueRemoveLabel($id: String!, $labelId: String!) {
            issueRemoveLabel(id: $id, labelId: $labelId) { success }
        }
        """
        return self._execute(query, {"id": issue_id, "labelId": label_id})["issueRemoveLabel"][
            "success"
        ]

    def batch_create_issues(self, issues: list[dict]) -> list[dict]:
        """Create multiple issues in one transaction."""
        query = """
        mutation IssueBatchCreate($input: IssueBatchCreateInput!) {
            issueBatchCreate(input: $input) {
                success
                issues {
                    id identifier title url
                    state { name }
                    team { key }
                }
            }
        }
        """
        result = self._execute(query, {"input": {"issues": issues}})
        return result["issueBatchCreate"]["issues"]

    def batch_update_issues(self, issue_ids: list[str], update: dict) -> bool:
        """Update multiple issues at once."""
        query = """
        mutation IssueBatchUpdate($ids: [UUID!]!, $input: IssueUpdateInput!) {
            issueBatchUpdate(ids: $ids, input: $input) { success }
        }
        """
        return self._execute(query, {"ids": issue_ids, "input": update})["issueBatchUpdate"][
            "success"
        ]

    # =========================================================================
    # Projects
    # =========================================================================

    def list_projects(
        self,
        team_id: str | None = None,
        state: str | None = None,
        limit: int = 50,
        after: str | None = None,
        include_archived: bool = False,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List projects."""
        query = """
        query ListProjects($first: Int, $after: String, $filter: ProjectFilter,
                           $includeArchived: Boolean) {
            projects(first: $first, after: $after, filter: $filter,
                     includeArchived: $includeArchived, orderBy: updatedAt) {
                nodes {
                    id name slugId description icon color
                    state priority sortOrder
                    progress scope
                    startDate targetDate
                    lead { id name email }
                    status { id name color }
                    teams { nodes { id name key } }
                    members { nodes { id name } }
                    createdAt updatedAt completedAt canceledAt archivedAt
                    url
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {"includeArchived": include_archived}
        filter_obj: dict[str, Any] = {}
        if state:
            filter_obj["state"] = {"eq": state}
        if team_id:
            filter_obj["accessibleTeams"] = {"some": {"id": {"eq": team_id}}}
        if filter_obj:
            variables["filter"] = filter_obj
        if after:
            variables["after"] = after

        return self._paginate(query, "projects", variables, limit=limit, fetch_all=fetch_all)

    def get_project(self, project_id: str) -> dict:
        """Get a project by ID."""
        query = """
        query GetProject($id: String!) {
            project(id: $id) {
                id name slugId description icon color content
                state priority sortOrder
                progress scope
                startDate targetDate
                lead { id name email }
                status { id name color }
                teams { nodes { id name key } }
                members { nodes { id name email } }
                issues { nodes { id identifier title state { name } } }
                milestones { nodes { id name sortOrder targetDate } }
                projectUpdates { nodes { id body createdAt user { name } } }
                labels { nodes { id name color } }
                createdAt updatedAt completedAt canceledAt archivedAt
                url
            }
        }
        """
        return self._execute(query, {"id": project_id})["project"]

    def create_project(
        self,
        name: str,
        team_ids: list[str],
        description: str | None = None,
        state: str | None = None,
        lead_id: str | None = None,
        start_date: str | None = None,
        target_date: str | None = None,
        priority: int | None = None,
        color: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a project."""
        query = """
        mutation ProjectCreate($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project { id name slugId url state createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name, "teamIds": team_ids}
        if description:
            input_data["description"] = description
        if state:
            input_data["state"] = state
        if lead_id:
            input_data["leadId"] = lead_id
        if start_date:
            input_data["startDate"] = start_date
        if target_date:
            input_data["targetDate"] = target_date
        if priority is not None:
            input_data["priority"] = priority
        if color:
            input_data["color"] = color
        if body:
            input_data.update(body)

        result = self._execute(query, {"input": input_data})
        return result["projectCreate"]["project"]

    def update_project(self, project_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a project."""
        query = """
        mutation ProjectUpdate($id: String!, $input: ProjectUpdateInput!) {
            projectUpdate(id: $id, input: $input) {
                success
                project { id name state url updatedAt }
            }
        }
        """
        input_data = {}
        field_map = {
            "name": "name",
            "description": "description",
            "state": "state",
            "lead_id": "leadId",
            "start_date": "startDate",
            "target_date": "targetDate",
            "priority": "priority",
            "color": "color",
            "status_id": "statusId",
        }
        for py_key, gql_key in field_map.items():
            if py_key in kwargs and kwargs[py_key] is not None:
                input_data[gql_key] = kwargs[py_key]
        if body:
            input_data.update(body)

        result = self._execute(query, {"id": project_id, "input": input_data})
        return result["projectUpdate"]["project"]

    def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        return self._bool_mutation("projectDelete", project_id)

    def archive_project(self, project_id: str) -> bool:
        """Archive a project."""
        return self._bool_mutation("projectArchive", project_id)

    def unarchive_project(self, project_id: str) -> bool:
        """Unarchive a project."""
        return self._bool_mutation("projectUnarchive", project_id)

    def search_projects(self, query_text: str, limit: int = 50) -> tuple[list[dict], dict]:
        """Search projects."""
        query = """
        query SearchProjects($term: String!, $first: Int) {
            searchProjects(term: $term, first: $first) {
                nodes { id name slugId state url progress createdAt }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        data = self._execute(query, {"term": query_text, "first": min(limit, 50)})
        result = data["searchProjects"]
        return result.get("nodes", []), result.get("pageInfo", {})

    # =========================================================================
    # Teams
    # =========================================================================

    def list_teams(
        self, limit: int = 50, include_archived: bool = False, fetch_all: bool = False
    ) -> tuple[list[dict], dict]:
        """List teams."""
        query = """
        query ListTeams($first: Int, $after: String, $includeArchived: Boolean) {
            teams(first: $first, after: $after, includeArchived: $includeArchived) {
                nodes {
                    id name key description private
                    icon color
                    issueCount
                    timezone autoArchivePeriod
                    triageEnabled cyclesEnabled
                    defaultIssueState { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(
            query,
            "teams",
            {"includeArchived": include_archived},
            limit=limit,
            fetch_all=fetch_all,
        )

    def get_team(self, team_id: str) -> dict:
        """Get a team by ID."""
        query = """
        query GetTeam($id: String!) {
            team(id: $id) {
                id name key description private
                icon color
                issueCount
                timezone autoArchivePeriod
                triageEnabled cyclesEnabled
                defaultIssueState { id name }
                states { nodes { id name type color position } }
                labels { nodes { id name color } }
                members { nodes { id name email active } }
                activeCycle { id name number startsAt endsAt }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": team_id})["team"]

    def create_team(
        self, name: str, key: str | None = None, body: dict | None = None, **kwargs
    ) -> dict:
        """Create a team."""
        query = """
        mutation TeamCreate($input: TeamCreateInput!) {
            teamCreate(input: $input) {
                success
                team { id name key createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        if key:
            input_data["key"] = key
        for k in ["description", "icon", "color", "timezone", "private"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)

        result = self._execute(query, {"input": input_data})
        return result["teamCreate"]["team"]

    def update_team(self, team_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a team."""
        query = """
        mutation TeamUpdate($id: String!, $input: TeamUpdateInput!) {
            teamUpdate(id: $id, input: $input) {
                success
                team { id name key updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "key", "description", "icon", "color", "timezone", "private"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)

        result = self._execute(query, {"id": team_id, "input": input_data})
        return result["teamUpdate"]["team"]

    def delete_team(self, team_id: str) -> bool:
        """Delete a team."""
        return self._bool_mutation("teamDelete", team_id)

    # =========================================================================
    # Cycles
    # =========================================================================

    def list_cycles(
        self,
        team_id: str | None = None,
        limit: int = 50,
        include_archived: bool = False,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List cycles."""
        query = """
        query ListCycles($first: Int, $after: String, $filter: CycleFilter,
                         $includeArchived: Boolean) {
            cycles(first: $first, after: $after, filter: $filter,
                   includeArchived: $includeArchived) {
                nodes {
                    id name number description
                    startsAt endsAt completedAt
                    progress scope
                    issueCountHistory completedIssueCountHistory
                    team { id name key }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {"includeArchived": include_archived}
        if team_id:
            variables["filter"] = {"team": {"id": {"eq": team_id}}}
        return self._paginate(query, "cycles", variables, limit=limit, fetch_all=fetch_all)

    def get_cycle(self, cycle_id: str) -> dict:
        """Get a cycle by ID."""
        query = """
        query GetCycle($id: String!) {
            cycle(id: $id) {
                id name number description
                startsAt endsAt completedAt
                progress scope
                issueCountHistory completedIssueCountHistory
                team { id name key }
                issues { nodes { id identifier title state { name } } }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": cycle_id})["cycle"]

    def create_cycle(
        self,
        team_id: str,
        starts_at: str,
        ends_at: str,
        name: str | None = None,
        description: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a cycle."""
        query = """
        mutation CycleCreate($input: CycleCreateInput!) {
            cycleCreate(input: $input) {
                success
                cycle { id name number startsAt endsAt team { key } }
            }
        }
        """
        input_data: dict[str, Any] = {
            "teamId": team_id,
            "startsAt": starts_at,
            "endsAt": ends_at,
        }
        if name:
            input_data["name"] = name
        if description:
            input_data["description"] = description
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["cycleCreate"]["cycle"]

    def update_cycle(self, cycle_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a cycle."""
        query = """
        mutation CycleUpdate($id: String!, $input: CycleUpdateInput!) {
            cycleUpdate(id: $id, input: $input) {
                success
                cycle { id name number updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "description", "startsAt", "endsAt"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": cycle_id, "input": input_data})
        return result["cycleUpdate"]["cycle"]

    def archive_cycle(self, cycle_id: str) -> bool:
        """Archive a cycle."""
        return self._bool_mutation("cycleArchive", cycle_id)

    # =========================================================================
    # Labels (Issue Labels)
    # =========================================================================

    def list_labels(
        self,
        team_id: str | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List issue labels."""
        query = """
        query ListLabels($first: Int, $after: String, $filter: IssueLabelFilter) {
            issueLabels(first: $first, after: $after, filter: $filter) {
                nodes {
                    id name description color
                    isGroup
                    parent { id name }
                    team { id name key }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {}
        if team_id:
            variables["filter"] = {"team": {"id": {"eq": team_id}}}
        return self._paginate(query, "issueLabels", variables, limit=limit, fetch_all=fetch_all)

    def get_label(self, label_id: str) -> dict:
        """Get a label by ID."""
        query = """
        query GetLabel($id: String!) {
            issueLabel(id: $id) {
                id name description color isGroup
                parent { id name }
                team { id name key }
                children { nodes { id name color } }
                issues { nodes { id identifier title } }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": label_id})["issueLabel"]

    def create_label(
        self,
        name: str,
        team_id: str | None = None,
        color: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a label."""
        query = """
        mutation LabelCreate($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel { id name color createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        if team_id:
            input_data["teamId"] = team_id
        if color:
            input_data["color"] = color
        if description:
            input_data["description"] = description
        if parent_id:
            input_data["parentId"] = parent_id
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["issueLabelCreate"]["issueLabel"]

    def update_label(self, label_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a label."""
        query = """
        mutation LabelUpdate($id: String!, $input: IssueLabelUpdateInput!) {
            issueLabelUpdate(id: $id, input: $input) {
                success
                issueLabel { id name color updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "color", "description"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": label_id, "input": input_data})
        return result["issueLabelUpdate"]["issueLabel"]

    def delete_label(self, label_id: str) -> bool:
        """Delete a label."""
        return self._bool_mutation("issueLabelDelete", label_id)

    # =========================================================================
    # Users
    # =========================================================================

    def list_users(
        self,
        limit: int = 50,
        include_archived: bool = False,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List users."""
        query = """
        query ListUsers($first: Int, $after: String, $includeArchived: Boolean) {
            users(first: $first, after: $after, includeArchived: $includeArchived) {
                nodes {
                    id name displayName email active admin guest
                    avatarUrl statusLabel statusEmoji
                    timezone lastSeen
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(
            query,
            "users",
            {"includeArchived": include_archived},
            limit=limit,
            fetch_all=fetch_all,
        )

    def get_user(self, user_id: str) -> dict:
        """Get a user by ID."""
        query = """
        query GetUser($id: String!) {
            user(id: $id) {
                id name displayName email active admin guest
                avatarUrl statusLabel statusEmoji
                timezone lastSeen description
                organization { id name }
                teamMemberships { nodes { id team { id name key } } }
                assignedIssues { nodes { id identifier title state { name } } }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": user_id})["user"]

    def update_user(self, user_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a user."""
        query = """
        mutation UserUpdate($id: String!, $input: UpdateUserInput!) {
            userUpdate(id: $id, input: $input) {
                success
                user { id name displayName email updatedAt }
            }
        }
        """
        input_data = {}
        for k in [
            "name",
            "displayName",
            "description",
            "avatarUrl",
            "statusLabel",
            "statusEmoji",
            "timezone",
        ]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": user_id, "input": input_data})
        return result["userUpdate"]["user"]

    def suspend_user(self, user_id: str) -> bool:
        """Suspend a user."""
        query = """
        mutation UserSuspend($id: String!) {
            userSuspend(id: $id) { success }
        }
        """
        return self._execute(query, {"id": user_id})["userSuspend"]["success"]

    def unsuspend_user(self, user_id: str) -> bool:
        """Unsuspend a user."""
        query = """
        mutation UserUnsuspend($id: String!) {
            userUnsuspend(id: $id) { success }
        }
        """
        return self._execute(query, {"id": user_id})["userUnsuspend"]["success"]

    # =========================================================================
    # Comments
    # =========================================================================

    def list_comments(
        self,
        issue_id: str | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List comments."""
        query = """
        query ListComments($first: Int, $after: String, $filter: CommentFilter) {
            comments(first: $first, after: $after, filter: $filter) {
                nodes {
                    id body
                    user { id name email }
                    issue { id identifier }
                    parent { id }
                    resolvedAt resolvedBy { id name }
                    createdAt updatedAt editedAt archivedAt
                    url
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {}
        if issue_id:
            variables["filter"] = {"issue": {"id": {"eq": issue_id}}}
        return self._paginate(query, "comments", variables, limit=limit, fetch_all=fetch_all)

    def create_comment(
        self,
        issue_id: str,
        body_text: str,
        parent_id: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a comment on an issue."""
        query = """
        mutation CommentCreate($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment { id body url user { name } createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"issueId": issue_id, "body": body_text}
        if parent_id:
            input_data["parentId"] = parent_id
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["commentCreate"]["comment"]

    def update_comment(self, comment_id: str, body_text: str, body: dict | None = None) -> dict:
        """Update a comment."""
        query = """
        mutation CommentUpdate($id: String!, $input: CommentUpdateInput!) {
            commentUpdate(id: $id, input: $input) {
                success
                comment { id body updatedAt }
            }
        }
        """
        input_data: dict[str, Any] = {"body": body_text}
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": comment_id, "input": input_data})
        return result["commentUpdate"]["comment"]

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment."""
        return self._bool_mutation("commentDelete", comment_id)

    def resolve_comment(self, comment_id: str) -> dict:
        """Resolve a comment."""
        query = """
        mutation CommentResolve($id: String!) {
            commentResolve(id: $id) {
                success
                comment { id resolvedAt }
            }
        }
        """
        return self._execute(query, {"id": comment_id})["commentResolve"]["comment"]

    def unresolve_comment(self, comment_id: str) -> dict:
        """Unresolve a comment."""
        query = """
        mutation CommentUnresolve($id: String!) {
            commentUnresolve(id: $id) {
                success
                comment { id resolvedAt }
            }
        }
        """
        return self._execute(query, {"id": comment_id})["commentUnresolve"]["comment"]

    # =========================================================================
    # Documents
    # =========================================================================

    def list_documents(
        self,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List documents."""
        query = """
        query ListDocuments($first: Int, $after: String) {
            documents(first: $first, after: $after) {
                nodes {
                    id title slugId icon color
                    project { id name }
                    creator { id name }
                    updatedBy { id name }
                    createdAt updatedAt archivedAt
                    url
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "documents", {}, limit=limit, fetch_all=fetch_all)

    def get_document(self, doc_id: str) -> dict:
        """Get a document by ID."""
        query = """
        query GetDocument($id: String!) {
            document(id: $id) {
                id title slugId icon color content
                project { id name }
                creator { id name }
                updatedBy { id name }
                createdAt updatedAt archivedAt
                url
            }
        }
        """
        return self._execute(query, {"id": doc_id})["document"]

    def create_document(
        self,
        title: str,
        content: str | None = None,
        project_id: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a document."""
        query = """
        mutation DocumentCreate($input: DocumentCreateInput!) {
            documentCreate(input: $input) {
                success
                document { id title slugId url createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"title": title}
        if content:
            input_data["content"] = content
        if project_id:
            input_data["projectId"] = project_id
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["documentCreate"]["document"]

    def update_document(self, doc_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a document."""
        query = """
        mutation DocumentUpdate($id: String!, $input: DocumentUpdateInput!) {
            documentUpdate(id: $id, input: $input) {
                success
                document { id title updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["title", "content", "icon", "color"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": doc_id, "input": input_data})
        return result["documentUpdate"]["document"]

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document."""
        return self._bool_mutation("documentDelete", doc_id)

    def search_documents(self, query_text: str, limit: int = 50) -> tuple[list[dict], dict]:
        """Search documents."""
        query = """
        query SearchDocuments($term: String!, $first: Int) {
            searchDocuments(term: $term, first: $first) {
                nodes { id title slugId url createdAt }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        data = self._execute(query, {"term": query_text, "first": min(limit, 50)})
        result = data["searchDocuments"]
        return result.get("nodes", []), result.get("pageInfo", {})

    # =========================================================================
    # Workflow States
    # =========================================================================

    def list_states(
        self,
        team_id: str | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List workflow states."""
        query = """
        query ListStates($first: Int, $after: String, $filter: WorkflowStateFilter) {
            workflowStates(first: $first, after: $after, filter: $filter) {
                nodes {
                    id name type color position description
                    team { id name key }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {}
        if team_id:
            variables["filter"] = {"team": {"id": {"eq": team_id}}}
        return self._paginate(query, "workflowStates", variables, limit=limit, fetch_all=fetch_all)

    def create_state(
        self,
        name: str,
        team_id: str,
        type: str,
        color: str | None = None,
        description: str | None = None,
        position: float | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a workflow state."""
        query = """
        mutation StateCreate($input: WorkflowStateCreateInput!) {
            workflowStateCreate(input: $input) {
                success
                workflowState { id name type color position createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name, "teamId": team_id, "type": type}
        if color:
            input_data["color"] = color
        if description:
            input_data["description"] = description
        if position is not None:
            input_data["position"] = position
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["workflowStateCreate"]["workflowState"]

    def update_state(self, state_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a workflow state."""
        query = """
        mutation StateUpdate($id: String!, $input: WorkflowStateUpdateInput!) {
            workflowStateUpdate(id: $id, input: $input) {
                success
                workflowState { id name type color updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "color", "description", "position"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": state_id, "input": input_data})
        return result["workflowStateUpdate"]["workflowState"]

    def archive_state(self, state_id: str) -> bool:
        """Archive a state."""
        return self._bool_mutation("workflowStateArchive", state_id)

    # =========================================================================
    # Initiatives
    # =========================================================================

    def list_initiatives(
        self,
        limit: int = 50,
        include_archived: bool = False,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List initiatives."""
        query = """
        query ListInitiatives($first: Int, $after: String, $includeArchived: Boolean) {
            initiatives(first: $first, after: $after, includeArchived: $includeArchived) {
                nodes {
                    id name slugId description icon color
                    status sortOrder
                    targetDate
                    owner { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(
            query,
            "initiatives",
            {"includeArchived": include_archived},
            limit=limit,
            fetch_all=fetch_all,
        )

    def get_initiative(self, initiative_id: str) -> dict:
        """Get an initiative by ID."""
        query = """
        query GetInitiative($id: String!) {
            initiative(id: $id) {
                id name slugId description icon color content
                status sortOrder targetDate
                owner { id name }
                projects { nodes { id name state progress } }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": initiative_id})["initiative"]

    def create_initiative(self, name: str, body: dict | None = None, **kwargs) -> dict:
        """Create an initiative."""
        query = """
        mutation InitiativeCreate($input: InitiativeCreateInput!) {
            initiativeCreate(input: $input) {
                success
                initiative { id name slugId createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        for k in ["description", "icon", "color", "status", "targetDate", "ownerId"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["initiativeCreate"]["initiative"]

    def update_initiative(self, initiative_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update an initiative."""
        query = """
        mutation InitiativeUpdate($id: String!, $input: InitiativeUpdateInput!) {
            initiativeUpdate(id: $id, input: $input) {
                success
                initiative { id name updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "description", "icon", "color", "status", "targetDate", "ownerId"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": initiative_id, "input": input_data})
        return result["initiativeUpdate"]["initiative"]

    def archive_initiative(self, initiative_id: str) -> bool:
        """Archive a initiative."""
        return self._bool_mutation("initiativeArchive", initiative_id)

    def unarchive_initiative(self, initiative_id: str) -> bool:
        """Unarchive a initiative."""
        return self._bool_mutation("initiativeUnarchive", initiative_id)

    def delete_initiative(self, initiative_id: str) -> bool:
        """Delete a initiative."""
        return self._bool_mutation("initiativeDelete", initiative_id)

    # =========================================================================
    # Roadmaps
    # =========================================================================

    def list_roadmaps(
        self,
        limit: int = 50,
        include_archived: bool = False,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List roadmaps."""
        query = """
        query ListRoadmaps($first: Int, $after: String, $includeArchived: Boolean) {
            roadmaps(first: $first, after: $after, includeArchived: $includeArchived) {
                nodes {
                    id name slugId description
                    sortOrder
                    owner { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(
            query,
            "roadmaps",
            {"includeArchived": include_archived},
            limit=limit,
            fetch_all=fetch_all,
        )

    def get_roadmap(self, roadmap_id: str) -> dict:
        """Get a roadmap by ID."""
        query = """
        query GetRoadmap($id: String!) {
            roadmap(id: $id) {
                id name slugId description
                sortOrder
                owner { id name }
                projects { nodes { id name state progress } }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": roadmap_id})["roadmap"]

    def create_roadmap(self, name: str, body: dict | None = None, **kwargs) -> dict:
        """Create a roadmap."""
        query = """
        mutation RoadmapCreate($input: RoadmapCreateInput!) {
            roadmapCreate(input: $input) {
                success
                roadmap { id name slugId createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        for k in ["description", "ownerId"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["roadmapCreate"]["roadmap"]

    def update_roadmap(self, roadmap_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a roadmap."""
        query = """
        mutation RoadmapUpdate($id: String!, $input: RoadmapUpdateInput!) {
            roadmapUpdate(id: $id, input: $input) {
                success
                roadmap { id name updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "description", "ownerId"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": roadmap_id, "input": input_data})
        return result["roadmapUpdate"]["roadmap"]

    def delete_roadmap(self, roadmap_id: str) -> bool:
        """Delete a roadmap."""
        return self._bool_mutation("roadmapDelete", roadmap_id)

    def archive_roadmap(self, roadmap_id: str) -> bool:
        """Archive a roadmap."""
        return self._bool_mutation("roadmapArchive", roadmap_id)

    def unarchive_roadmap(self, roadmap_id: str) -> bool:
        """Unarchive a roadmap."""
        return self._bool_mutation("roadmapUnarchive", roadmap_id)

    # =========================================================================
    # Webhooks
    # =========================================================================

    def list_webhooks(self, limit: int = 50, fetch_all: bool = False) -> tuple[list[dict], dict]:
        """List webhooks."""
        query = """
        query ListWebhooks($first: Int, $after: String) {
            webhooks(first: $first, after: $after) {
                nodes {
                    id label url enabled allPublicTeams
                    resourceTypes
                    team { id name key }
                    creator { id name }
                    createdAt updatedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "webhooks", {}, limit=limit, fetch_all=fetch_all)

    def get_webhook(self, webhook_id: str) -> dict:
        """Get a webhook by ID."""
        query = """
        query GetWebhook($id: String!) {
            webhook(id: $id) {
                id label url enabled allPublicTeams secret
                resourceTypes
                team { id name key }
                creator { id name }
                createdAt updatedAt
            }
        }
        """
        return self._execute(query, {"id": webhook_id})["webhook"]

    def create_webhook(
        self,
        url: str,
        label: str | None = None,
        team_id: str | None = None,
        resource_types: list[str] | None = None,
        enabled: bool = True,
        body: dict | None = None,
    ) -> dict:
        """Create a webhook."""
        query = """
        mutation WebhookCreate($input: WebhookCreateInput!) {
            webhookCreate(input: $input) {
                success
                webhook { id label url enabled secret createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"url": url, "enabled": enabled}
        if label:
            input_data["label"] = label
        if team_id:
            input_data["teamId"] = team_id
        if resource_types:
            input_data["resourceTypes"] = resource_types
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["webhookCreate"]["webhook"]

    def update_webhook(self, webhook_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a webhook."""
        query = """
        mutation WebhookUpdate($id: String!, $input: WebhookUpdateInput!) {
            webhookUpdate(id: $id, input: $input) {
                success
                webhook { id label url enabled updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["url", "label", "enabled", "resourceTypes"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": webhook_id, "input": input_data})
        return result["webhookUpdate"]["webhook"]

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        return self._bool_mutation("webhookDelete", webhook_id)

    # =========================================================================
    # Notifications
    # =========================================================================

    def list_notifications(
        self, limit: int = 50, fetch_all: bool = False
    ) -> tuple[list[dict], dict]:
        """List notifications."""
        query = """
        query ListNotifications($first: Int, $after: String) {
            notifications(first: $first, after: $after) {
                nodes {
                    id type readAt snoozedUntilAt
                    createdAt updatedAt archivedAt
                    ... on IssueNotification {
                        issue { id identifier title }
                        comment { id body }
                    }
                    ... on ProjectNotification {
                        project { id name }
                        projectUpdate { id body }
                    }
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "notifications", {}, limit=limit, fetch_all=fetch_all)

    def get_notification(self, notification_id: str) -> dict:
        """Get a notification by ID."""
        query = """
        query GetNotification($id: String!) {
            notification(id: $id) {
                id type readAt snoozedUntilAt
                createdAt updatedAt archivedAt
                ... on IssueNotification {
                    issue { id identifier title }
                    comment { id body }
                }
                ... on ProjectNotification {
                    project { id name }
                }
            }
        }
        """
        return self._execute(query, {"id": notification_id})["notification"]

    def archive_notification(self, notification_id: str) -> bool:
        """Archive a notification."""
        return self._bool_mutation("notificationArchive", notification_id)

    def unarchive_notification(self, notification_id: str) -> bool:
        """Unarchive a notification."""
        return self._bool_mutation("notificationUnarchive", notification_id)

    def mark_all_notifications_read(self) -> bool:
        """Mark all notifications as read."""
        query = """
        mutation { notificationMarkReadAll { success } }
        """
        return self._execute(query)["notificationMarkReadAll"]["success"]

    # =========================================================================
    # Attachments
    # =========================================================================

    def list_attachments(
        self,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List attachments."""
        query = """
        query ListAttachments($first: Int, $after: String) {
            attachments(first: $first, after: $after) {
                nodes {
                    id title subtitle url sourceType
                    issue { id identifier title }
                    creator { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "attachments", {}, limit=limit, fetch_all=fetch_all)

    def get_attachment(self, attachment_id: str) -> dict:
        """Get an attachment by ID."""
        query = """
        query GetAttachment($id: String!) {
            attachment(id: $id) {
                id title subtitle url sourceType metadata
                issue { id identifier title }
                creator { id name }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": attachment_id})["attachment"]

    def create_attachment(
        self,
        issue_id: str,
        url: str,
        title: str | None = None,
        subtitle: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create an attachment."""
        query = """
        mutation AttachmentCreate($input: AttachmentCreateInput!) {
            attachmentCreate(input: $input) {
                success
                attachment { id title url sourceType createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"issueId": issue_id, "url": url}
        if title:
            input_data["title"] = title
        if subtitle:
            input_data["subtitle"] = subtitle
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["attachmentCreate"]["attachment"]

    def delete_attachment(self, attachment_id: str) -> bool:
        """Delete a attachment."""
        return self._bool_mutation("attachmentDelete", attachment_id)

    def link_url_to_issue(self, issue_id: str, url: str, title: str | None = None) -> dict:
        """Link a URL to an issue (auto-detects integration type)."""
        query = """
        mutation AttachmentLinkURL($issueId: String!, $url: String!, $title: String) {
            attachmentLinkURL(issueId: $issueId, url: $url, title: $title) {
                success
                attachment { id title url sourceType createdAt }
            }
        }
        """
        return self._execute(
            query,
            {
                "issueId": issue_id,
                "url": url,
                "title": title,
            },
        )["attachmentLinkURL"]["attachment"]

    # =========================================================================
    # Templates
    # =========================================================================

    def list_templates(self, limit: int = 50, fetch_all: bool = False) -> tuple[list[dict], dict]:
        """List templates."""
        query = """
        query ListTemplates($first: Int, $after: String) {
            templates(first: $first, after: $after) {
                nodes {
                    id name type description
                    team { id name key }
                    creator { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "templates", {}, limit=limit, fetch_all=fetch_all)

    def get_template(self, template_id: str) -> dict:
        """Get a template by ID."""
        query = """
        query GetTemplate($id: String!) {
            template(id: $id) {
                id name type description templateData
                team { id name key }
                creator { id name }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": template_id})["template"]

    def create_template(
        self,
        name: str,
        type: str,
        template_data: dict,
        team_id: str | None = None,
        description: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a template."""
        query = """
        mutation TemplateCreate($input: TemplateCreateInput!) {
            templateCreate(input: $input) {
                success
                template { id name type createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {
            "name": name,
            "type": type,
            "templateData": template_data,
        }
        if team_id:
            input_data["teamId"] = team_id
        if description:
            input_data["description"] = description
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["templateCreate"]["template"]

    def update_template(self, template_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a template."""
        query = """
        mutation TemplateUpdate($id: String!, $input: TemplateUpdateInput!) {
            templateUpdate(id: $id, input: $input) {
                success
                template { id name updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "description", "templateData"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": template_id, "input": input_data})
        return result["templateUpdate"]["template"]

    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        return self._bool_mutation("templateDelete", template_id)

    # =========================================================================
    # Favorites
    # =========================================================================

    def list_favorites(self) -> list[dict]:
        """List user favorites."""
        query = """
        query {
            favorites {
                nodes {
                    id type sortOrder
                    issue { id identifier title }
                    project { id name }
                    cycle { id name number }
                    customView { id name }
                    label { id name }
                    createdAt updatedAt
                }
            }
        }
        """
        return self._execute(query)["favorites"]["nodes"]

    def create_favorite(self, body: dict) -> dict:
        """Create a favorite."""
        query = """
        mutation FavoriteCreate($input: FavoriteCreateInput!) {
            favoriteCreate(input: $input) {
                success
                favorite { id type createdAt }
            }
        }
        """
        result = self._execute(query, {"input": body})
        return result["favoriteCreate"]["favorite"]

    def delete_favorite(self, favorite_id: str) -> bool:
        """Delete a favorite."""
        return self._bool_mutation("favoriteDelete", favorite_id)

    # =========================================================================
    # Organization
    # =========================================================================

    def get_organization(self) -> dict:
        """Get current organization."""
        query = """
        query {
            organization {
                id name urlKey logoUrl
                gitBranchFormat
                gitLinkbackMessagesEnabled
                gitPublicLinkbackMessagesEnabled
                periodUploadVolume
                projectUpdateRemindersHour
                roadmapEnabled
                samlEnabled scimEnabled
                trialEndsAt
                subscription { id type seats }
                allowedAuthServices
                userCount createdAt
            }
        }
        """
        return self._execute(query)["organization"]

    def update_organization(self, body: dict) -> dict:
        """Update organization settings."""
        query = """
        mutation OrganizationUpdate($input: OrganizationUpdateInput!) {
            organizationUpdate(input: $input) {
                success
                organization { id name urlKey updatedAt }
            }
        }
        """
        result = self._execute(query, {"input": body})
        return result["organizationUpdate"]["organization"]

    # =========================================================================
    # Custom Views
    # =========================================================================

    def list_views(self, limit: int = 50, fetch_all: bool = False) -> tuple[list[dict], dict]:
        """List custom views."""
        query = """
        query ListViews($first: Int, $after: String) {
            customViews(first: $first, after: $after) {
                nodes {
                    id name description icon color shared
                    filterData
                    team { id name key }
                    owner { id name }
                    creator { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "customViews", {}, limit=limit, fetch_all=fetch_all)

    def get_view(self, view_id: str) -> dict:
        """Get a custom view by ID."""
        query = """
        query GetView($id: String!) {
            customView(id: $id) {
                id name description icon color shared
                filterData
                team { id name key }
                owner { id name }
                creator { id name }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": view_id})["customView"]

    def create_view(self, name: str, body: dict | None = None, **kwargs) -> dict:
        """Create a custom view."""
        query = """
        mutation ViewCreate($input: CustomViewCreateInput!) {
            customViewCreate(input: $input) {
                success
                customView { id name createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        for k in ["description", "icon", "color", "shared", "filterData", "teamId"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["customViewCreate"]["customView"]

    def update_view(self, view_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a custom view."""
        query = """
        mutation ViewUpdate($id: String!, $input: CustomViewUpdateInput!) {
            customViewUpdate(id: $id, input: $input) {
                success
                customView { id name updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "description", "icon", "color", "shared", "filterData"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": view_id, "input": input_data})
        return result["customViewUpdate"]["customView"]

    def delete_view(self, view_id: str) -> bool:
        """Delete a view."""
        return self._bool_mutation("customViewDelete", view_id)

    # =========================================================================
    # Customers
    # =========================================================================

    def list_customers(
        self,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List customers."""
        query = """
        query ListCustomers($first: Int, $after: String) {
            customers(first: $first, after: $after) {
                nodes {
                    id name externalIds domains logoUrl
                    revenue
                    status { id name }
                    tier { id name }
                    owner { id name }
                    needs { nodes { id body priority } }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "customers", {}, limit=limit, fetch_all=fetch_all)

    def get_customer(self, customer_id: str) -> dict:
        """Get a customer by ID."""
        query = """
        query GetCustomer($id: String!) {
            customer(id: $id) {
                id name externalIds domains logoUrl
                revenue slackChannelId
                status { id name color }
                tier { id name }
                owner { id name }
                needs { nodes { id body priority createdAt } }
                createdAt updatedAt archivedAt
            }
        }
        """
        return self._execute(query, {"id": customer_id})["customer"]

    def create_customer(self, name: str, body: dict | None = None, **kwargs) -> dict:
        """Create a customer."""
        query = """
        mutation CustomerCreate($input: CustomerCreateInput!) {
            customerCreate(input: $input) {
                success
                customer { id name createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        for k in ["domains", "externalIds", "logoUrl", "revenue", "ownerId", "statusId", "tierId"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["customerCreate"]["customer"]

    def update_customer(self, customer_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a customer."""
        query = """
        mutation CustomerUpdate($id: String!, $input: CustomerUpdateInput!) {
            customerUpdate(id: $id, input: $input) {
                success
                customer { id name updatedAt }
            }
        }
        """
        input_data = {}
        for k in [
            "name",
            "domains",
            "externalIds",
            "logoUrl",
            "revenue",
            "ownerId",
            "statusId",
            "tierId",
        ]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": customer_id, "input": input_data})
        return result["customerUpdate"]["customer"]

    def delete_customer(self, customer_id: str) -> bool:
        """Delete a customer."""
        return self._bool_mutation("customerDelete", customer_id)

    # =========================================================================
    # Releases
    # =========================================================================

    def list_releases(
        self,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List releases."""
        query = """
        query ListReleases($first: Int, $after: String) {
            releases(first: $first, after: $after) {
                nodes {
                    id name description
                    status
                    releaseStage { id name }
                    releasePipeline { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "releases", {}, limit=limit, fetch_all=fetch_all)

    def create_release(self, name: str, body: dict) -> dict:
        """Create a release."""
        query = """
        mutation ReleaseCreate($input: ReleaseCreateInput!) {
            releaseCreate(input: $input) {
                success
                release { id name status createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name}
        input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["releaseCreate"]["release"]

    def update_release(self, release_id: str, body: dict) -> dict:
        """Update a release."""
        query = """
        mutation ReleaseUpdate($id: String!, $input: ReleaseUpdateInput!) {
            releaseUpdate(id: $id, input: $input) {
                success
                release { id name status updatedAt }
            }
        }
        """
        result = self._execute(query, {"id": release_id, "input": body})
        return result["releaseUpdate"]["release"]

    def delete_release(self, release_id: str) -> bool:
        """Delete a release."""
        return self._bool_mutation("releaseDelete", release_id)

    def archive_release(self, release_id: str) -> bool:
        """Archive a release."""
        return self._bool_mutation("releaseArchive", release_id)

    # =========================================================================
    # Project Milestones
    # =========================================================================

    def list_milestones(
        self,
        project_id: str | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List project milestones."""
        query = """
        query ListMilestones($first: Int, $after: String, $filter: ProjectMilestoneFilter) {
            projectMilestones(first: $first, after: $after, filter: $filter) {
                nodes {
                    id name description sortOrder targetDate
                    project { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {}
        if project_id:
            variables["filter"] = {"project": {"id": {"eq": project_id}}}
        return self._paginate(
            query, "projectMilestones", variables, limit=limit, fetch_all=fetch_all
        )

    def create_milestone(
        self,
        name: str,
        project_id: str,
        target_date: str | None = None,
        description: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a project milestone."""
        query = """
        mutation MilestoneCreate($input: ProjectMilestoneCreateInput!) {
            projectMilestoneCreate(input: $input) {
                success
                projectMilestone { id name targetDate createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"name": name, "projectId": project_id}
        if target_date:
            input_data["targetDate"] = target_date
        if description:
            input_data["description"] = description
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["projectMilestoneCreate"]["projectMilestone"]

    def update_milestone(self, milestone_id: str, body: dict | None = None, **kwargs) -> dict:
        """Update a project milestone."""
        query = """
        mutation MilestoneUpdate($id: String!, $input: ProjectMilestoneUpdateInput!) {
            projectMilestoneUpdate(id: $id, input: $input) {
                success
                projectMilestone { id name updatedAt }
            }
        }
        """
        input_data = {}
        for k in ["name", "description", "targetDate", "sortOrder"]:
            if k in kwargs and kwargs[k] is not None:
                input_data[k] = kwargs[k]
        if body:
            input_data.update(body)
        result = self._execute(query, {"id": milestone_id, "input": input_data})
        return result["projectMilestoneUpdate"]["projectMilestone"]

    def delete_milestone(self, milestone_id: str) -> bool:
        """Delete a milestone."""
        return self._bool_mutation("projectMilestoneDelete", milestone_id)

    # =========================================================================
    # Issue Relations
    # =========================================================================

    def list_issue_relations(
        self,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List issue relations."""
        query = """
        query ListIssueRelations($first: Int, $after: String) {
            issueRelations(first: $first, after: $after) {
                nodes {
                    id type
                    issue { id identifier title }
                    relatedIssue { id identifier title }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "issueRelations", {}, limit=limit, fetch_all=fetch_all)

    def create_issue_relation(
        self,
        issue_id: str,
        related_issue_id: str,
        type: str,
    ) -> dict:
        """Create an issue relation.

        Types: blocks, duplicate, related
        """
        query = """
        mutation IssueRelationCreate($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                success
                issueRelation { id type createdAt }
            }
        }
        """
        result = self._execute(
            query,
            {
                "input": {
                    "issueId": issue_id,
                    "relatedIssueId": related_issue_id,
                    "type": type,
                }
            },
        )
        return result["issueRelationCreate"]["issueRelation"]

    def delete_issue_relation(self, relation_id: str) -> bool:
        """Delete a issue relation."""
        return self._bool_mutation("issueRelationDelete", relation_id)

    # =========================================================================
    # Team Memberships
    # =========================================================================

    def list_team_memberships(
        self,
        team_id: str | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List team memberships."""
        query = """
        query ListTeamMemberships($first: Int, $after: String) {
            teamMemberships(first: $first, after: $after) {
                nodes {
                    id owner sortOrder
                    user { id name email }
                    team { id name key }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "teamMemberships", {}, limit=limit, fetch_all=fetch_all)

    def create_team_membership(self, team_id: str, user_id: str) -> dict:
        """Add a user to a team."""
        query = """
        mutation TeamMembershipCreate($input: TeamMembershipCreateInput!) {
            teamMembershipCreate(input: $input) {
                success
                teamMembership { id createdAt }
            }
        }
        """
        result = self._execute(query, {"input": {"teamId": team_id, "userId": user_id}})
        return result["teamMembershipCreate"]["teamMembership"]

    def delete_team_membership(self, membership_id: str) -> bool:
        """Delete a team membership."""
        return self._bool_mutation("teamMembershipDelete", membership_id)

    # =========================================================================
    # Project Updates
    # =========================================================================

    def list_project_updates(
        self,
        project_id: str | None = None,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List project updates."""
        query = """
        query ListProjectUpdates($first: Int, $after: String, $filter: ProjectUpdateFilter) {
            projectUpdates(first: $first, after: $after, filter: $filter) {
                nodes {
                    id body health
                    project { id name }
                    user { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        variables: dict[str, Any] = {}
        if project_id:
            variables["filter"] = {"project": {"id": {"eq": project_id}}}
        return self._paginate(query, "projectUpdates", variables, limit=limit, fetch_all=fetch_all)

    def create_project_update(
        self,
        project_id: str,
        body_text: str,
        health: str | None = None,
        body: dict | None = None,
    ) -> dict:
        """Create a project update."""
        query = """
        mutation ProjectUpdateCreate($input: ProjectUpdateCreateInput!) {
            projectUpdateCreate(input: $input) {
                success
                projectUpdate { id body health createdAt }
            }
        }
        """
        input_data: dict[str, Any] = {"projectId": project_id, "body": body_text}
        if health:
            input_data["health"] = health
        if body:
            input_data.update(body)
        result = self._execute(query, {"input": input_data})
        return result["projectUpdateCreate"]["projectUpdate"]

    def delete_project_update(self, update_id: str) -> bool:
        """Delete a project update."""
        return self._bool_mutation("projectUpdateDelete", update_id)

    # =========================================================================
    # Emojis
    # =========================================================================

    def list_emojis(self, limit: int = 50, fetch_all: bool = False) -> tuple[list[dict], dict]:
        """List custom emojis."""
        query = """
        query ListEmojis($first: Int, $after: String) {
            emojis(first: $first, after: $after) {
                nodes {
                    id name url
                    creator { id name }
                    createdAt updatedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "emojis", {}, limit=limit, fetch_all=fetch_all)

    def create_emoji(self, name: str, url: str) -> dict:
        """Create a custom emoji."""
        query = """
        mutation EmojiCreate($input: EmojiCreateInput!) {
            emojiCreate(input: $input) {
                success
                emoji { id name url createdAt }
            }
        }
        """
        result = self._execute(query, {"input": {"name": name, "url": url}})
        return result["emojiCreate"]["emoji"]

    def delete_emoji(self, emoji_id: str) -> bool:
        """Delete a emoji."""
        return self._bool_mutation("emojiDelete", emoji_id)

    # =========================================================================
    # Integrations
    # =========================================================================

    def list_integrations(
        self, limit: int = 50, fetch_all: bool = False
    ) -> tuple[list[dict], dict]:
        """List integrations."""
        query = """
        query ListIntegrations($first: Int, $after: String) {
            integrations(first: $first, after: $after) {
                nodes {
                    id service
                    team { id name key }
                    creator { id name }
                    createdAt updatedAt archivedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "integrations", {}, limit=limit, fetch_all=fetch_all)

    # =========================================================================
    # Audit Entries
    # =========================================================================

    def list_audit_entries(
        self,
        limit: int = 50,
        fetch_all: bool = False,
    ) -> tuple[list[dict], dict]:
        """List audit log entries."""
        query = """
        query ListAuditEntries($first: Int, $after: String) {
            auditEntries(first: $first, after: $after) {
                nodes {
                    id type
                    actor { id name }
                    metadata
                    createdAt updatedAt
                }
                pageInfo { hasNextPage endCursor }
            }
        }
        """
        return self._paginate(query, "auditEntries", {}, limit=limit, fetch_all=fetch_all)
