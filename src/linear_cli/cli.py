"""Linear CLI - Forma Protocol compliant CLI entry point."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from linear_cli import __version__
from linear_cli.cache import ResponseCache
from linear_cli.client import Client, LinearAPIError, RateLimitError
from linear_cli.config import (
    delete_api_key,
    get_api_key,
    get_auth_source,
    get_auth_status,
    save_api_key,
)

# Forma standard exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_AUTH_REQUIRED = 2
EXIT_NOT_FOUND = 3
EXIT_VALIDATION = 4
EXIT_FORBIDDEN = 5
EXIT_RATE_LIMITED = 6
EXIT_CONFLICT = 7

# ---------------------------------------------------------------------------
# Application root
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="linear",
    help="Linear project management CLI — Forma Protocol compliant.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# All human-readable output goes to stderr so JSON on stdout is uncontaminated.
console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{2,64}$")


def _validate_id(value: str, label: str = "id") -> str:
    """Guard against obviously malformed IDs (agent safety)."""
    if not value or not _ID_RE.match(value):
        _error(f"Invalid {label}: {value!r}", code=4)
    return value


def _output_json(data: object) -> None:
    """Write JSON envelope to stdout."""
    print(json.dumps(data, default=str))


def _error(message: str, code: int = 1) -> None:
    """Print error to stderr and exit with the given code."""
    console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(code)


def _error_json(code_str: str, message: str, exit_code: int = 1) -> None:
    """Print JSON error envelope to stdout and exit."""
    _output_json({"error": {"code": code_str, "message": message}})
    raise typer.Exit(exit_code)


def _handle_api_error(exc: LinearAPIError, json_output: bool) -> None:
    """Translate API errors to Forma exit codes and output."""
    if isinstance(exc, RateLimitError):
        if json_output:
            _error_json("rate_limited", str(exc), exit_code=6)
        _error(f"Rate limited: {exc}", code=6)

    status = exc.status_code
    message = str(exc)

    if status == 401 or status == 403:
        if json_output:
            _error_json("forbidden", message, exit_code=5)
        _error(message, code=5)
    elif status == 404:
        if json_output:
            _error_json("not_found", message, exit_code=3)
        _error(message, code=3)
    elif status == 409:
        if json_output:
            _error_json("conflict", message, exit_code=7)
        _error(message, code=7)
    elif status == 422:
        if json_output:
            _error_json("validation", message, exit_code=4)
        _error(message, code=4)
    else:
        if json_output:
            _error_json("api_error", message, exit_code=1)
        _error(message, code=1)


def _require_auth(json_output: bool = False) -> None:
    """Exit 2 (auth_required) if no API key is configured."""
    if not get_api_key():
        if json_output:
            _error_json(
                "auth_required", "No API key configured. Run: linear auth login", exit_code=2
            )
        console.print("[yellow]Not authenticated.[/yellow] Run: [bold]linear auth login[/bold]")
        raise typer.Exit(2)


def _filter_fields(nodes: list[dict], fields: str | None) -> list[dict]:
    """Return nodes with only the requested fields, if --fields is specified."""
    if not fields:
        return nodes
    keys = [f.strip() for f in fields.split(",") if f.strip()]
    if not keys:
        return nodes
    return [{k: node.get(k) for k in keys} for node in nodes]


def _filter_fields_single(node: dict, fields: str | None) -> dict:
    """Filter a single dict's fields."""
    if not fields:
        return node
    return _filter_fields([node], fields)[0]


def _parse_body(body: str | None, json_output: bool) -> dict | None:
    """Parse --body JSON string, exit with validation error if invalid."""
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        if json_output:
            _error_json("validation", f"Invalid JSON in --body: {exc}", exit_code=4)
        _error(f"Invalid JSON in --body: {exc}", code=4)


def _get_client(json_output: bool) -> Client:
    """Require auth and return an API client."""
    _require_auth(json_output)
    return Client()


def _output_list_json(nodes: list[dict], fields: str | None, page_info: dict) -> None:
    """Output standard list JSON envelope."""
    _output_json(
        {"data": _filter_fields(nodes, fields), "meta": {"count": len(nodes), **page_info}}
    )


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"linear {__version__}")
        raise typer.Exit()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# Cache TTLs in seconds, keyed by operation name.
TTLS: dict[str, int] = {
    "list_teams": 1800,
    "list_labels": 1800,
    "list_users": 1800,
    "list_issues": 300,
    "list_projects": 300,
    "list_cycles": 300,
}
DEFAULT_TTL = 300


# ---------------------------------------------------------------------------
# Root options
# ---------------------------------------------------------------------------


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", "-V", callback=_version_callback, is_eager=True, help="Show version"
        ),
    ] = None,
) -> None:
    """Linear CLI — Forma Protocol."""


# ===========================================================================
# 1. auth
# ===========================================================================

auth_app = typer.Typer(help="Authentication commands.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")


@auth_app.command("login")
def auth_login(
    key: Annotated[
        str | None, typer.Option("--key", "-k", help="API key (omit for interactive prompt)")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Save a Linear API key.

    Examples:
        linear auth login --key lin_api_xxxxxxxx
        linear auth login
    """
    if not key:
        key = typer.prompt("Linear API key", hide_input=True)
    if not key or not key.strip():
        if json_output:
            _error_json("validation", "API key cannot be empty", exit_code=4)
        _error("API key cannot be empty", code=4)

    key = key.strip()
    # Validate the key by calling the API.
    try:
        client = Client(api_key=key)
        viewer = client.viewer()
    except LinearAPIError as e:
        if json_output:
            _error_json("auth_failed", f"Invalid API key: {e}", exit_code=2)
        _error(f"Authentication failed: {e}", code=2)

    save_api_key(key)

    if json_output:
        _output_json({"data": {"authenticated": True, "user": viewer}})
        return

    name = viewer.get("name", viewer.get("email", "?"))
    console.print(f"[green]Authenticated[/green] as [bold]{name}[/bold]")


@auth_app.command("status")
def auth_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Show current authentication status.

    Examples:
        linear auth status
        linear auth status --json
    """
    status = get_auth_status()
    source = get_auth_source()
    api_key = get_api_key()

    authenticated = bool(api_key)
    viewer: dict | None = None

    if authenticated:
        try:
            viewer = Client().viewer()
        except LinearAPIError:
            authenticated = False

    if json_output:
        _output_json(
            {
                "data": {
                    "authenticated": authenticated,
                    "source": source,
                    "user": viewer,
                    **status,
                }
            }
        )
        return

    if authenticated and viewer:
        uname = viewer.get("name")
        uemail = viewer.get("email")
        console.print(f"[green]Authenticated[/green] as [bold]{uname}[/bold] ({uemail})")
        console.print(f"Source: {source}")
    else:
        console.print("[yellow]Not authenticated.[/yellow] Run: [bold]linear auth login[/bold]")


@auth_app.command("logout")
def auth_logout(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Remove the stored API key.

    Examples:
        linear auth logout
    """
    delete_api_key()
    if json_output:
        _output_json({"data": {"authenticated": False}})
        return
    console.print("[green]Logged out.[/green] API key removed.")


# ===========================================================================
# 2. cache
# ===========================================================================

cache_app = typer.Typer(help="Cache management commands.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")


@cache_app.command("status")
def cache_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Show cache statistics.

    Examples:
        linear cache status
        linear cache status --json
    """
    stats = ResponseCache().stats()
    if json_output:
        _output_json({"data": stats})
        return
    console.print(f"Cache directory: {stats['cache_dir']}")
    console.print(
        f"Entries: {stats['entries']} ({stats['active']} active, {stats['expired']} expired)"
    )
    console.print(f"Size: {stats['size_bytes']} bytes")


@cache_app.command("clear")
def cache_clear(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Clear all cached responses.

    Examples:
        linear cache clear
    """
    count = ResponseCache().clear()
    if json_output:
        _output_json({"data": {"cleared": count}})
        return
    console.print(f"[green]Cleared[/green] {count} cache entries.")


# ===========================================================================
# update  (top-level, protocol section 23)
# ===========================================================================


@app.command()
def update(
    check: Annotated[bool, typer.Option("--check", help="Check only, do not install")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Check for updates and self-update from the git remote.

    Examples:
        linear update --check
        linear update --check --json
        linear update
    """
    from linear_cli.update import do_update, find_tool_dir, get_latest_tag, version_gt

    current = __version__
    tool_dir = find_tool_dir()
    latest = get_latest_tag(tool_dir)
    available = bool(latest and version_gt(latest, current))

    if json_output:
        print(
            json.dumps(
                {
                    "data": {
                        "current": current,
                        "latest": latest or current,
                        "update_available": available,
                    },
                    "meta": {"timestamp": _now_iso()},
                }
            )
        )
        return

    console.print(f"Current: v{current}")
    console.print(f"Latest:  v{latest or current}")

    if not available:
        console.print("Already up to date.")
        return

    if check:
        console.print("Update available. Run: linear update")
        return

    console.print("Updating...")
    if do_update(tool_dir):
        console.print(f"[green]Updated to v{latest}[/green]")
    else:
        console.print(
            "[red]Update failed.[/red] Try: git pull && uv pip install -e .",
            style="red",
        )
        raise typer.Exit(1)


# ===========================================================================
# describe  (top-level, protocol section 09)
# ===========================================================================


def _typer_type_name(annotation) -> str:
    """Return a human-readable type name for a Typer parameter annotation."""
    import typing

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", None)

    if origin is typing.Union and args:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _typer_type_name(non_none[0])
    if annotation is str or annotation == "str":
        return "string"
    if annotation is int or annotation == "int":
        return "integer"
    if annotation is bool or annotation == "bool":
        return "boolean"
    if annotation is float or annotation == "float":
        return "number"
    return "string"


def _introspect_app(typer_app: typer.Typer, prefix: str = "") -> list[dict]:
    """Recursively introspect a Typer app and return command descriptors."""
    import inspect

    commands: list[dict] = []

    for registered in typer_app.registered_commands:
        func = registered.callback
        if func is None:
            continue

        cmd_name = registered.name or func.__name__.replace("_", "-")
        full_name = f"{prefix} {cmd_name}".strip() if prefix else cmd_name
        doc = inspect.getdoc(func) or ""
        description = doc.split("\n")[0]

        options: list[dict] = []
        arguments: list[dict] = []
        sig = inspect.signature(func)

        for param_name, param in sig.parameters.items():
            annotation = param.annotation

            # Unwrap Annotated[T, typer.Option(...)] / Annotated[T, typer.Argument(...)]
            inner_type = annotation
            typer_info = None

            if hasattr(annotation, "__metadata__"):
                # typing.Annotated
                inner_type = annotation.__args__[0]
                for meta in annotation.__metadata__:
                    if isinstance(meta, (typer.models.OptionInfo, typer.models.ArgumentInfo)):
                        typer_info = meta
                        break

            if isinstance(typer_info, typer.models.ArgumentInfo):
                arguments.append(
                    {
                        "name": param_name,
                        "type": _typer_type_name(inner_type),
                        "required": param.default is inspect.Parameter.empty
                        or (hasattr(typer_info, "default") and typer_info.default is ...),
                        "help": typer_info.help or "",
                    }
                )
            elif isinstance(typer_info, typer.models.OptionInfo):
                flag_name = (
                    typer_info.param_decls[0]
                    if typer_info.param_decls
                    else f"--{param_name.replace('_', '-')}"
                )
                opt_default = typer_info.default
                options.append(
                    {
                        "name": flag_name,
                        "type": _typer_type_name(inner_type),
                        "required": False,
                        "default": None if opt_default is ... else opt_default,
                        "help": typer_info.help or "",
                    }
                )

        commands.append(
            {
                "name": full_name,
                "description": description,
                "options": options,
                "arguments": arguments,
            }
        )

    for group in typer_app.registered_groups:
        sub_app = group.typer_instance
        group_name = group.name or ""
        if sub_app is not None:
            commands.extend(_introspect_app(sub_app, prefix=group_name))

    return commands


@app.command()
def describe(
    resource: Annotated[str | None, typer.Argument(help="Resource group to filter")] = None,
    action: Annotated[str | None, typer.Argument(help="Action to filter")] = None,
) -> None:
    """
    Output machine-readable JSON describing available commands.

    Examples:
        linear describe
        linear describe issues
        linear describe issues list
    """
    all_commands = _introspect_app(app)

    if resource:
        all_commands = [c for c in all_commands if c["name"].startswith(resource)]
    if action:
        all_commands = [c for c in all_commands if c["name"] == f"{resource} {action}"]

    print(
        json.dumps(
            {
                "tool": "linear",
                "version": __version__,
                "protocol": "forma/1.2",
                "commands": all_commands,
            }
        )
    )


# ===========================================================================
# 3. issues
# ===========================================================================

issues_app = typer.Typer(help="Issue commands.", no_args_is_help=True)
app.add_typer(issues_app, name="issues")


@issues_app.command("list")
def issues_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    all_results: Annotated[bool, typer.Option("--all", help="Fetch all pages")] = False,
    fields: Annotated[str | None, typer.Option("--fields", help="Comma-separated fields")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    team: Annotated[str | None, typer.Option("--team", help="Filter by team ID")] = None,
    assignee: Annotated[
        str | None, typer.Option("--assignee", help="Filter by assignee ID")
    ] = None,
    state: Annotated[str | None, typer.Option("--state", help="Filter by state name")] = None,
    state_type: Annotated[
        str | None,
        typer.Option(
            "--state-type",
            help="Filter by state type: backlog, unstarted, started, completed, canceled",
        ),
    ] = None,
    label: Annotated[str | None, typer.Option("--label", help="Filter by label name")] = None,
    priority: Annotated[
        int | None, typer.Option("--priority", help="Filter by priority (0-4)")
    ] = None,
    project: Annotated[str | None, typer.Option("--project", help="Filter by project ID")] = None,
    cycle: Annotated[str | None, typer.Option("--cycle", help="Filter by cycle ID")] = None,
    archived: Annotated[bool, typer.Option("--archived", help="Include archived issues")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache for this call")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force refresh and update cache")
    ] = False,
) -> None:
    """
    List issues.

    Examples:
        linear issues list
        linear issues list --team TEAM_ID --state "In Progress"
        linear issues list --state-type started --json
        linear issues list --json | jq '.data[0]'
        linear issues list --all --fields id,identifier,title
    """
    _require_auth(json_output)

    cache = ResponseCache()
    cache_key = ResponseCache.key(
        "list_issues",
        str(team),
        str(assignee),
        str(state),
        str(state_type),
        str(label),
        str(priority),
        str(project),
        str(cycle),
        str(archived),
        str(limit),
        str(all_results),
    )

    nodes: list[dict] | None = None
    page_info: dict = {}

    if not no_cache and not refresh:
        cached = cache.get(cache_key, ttl=TTLS["list_issues"])
        if cached is not None:
            nodes = cached.get("nodes", [])
            page_info = cached.get("page_info", {})

    if nodes is None:
        client = Client()
        try:
            nodes, page_info = client.list_issues(
                team_id=team,
                assignee_id=assignee,
                state_name=state,
                state_type=state_type,
                label_name=label,
                priority=priority,
                project_id=project,
                cycle_id=cycle,
                limit=limit,
                include_archived=archived,
                fetch_all=all_results,
            )
        except LinearAPIError as e:
            _handle_api_error(e, json_output)
            return
        if not no_cache:
            cache.set(cache_key, {"nodes": nodes, "page_info": page_info})

    if json_output:
        _output_json(
            {
                "data": _filter_fields(nodes, fields),
                "meta": {"count": len(nodes), **page_info},
            }
        )
        return

    table = Table(title=f"Issues ({len(nodes)})", show_lines=False)
    table.add_column("Identifier", style="cyan", no_wrap=True)
    table.add_column("Title")
    table.add_column("State", style="yellow")
    table.add_column("Assignee")
    table.add_column("Priority")
    table.add_column("Team", style="dim")

    for node in nodes:
        table.add_row(
            node.get("identifier", ""),
            node.get("title", ""),
            (node.get("state") or {}).get("name", ""),
            (node.get("assignee") or {}).get("name", ""),
            node.get("priorityLabel", ""),
            (node.get("team") or {}).get("key", ""),
        )
    console.print(table)


@issues_app.command("get")
def issues_get(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier (e.g. LIN-123)")],
    fields: Annotated[str | None, typer.Option("--fields", help="Comma-separated fields")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Get a single issue.

    Examples:
        linear issues get LIN-123
        linear issues get LIN-123 --json
    """
    client = _get_client(json_output)
    try:
        node = client.get_issue(issue_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return

    console.print(f"[bold cyan]{node.get('identifier')}[/bold cyan] {node.get('title')}")
    console.print(f"State: {(node.get('state') or {}).get('name', '')}")
    console.print(f"Assignee: {(node.get('assignee') or {}).get('name', 'Unassigned')}")
    console.print(f"Priority: {node.get('priorityLabel', '')}")
    console.print(f"URL: {node.get('url', '')}")
    if node.get("description"):
        console.print(f"\n{node['description']}")


@issues_app.command("create")
def issues_create(
    title: Annotated[str, typer.Argument(help="Issue title")],
    team_id: Annotated[str, typer.Option("--team", help="Team ID (required)")],
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="Issue description")
    ] = None,
    assignee_id: Annotated[str | None, typer.Option("--assignee", help="Assignee user ID")] = None,
    state_id: Annotated[str | None, typer.Option("--state-id", help="Workflow state ID")] = None,
    priority: Annotated[int | None, typer.Option("--priority", "-p", help="Priority 0-4")] = None,
    project_id: Annotated[str | None, typer.Option("--project", help="Project ID")] = None,
    label_ids: Annotated[
        str | None, typer.Option("--labels", help="Comma-separated label IDs")
    ] = None,
    due_date: Annotated[
        str | None, typer.Option("--due-date", help="Due date (YYYY-MM-DD)")
    ] = None,
    estimate: Annotated[int | None, typer.Option("--estimate", help="Story point estimate")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON string")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print payload without sending")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Create a new issue.

    Examples:
        linear issues create "Fix login bug" --team TEAM_ID
        linear issues create "Task" --team TEAM_ID --priority 1 --json
    """
    _require_auth(json_output)
    _validate_id(team_id, "team-id")

    label_id_list = (
        [lid.strip() for lid in label_ids.split(",") if lid.strip()] if label_ids else None
    )
    extra = _parse_body(body, json_output)

    if dry_run:
        payload = {
            "title": title,
            "teamId": team_id,
            "description": description,
            "assigneeId": assignee_id,
            "stateId": state_id,
            "priority": priority,
            "projectId": project_id,
            "labelIds": label_id_list,
            "dueDate": due_date,
            "estimate": estimate,
        }
        if extra:
            payload.update(extra)
        _output_json({"dry_run": True, "payload": payload})
        return

    client = Client()
    try:
        node = client.create_issue(
            title=title,
            team_id=team_id,
            description=description,
            assignee_id=assignee_id,
            state_id=state_id,
            priority=priority,
            label_ids=label_id_list,
            project_id=project_id,
            estimate=estimate,
            due_date=due_date,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json({"data": node})
        return
    ident = node.get("identifier")
    console.print(f"[green]Created[/green] [bold cyan]{ident}[/bold cyan]: {node.get('title')}")
    console.print(f"URL: {node.get('url')}")


@issues_app.command("update")
def issues_update(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier")],
    title: Annotated[str | None, typer.Option("--title", help="New title")] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="New description")
    ] = None,
    assignee_id: Annotated[str | None, typer.Option("--assignee", help="Assignee user ID")] = None,
    state_id: Annotated[str | None, typer.Option("--state-id", help="Workflow state ID")] = None,
    priority: Annotated[int | None, typer.Option("--priority", "-p", help="Priority 0-4")] = None,
    project_id: Annotated[str | None, typer.Option("--project", help="Project ID")] = None,
    due_date: Annotated[
        str | None, typer.Option("--due-date", help="Due date (YYYY-MM-DD)")
    ] = None,
    estimate: Annotated[int | None, typer.Option("--estimate", help="Story point estimate")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON string")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print payload without sending")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Update an issue.

    Examples:
        linear issues update LIN-123 --title "New title"
        linear issues update LIN-123 --priority 2 --json
    """
    _require_auth(json_output)
    extra = _parse_body(body, json_output)

    if dry_run:
        _output_json(
            {
                "dry_run": True,
                "id": issue_id,
                "payload": {
                    "title": title,
                    "description": description,
                    "assigneeId": assignee_id,
                    "stateId": state_id,
                    "priority": priority,
                    "projectId": project_id,
                    "dueDate": due_date,
                    "estimate": estimate,
                },
            }
        )
        return

    client = Client()
    try:
        node = client.update_issue(
            issue_id,
            body=extra,
            title=title,
            description=description,
            assignee_id=assignee_id,
            state_id=state_id,
            priority=priority,
            project_id=project_id,
            due_date=due_date,
            estimate=estimate,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json({"data": node})
        return
    ident = node.get("identifier")
    console.print(f"[green]Updated[/green] [bold cyan]{ident}[/bold cyan]: {node.get('title')}")


@issues_app.command("delete")
def issues_delete(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier")],
    confirm: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print what would be deleted")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Delete an issue.

    Examples:
        linear issues delete LIN-123 --yes
    """
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": issue_id})
        return
    if not confirm:
        typer.confirm(f"Delete issue {issue_id}?", abort=True)

    client = Client()
    try:
        ok = client.delete_issue(issue_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json({"data": {"deleted": ok, "id": issue_id}})
        return
    console.print(f"[green]Deleted[/green] issue {issue_id}.")


@issues_app.command("archive")
def issues_archive(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print what would be archived")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Archive an issue."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": issue_id})
        return
    client = Client()
    try:
        ok = client.archive_issue(issue_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": issue_id}})
        return
    console.print(f"[green]Archived[/green] issue {issue_id}.")


@issues_app.command("unarchive")
def issues_unarchive(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print what would be unarchived")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Unarchive an issue."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": issue_id})
        return
    client = Client()
    try:
        ok = client.unarchive_issue(issue_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"unarchived": ok, "id": issue_id}})
        return
    console.print(f"[green]Unarchived[/green] issue {issue_id}.")


@issues_app.command("search")
def issues_search(
    query: Annotated[str, typer.Argument(help="Search text")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    all_results: Annotated[bool, typer.Option("--all", help="Fetch all pages")] = False,
    fields: Annotated[str | None, typer.Option("--fields", help="Comma-separated fields")] = None,
    archived: Annotated[bool, typer.Option("--archived", help="Include archived issues")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    Search issues by text.

    Examples:
        linear issues search "login bug"
        linear issues search "api" --json | jq '.data[].identifier'
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.search_issues(query, limit=limit, include_archived=archived)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json(
            {
                "data": _filter_fields(nodes, fields),
                "meta": {"count": len(nodes), **page_info},
            }
        )
        return

    table = Table(title=f"Search results ({len(nodes)})", show_lines=False)
    table.add_column("Identifier", style="cyan", no_wrap=True)
    table.add_column("Title")
    table.add_column("State", style="yellow")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            node.get("identifier", ""),
            node.get("title", ""),
            (node.get("state") or {}).get("name", ""),
            (node.get("team") or {}).get("key", ""),
        )
    console.print(table)


@issues_app.command("add-label")
def issues_add_label(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier")],
    label_id: Annotated[str, typer.Argument(help="Label ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without sending")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Add a label to an issue."""
    _require_auth(json_output)
    _validate_id(label_id, "label-id")
    if dry_run:
        _output_json({"dry_run": True, "issueId": issue_id, "labelId": label_id})
        return
    client = Client()
    try:
        ok = client.add_issue_label(issue_id, label_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"success": ok}})
        return
    console.print(f"[green]Added[/green] label {label_id} to issue {issue_id}.")


@issues_app.command("remove-label")
def issues_remove_label(
    issue_id: Annotated[str, typer.Argument(help="Issue ID or identifier")],
    label_id: Annotated[str, typer.Argument(help="Label ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without sending")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Remove a label from an issue."""
    _require_auth(json_output)
    _validate_id(label_id, "label-id")
    if dry_run:
        _output_json({"dry_run": True, "issueId": issue_id, "labelId": label_id})
        return
    client = Client()
    try:
        ok = client.remove_issue_label(issue_id, label_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"success": ok}})
        return
    console.print(f"[green]Removed[/green] label {label_id} from issue {issue_id}.")


# ===========================================================================
# 4. projects
# ===========================================================================

projects_app = typer.Typer(help="Project commands.", no_args_is_help=True)
app.add_typer(projects_app, name="projects")


@projects_app.command("list")
def projects_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    all_results: Annotated[bool, typer.Option("--all", help="Fetch all pages")] = False,
    fields: Annotated[str | None, typer.Option("--fields", help="Comma-separated fields")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    team: Annotated[str | None, typer.Option("--team", help="Filter by team ID")] = None,
    state: Annotated[str | None, typer.Option("--state", help="Filter by state")] = None,
    archived: Annotated[bool, typer.Option("--archived", help="Include archived projects")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache for this call")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force refresh and update cache")
    ] = False,
) -> None:
    """
    List projects.

    Examples:
        linear projects list
        linear projects list --state backlog --json
    """
    _require_auth(json_output)

    cache = ResponseCache()
    cache_key = ResponseCache.key("list_projects", str(team), str(state), str(archived), str(limit))

    nodes: list[dict] | None = None
    page_info: dict = {}

    if not no_cache and not refresh:
        cached = cache.get(cache_key, ttl=TTLS["list_projects"])
        if cached is not None:
            nodes = cached.get("nodes", [])
            page_info = cached.get("page_info", {})

    if nodes is None:
        client = Client()
        try:
            nodes, page_info = client.list_projects(
                team_id=team,
                state=state,
                limit=limit,
                include_archived=archived,
                fetch_all=all_results,
            )
        except LinearAPIError as e:
            _handle_api_error(e, json_output)
            return
        if not no_cache:
            cache.set(cache_key, {"nodes": nodes, "page_info": page_info})

    if json_output:
        _output_json(
            {
                "data": _filter_fields(nodes, fields),
                "meta": {"count": len(nodes), **page_info},
            }
        )
        return

    table = Table(title=f"Projects ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("State", style="yellow")
    table.add_column("Progress")
    table.add_column("Lead")
    table.add_column("Target Date", style="dim")
    for node in nodes:
        progress = node.get("progress", 0)
        table.add_row(
            node.get("name", ""),
            node.get("state", ""),
            f"{progress * 100:.0f}%" if isinstance(progress, float) else str(progress),
            (node.get("lead") or {}).get("name", ""),
            node.get("targetDate", "") or "",
        )
    console.print(table)


@projects_app.command("get")
def projects_get(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    fields: Annotated[str | None, typer.Option("--fields", help="Comma-separated fields")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get a project by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_project(project_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold] ({node.get('state')})")
    console.print(f"URL: {node.get('url', '')}")
    if node.get("description"):
        console.print(node["description"])


@projects_app.command("create")
def projects_create(
    name: Annotated[str, typer.Argument(help="Project name")],
    team_ids: Annotated[str, typer.Option("--teams", help="Comma-separated team IDs (required)")],
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    state: Annotated[str | None, typer.Option("--state")] = None,
    lead_id: Annotated[str | None, typer.Option("--lead")] = None,
    start_date: Annotated[str | None, typer.Option("--start-date")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
    priority: Annotated[int | None, typer.Option("--priority")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a project."""
    _require_auth(json_output)
    team_id_list = [t.strip() for t in team_ids.split(",") if t.strip()]
    extra = _parse_body(body, json_output)

    if dry_run:
        _output_json(
            {
                "dry_run": True,
                "payload": {
                    "name": name,
                    "teamIds": team_id_list,
                    "description": description,
                    "state": state,
                    "leadId": lead_id,
                },
            }
        )
        return

    client = Client()
    try:
        node = client.create_project(
            name=name,
            team_ids=team_id_list,
            description=description,
            state=state,
            lead_id=lead_id,
            start_date=start_date,
            target_date=target_date,
            priority=priority,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] project [bold]{node.get('name')}[/bold]")
    console.print(f"URL: {node.get('url')}")


@projects_app.command("update")
def projects_update(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    state: Annotated[str | None, typer.Option("--state")] = None,
    lead_id: Annotated[str | None, typer.Option("--lead")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
    priority: Annotated[int | None, typer.Option("--priority")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a project."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)

    if dry_run:
        _output_json({"dry_run": True, "id": project_id})
        return

    client = Client()
    try:
        node = client.update_project(
            project_id,
            body=extra,
            name=name,
            description=description,
            state=state,
            lead_id=lead_id,
            target_date=target_date,
            priority=priority,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return

    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] project [bold]{node.get('name')}[/bold]")


@projects_app.command("delete")
def projects_delete(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a project."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": project_id})
        return
    if not confirm:
        typer.confirm(f"Delete project {project_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_project(project_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": project_id}})
        return
    console.print(f"[green]Deleted[/green] project {project_id}.")


@projects_app.command("archive")
def projects_archive(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive a project."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": project_id})
        return
    client = Client()
    try:
        ok = client.archive_project(project_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": project_id}})
        return
    console.print(f"[green]Archived[/green] project {project_id}.")


@projects_app.command("unarchive")
def projects_unarchive(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Unarchive a project."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": project_id})
        return
    client = Client()
    try:
        ok = client.unarchive_project(project_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"unarchived": ok, "id": project_id}})
        return
    console.print(f"[green]Unarchived[/green] project {project_id}.")


@projects_app.command("search")
def projects_search(
    query: Annotated[str, typer.Argument(help="Search text")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search projects by text."""
    client = _get_client(json_output)
    try:
        nodes, page_info = client.search_projects(query, limit=limit)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json(
            {
                "data": _filter_fields(nodes, fields),
                "meta": {"count": len(nodes), **page_info},
            }
        )
        return
    table = Table(title=f"Projects ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("State", style="yellow")
    table.add_column("URL", style="dim")
    for node in nodes:
        table.add_row(node.get("name", ""), node.get("state", ""), node.get("url", ""))
    console.print(table)


# ===========================================================================
# 5. teams
# ===========================================================================

teams_app = typer.Typer(help="Team commands.", no_args_is_help=True)
app.add_typer(teams_app, name="teams")


@teams_app.command("list")
def teams_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    archived: Annotated[bool, typer.Option("--archived")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache for this call")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force refresh and update cache")
    ] = False,
) -> None:
    """
    List teams.

    Examples:
        linear teams list
        linear teams list --json | jq '.data[].key'
    """
    _require_auth(json_output)

    cache = ResponseCache()
    cache_key = ResponseCache.key("list_teams", str(archived), str(limit))

    nodes: list[dict] | None = None
    page_info: dict = {}

    if not no_cache and not refresh:
        cached = cache.get(cache_key, ttl=TTLS["list_teams"])
        if cached is not None:
            nodes = cached.get("nodes", [])
            page_info = cached.get("page_info", {})

    if nodes is None:
        client = Client()
        try:
            nodes, page_info = client.list_teams(
                limit=limit, include_archived=archived, fetch_all=all_results
            )
        except LinearAPIError as e:
            _handle_api_error(e, json_output)
            return
        if not no_cache:
            cache.set(cache_key, {"nodes": nodes, "page_info": page_info})

    if json_output:
        _output_list_json(nodes, fields, page_info)
        return

    table = Table(title=f"Teams ({len(nodes)})", show_lines=False)
    table.add_column("Key", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Issues")
    table.add_column("Private")
    for node in nodes:
        table.add_row(
            node.get("key", ""),
            node.get("name", ""),
            str(node.get("issueCount", 0)),
            "Yes" if node.get("private") else "No",
        )
    console.print(table)


@teams_app.command("get")
def teams_get(
    team_id: Annotated[str, typer.Argument(help="Team ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a team by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_team(team_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold cyan]{node.get('key')}[/bold cyan] {node.get('name')}")
    console.print(f"Issues: {node.get('issueCount', 0)}")
    console.print(f"Private: {node.get('private', False)}")


@teams_app.command("create")
def teams_create(
    name: Annotated[str, typer.Argument(help="Team name")],
    key: Annotated[str | None, typer.Option("--key", help="Team identifier key")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    private: Annotated[bool, typer.Option("--private/--no-private")] = False,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a team."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, "key": key}})
        return
    client = Client()
    try:
        node = client.create_team(
            name=name, key=key, body=extra, description=description, private=private
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(
        f"[green]Created[/green] team [bold]{node.get('name')}[/bold] ({node.get('key')})"
    )


@teams_app.command("update")
def teams_update(
    team_id: Annotated[str, typer.Argument(help="Team ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    key: Annotated[str | None, typer.Option("--key")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    private: Annotated[bool | None, typer.Option("--private/--no-private")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a team."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": team_id})
        return
    client = Client()
    try:
        node = client.update_team(
            team_id, body=extra, name=name, key=key, description=description, private=private
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] team [bold]{node.get('name')}[/bold]")


@teams_app.command("delete")
def teams_delete(
    team_id: Annotated[str, typer.Argument(help="Team ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a team."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": team_id})
        return
    if not confirm:
        typer.confirm(f"Delete team {team_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_team(team_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": team_id}})
        return
    console.print(f"[green]Deleted[/green] team {team_id}.")


# ===========================================================================
# 6. cycles
# ===========================================================================

cycles_app = typer.Typer(help="Cycle commands.", no_args_is_help=True)
app.add_typer(cycles_app, name="cycles")


@cycles_app.command("list")
def cycles_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    team: Annotated[str | None, typer.Option("--team", help="Filter by team ID")] = None,
    archived: Annotated[bool, typer.Option("--archived")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache for this call")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force refresh and update cache")
    ] = False,
) -> None:
    """
    List cycles.

    Examples:
        linear cycles list --team TEAM_ID
        linear cycles list --json
    """
    _require_auth(json_output)

    cache = ResponseCache()
    cache_key = ResponseCache.key("list_cycles", str(team), str(archived), str(limit))

    nodes: list[dict] | None = None
    page_info: dict = {}

    if not no_cache and not refresh:
        cached = cache.get(cache_key, ttl=TTLS["list_cycles"])
        if cached is not None:
            nodes = cached.get("nodes", [])
            page_info = cached.get("page_info", {})

    if nodes is None:
        client = Client()
        try:
            nodes, page_info = client.list_cycles(
                team_id=team, limit=limit, include_archived=archived, fetch_all=all_results
            )
        except LinearAPIError as e:
            _handle_api_error(e, json_output)
            return
        if not no_cache:
            cache.set(cache_key, {"nodes": nodes, "page_info": page_info})

    if json_output:
        _output_list_json(nodes, fields, page_info)
        return

    table = Table(title=f"Cycles ({len(nodes)})", show_lines=False)
    table.add_column("#", style="cyan")
    table.add_column("Name")
    table.add_column("Starts At")
    table.add_column("Ends At")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            str(node.get("number", "")),
            node.get("name") or "",
            (node.get("startsAt") or "")[:10],
            (node.get("endsAt") or "")[:10],
            (node.get("team") or {}).get("key", ""),
        )
    console.print(table)


@cycles_app.command("get")
def cycles_get(
    cycle_id: Annotated[str, typer.Argument(help="Cycle ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a cycle by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_cycle(cycle_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"Cycle #{node.get('number')} {node.get('name') or ''}")
    console.print(f"Starts: {node.get('startsAt', '')[:10]}  Ends: {node.get('endsAt', '')[:10]}")


@cycles_app.command("create")
def cycles_create(
    team_id: Annotated[str, typer.Argument(help="Team ID")],
    starts_at: Annotated[str, typer.Argument(help="Start date (YYYY-MM-DD)")],
    ends_at: Annotated[str, typer.Argument(help="End date (YYYY-MM-DD)")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a cycle."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json(
            {
                "dry_run": True,
                "payload": {"teamId": team_id, "startsAt": starts_at, "endsAt": ends_at},
            }
        )
        return
    client = Client()
    try:
        node = client.create_cycle(
            team_id=team_id,
            starts_at=starts_at,
            ends_at=ends_at,
            name=name,
            description=description,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(
        f"[green]Created[/green] cycle #{node.get('number')}"
        f" for team {(node.get('team') or {}).get('key', '')}"
    )


@cycles_app.command("update")
def cycles_update(
    cycle_id: Annotated[str, typer.Argument(help="Cycle ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    starts_at: Annotated[str | None, typer.Option("--starts-at")] = None,
    ends_at: Annotated[str | None, typer.Option("--ends-at")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a cycle."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": cycle_id})
        return
    client = Client()
    try:
        node = client.update_cycle(
            cycle_id,
            body=extra,
            name=name,
            description=description,
            startsAt=starts_at,
            endsAt=ends_at,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] cycle #{node.get('number')}")


@cycles_app.command("archive")
def cycles_archive(
    cycle_id: Annotated[str, typer.Argument(help="Cycle ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive a cycle."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": cycle_id})
        return
    client = Client()
    try:
        ok = client.archive_cycle(cycle_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": cycle_id}})
        return
    console.print(f"[green]Archived[/green] cycle {cycle_id}.")


# ===========================================================================
# 7. labels
# ===========================================================================

labels_app = typer.Typer(help="Label commands.", no_args_is_help=True)
app.add_typer(labels_app, name="labels")


@labels_app.command("list")
def labels_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    team: Annotated[str | None, typer.Option("--team", help="Filter by team ID")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache for this call")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force refresh and update cache")
    ] = False,
) -> None:
    """
    List labels.

    Examples:
        linear labels list
        linear labels list --team TEAM_ID --json
    """
    _require_auth(json_output)

    cache = ResponseCache()
    cache_key = ResponseCache.key("list_labels", str(team), str(limit))

    nodes: list[dict] | None = None
    page_info: dict = {}

    if not no_cache and not refresh:
        cached = cache.get(cache_key, ttl=TTLS["list_labels"])
        if cached is not None:
            nodes = cached.get("nodes", [])
            page_info = cached.get("page_info", {})

    if nodes is None:
        client = Client()
        try:
            nodes, page_info = client.list_labels(team_id=team, limit=limit, fetch_all=all_results)
        except LinearAPIError as e:
            _handle_api_error(e, json_output)
            return
        if not no_cache:
            cache.set(cache_key, {"nodes": nodes, "page_info": page_info})

    if json_output:
        _output_list_json(nodes, fields, page_info)
        return

    table = Table(title=f"Labels ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Color")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""), node.get("color", ""), (node.get("team") or {}).get("key", "")
        )
    console.print(table)


@labels_app.command("get")
def labels_get(
    label_id: Annotated[str, typer.Argument(help="Label ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a label by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_label(label_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold]  Color: {node.get('color', '')}")


@labels_app.command("create")
def labels_create(
    name: Annotated[str, typer.Argument(help="Label name")],
    team_id: Annotated[str | None, typer.Option("--team")] = None,
    color: Annotated[str | None, typer.Option("--color")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    parent_id: Annotated[str | None, typer.Option("--parent")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a label."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, "teamId": team_id}})
        return
    client = Client()
    try:
        node = client.create_label(
            name=name,
            team_id=team_id,
            color=color,
            description=description,
            parent_id=parent_id,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] label [bold]{node.get('name')}[/bold]")


@labels_app.command("update")
def labels_update(
    label_id: Annotated[str, typer.Argument(help="Label ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    color: Annotated[str | None, typer.Option("--color")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a label."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": label_id})
        return
    client = Client()
    try:
        node = client.update_label(
            label_id, body=extra, name=name, color=color, description=description
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] label [bold]{node.get('name')}[/bold]")


@labels_app.command("delete")
def labels_delete(
    label_id: Annotated[str, typer.Argument(help="Label ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a label."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": label_id})
        return
    if not confirm:
        typer.confirm(f"Delete label {label_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_label(label_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": label_id}})
        return
    console.print(f"[green]Deleted[/green] label {label_id}.")


# ===========================================================================
# 8. users
# ===========================================================================

users_app = typer.Typer(help="User commands.", no_args_is_help=True)
app.add_typer(users_app, name="users")


@users_app.command("list")
def users_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    archived: Annotated[bool, typer.Option("--archived")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Bypass cache for this call")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force refresh and update cache")
    ] = False,
) -> None:
    """
    List users.

    Examples:
        linear users list
        linear users list --json | jq '.data[].email'
    """
    _require_auth(json_output)

    cache = ResponseCache()
    cache_key = ResponseCache.key("list_users", str(archived), str(limit))

    nodes: list[dict] | None = None
    page_info: dict = {}

    if not no_cache and not refresh:
        cached = cache.get(cache_key, ttl=TTLS["list_users"])
        if cached is not None:
            nodes = cached.get("nodes", [])
            page_info = cached.get("page_info", {})

    if nodes is None:
        client = Client()
        try:
            nodes, page_info = client.list_users(
                limit=limit, include_archived=archived, fetch_all=all_results
            )
        except LinearAPIError as e:
            _handle_api_error(e, json_output)
            return
        if not no_cache:
            cache.set(cache_key, {"nodes": nodes, "page_info": page_info})

    if json_output:
        _output_list_json(nodes, fields, page_info)
        return

    table = Table(title=f"Users ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Email")
    table.add_column("Active")
    table.add_column("Admin")
    for node in nodes:
        table.add_row(
            node.get("name", ""),
            node.get("email", ""),
            "Yes" if node.get("active") else "No",
            "Yes" if node.get("admin") else "No",
        )
    console.print(table)


@users_app.command("get")
def users_get(
    user_id: Annotated[str, typer.Argument(help="User ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a user by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_user(user_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold] ({node.get('email')})")
    console.print(f"Active: {node.get('active')}  Admin: {node.get('admin')}")


@users_app.command("me")
def users_me(
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    Get the currently authenticated user (viewer).

    Examples:
        linear users me
        linear users me --json
    """
    client = _get_client(json_output)
    try:
        node = client.viewer()
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold] ({node.get('email')})")
    console.print(
        f"Admin: {node.get('admin')}  Org: {(node.get('organization') or {}).get('name', '')}"
    )


@users_app.command("update")
def users_update(
    user_id: Annotated[str, typer.Argument(help="User ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    display_name: Annotated[str | None, typer.Option("--display-name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    timezone: Annotated[str | None, typer.Option("--timezone")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a user."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": user_id})
        return
    client = Client()
    try:
        node = client.update_user(
            user_id,
            body=extra,
            name=name,
            displayName=display_name,
            description=description,
            timezone=timezone,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] user [bold]{node.get('name')}[/bold]")


@users_app.command("suspend")
def users_suspend(
    user_id: Annotated[str, typer.Argument(help="User ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Suspend a user."""
    _require_auth(json_output)
    _validate_id(user_id, "user-id")
    if dry_run:
        _output_json({"dry_run": True, "id": user_id})
        return
    client = Client()
    try:
        ok = client.suspend_user(user_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"suspended": ok, "id": user_id}})
        return
    console.print(f"[green]Suspended[/green] user {user_id}.")


@users_app.command("unsuspend")
def users_unsuspend(
    user_id: Annotated[str, typer.Argument(help="User ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Unsuspend a user."""
    _require_auth(json_output)
    _validate_id(user_id, "user-id")
    if dry_run:
        _output_json({"dry_run": True, "id": user_id})
        return
    client = Client()
    try:
        ok = client.unsuspend_user(user_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"unsuspended": ok, "id": user_id}})
        return
    console.print(f"[green]Unsuspended[/green] user {user_id}.")


# ===========================================================================
# 9. comments
# ===========================================================================

comments_app = typer.Typer(help="Comment commands.", no_args_is_help=True)
app.add_typer(comments_app, name="comments")


@comments_app.command("list")
def comments_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    issue: Annotated[str | None, typer.Option("--issue", help="Filter by issue ID")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List comments.

    Examples:
        linear comments list --issue ISSUE_ID
        linear comments list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_comments(issue_id=issue, limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Comments ({len(nodes)})", show_lines=False)
    table.add_column("Author")
    table.add_column("Body")
    table.add_column("Created", style="dim")
    for node in nodes:
        body_preview = (node.get("body") or "")[:80].replace("\n", " ")
        table.add_row(
            (node.get("user") or {}).get("name", ""),
            body_preview,
            (node.get("createdAt") or "")[:10],
        )
    console.print(table)


@comments_app.command("create")
def comments_create(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    body_text: Annotated[str, typer.Argument(help="Comment body")],
    parent_id: Annotated[
        str | None, typer.Option("--parent", help="Parent comment ID for replies")
    ] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a comment on an issue."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"issueId": issue_id, "body": body_text}})
        return
    client = Client()
    try:
        node = client.create_comment(
            issue_id=issue_id, body_text=body_text, parent_id=parent_id, body=extra
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] comment {node.get('id')}")
    console.print(f"URL: {node.get('url')}")


@comments_app.command("update")
def comments_update(
    comment_id: Annotated[str, typer.Argument(help="Comment ID")],
    body_text: Annotated[str, typer.Argument(help="New body text")],
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON string")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a comment."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": comment_id})
        return
    client = Client()
    try:
        node = client.update_comment(comment_id, body_text, body=extra)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] comment {node.get('id')}")


@comments_app.command("delete")
def comments_delete(
    comment_id: Annotated[str, typer.Argument(help="Comment ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a comment."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": comment_id})
        return
    if not confirm:
        typer.confirm(f"Delete comment {comment_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_comment(comment_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": comment_id}})
        return
    console.print(f"[green]Deleted[/green] comment {comment_id}.")


@comments_app.command("resolve")
def comments_resolve(
    comment_id: Annotated[str, typer.Argument(help="Comment ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Resolve a comment."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": comment_id})
        return
    client = Client()
    try:
        node = client.resolve_comment(comment_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Resolved[/green] comment {comment_id}.")


@comments_app.command("unresolve")
def comments_unresolve(
    comment_id: Annotated[str, typer.Argument(help="Comment ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Unresolve a comment."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": comment_id})
        return
    client = Client()
    try:
        node = client.unresolve_comment(comment_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Unresolved[/green] comment {comment_id}.")


# ===========================================================================
# 10. documents
# ===========================================================================

documents_app = typer.Typer(help="Document commands.", no_args_is_help=True)
app.add_typer(documents_app, name="documents")


@documents_app.command("list")
def documents_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List documents.

    Examples:
        linear documents list
        linear documents list --json | jq '.data[].title'
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_documents(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Documents ({len(nodes)})", show_lines=False)
    table.add_column("Title", style="bold")
    table.add_column("Project")
    table.add_column("Creator")
    table.add_column("Updated", style="dim")
    for node in nodes:
        table.add_row(
            node.get("title", ""),
            (node.get("project") or {}).get("name", ""),
            (node.get("creator") or {}).get("name", ""),
            (node.get("updatedAt") or "")[:10],
        )
    console.print(table)


@documents_app.command("get")
def documents_get(
    doc_id: Annotated[str, typer.Argument(help="Document ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a document by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_document(doc_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('title')}[/bold]")
    console.print(f"URL: {node.get('url', '')}")
    if node.get("content"):
        console.print(f"\n{node['content'][:500]}")


@documents_app.command("create")
def documents_create(
    title: Annotated[str, typer.Argument(help="Document title")],
    content: Annotated[str | None, typer.Option("--content", "-c")] = None,
    project_id: Annotated[str | None, typer.Option("--project")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a document."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"title": title, "projectId": project_id}})
        return
    client = Client()
    try:
        node = client.create_document(
            title=title, content=content, project_id=project_id, body=extra
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] document [bold]{node.get('title')}[/bold]")
    console.print(f"URL: {node.get('url')}")


@documents_app.command("update")
def documents_update(
    doc_id: Annotated[str, typer.Argument(help="Document ID")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    content: Annotated[str | None, typer.Option("--content", "-c")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a document."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": doc_id})
        return
    client = Client()
    try:
        node = client.update_document(doc_id, body=extra, title=title, content=content)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] document [bold]{node.get('title')}[/bold]")


@documents_app.command("delete")
def documents_delete(
    doc_id: Annotated[str, typer.Argument(help="Document ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a document."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": doc_id})
        return
    if not confirm:
        typer.confirm(f"Delete document {doc_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_document(doc_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": doc_id}})
        return
    console.print(f"[green]Deleted[/green] document {doc_id}.")


@documents_app.command("search")
def documents_search(
    query: Annotated[str, typer.Argument(help="Search text")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search documents by text."""
    client = _get_client(json_output)
    try:
        nodes, page_info = client.search_documents(query, limit=limit)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Documents ({len(nodes)})", show_lines=False)
    table.add_column("Title", style="bold")
    table.add_column("URL", style="dim")
    for node in nodes:
        table.add_row(node.get("title", ""), node.get("url", ""))
    console.print(table)


# ===========================================================================
# 11. initiatives
# ===========================================================================

initiatives_app = typer.Typer(help="Initiative commands.", no_args_is_help=True)
app.add_typer(initiatives_app, name="initiatives")


@initiatives_app.command("list")
def initiatives_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    archived: Annotated[bool, typer.Option("--archived")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List initiatives.

    Examples:
        linear initiatives list
        linear initiatives list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_initiatives(
            limit=limit, include_archived=archived, fetch_all=all_results
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Initiatives ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Owner")
    table.add_column("Target Date", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""),
            node.get("status", ""),
            (node.get("owner") or {}).get("name", ""),
            node.get("targetDate", "") or "",
        )
    console.print(table)


@initiatives_app.command("get")
def initiatives_get(
    initiative_id: Annotated[str, typer.Argument(help="Initiative ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get an initiative by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_initiative(initiative_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold] ({node.get('status')})")
    if node.get("description"):
        console.print(node["description"])


@initiatives_app.command("create")
def initiatives_create(
    name: Annotated[str, typer.Argument(help="Initiative name")],
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create an initiative."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name}})
        return
    client = Client()
    try:
        node = client.create_initiative(
            name=name,
            body=extra,
            description=description,
            status=status,
            targetDate=target_date,
            ownerId=owner_id,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] initiative [bold]{node.get('name')}[/bold]")


@initiatives_app.command("update")
def initiatives_update(
    initiative_id: Annotated[str, typer.Argument(help="Initiative ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update an initiative."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": initiative_id})
        return
    client = Client()
    try:
        node = client.update_initiative(
            initiative_id,
            body=extra,
            name=name,
            description=description,
            status=status,
            targetDate=target_date,
            ownerId=owner_id,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] initiative [bold]{node.get('name')}[/bold]")


@initiatives_app.command("delete")
def initiatives_delete(
    initiative_id: Annotated[str, typer.Argument(help="Initiative ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete an initiative."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": initiative_id})
        return
    if not confirm:
        typer.confirm(f"Delete initiative {initiative_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_initiative(initiative_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": initiative_id}})
        return
    console.print(f"[green]Deleted[/green] initiative {initiative_id}.")


@initiatives_app.command("archive")
def initiatives_archive(
    initiative_id: Annotated[str, typer.Argument(help="Initiative ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive an initiative."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": initiative_id})
        return
    client = Client()
    try:
        ok = client.archive_initiative(initiative_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": initiative_id}})
        return
    console.print(f"[green]Archived[/green] initiative {initiative_id}.")


@initiatives_app.command("unarchive")
def initiatives_unarchive(
    initiative_id: Annotated[str, typer.Argument(help="Initiative ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Unarchive an initiative."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": initiative_id})
        return
    client = Client()
    try:
        ok = client.unarchive_initiative(initiative_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"unarchived": ok, "id": initiative_id}})
        return
    console.print(f"[green]Unarchived[/green] initiative {initiative_id}.")


# ===========================================================================
# 12. roadmaps
# ===========================================================================

roadmaps_app = typer.Typer(help="Roadmap commands.", no_args_is_help=True)
app.add_typer(roadmaps_app, name="roadmaps")


@roadmaps_app.command("list")
def roadmaps_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    archived: Annotated[bool, typer.Option("--archived")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List roadmaps.

    Examples:
        linear roadmaps list
        linear roadmaps list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_roadmaps(
            limit=limit, include_archived=archived, fetch_all=all_results
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Roadmaps ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Owner")
    table.add_column("Updated", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""),
            (node.get("owner") or {}).get("name", ""),
            (node.get("updatedAt") or "")[:10],
        )
    console.print(table)


@roadmaps_app.command("get")
def roadmaps_get(
    roadmap_id: Annotated[str, typer.Argument(help="Roadmap ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a roadmap by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_roadmap(roadmap_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold]")
    if node.get("description"):
        console.print(node["description"])


@roadmaps_app.command("create")
def roadmaps_create(
    name: Annotated[str, typer.Argument(help="Roadmap name")],
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a roadmap."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name}})
        return
    client = Client()
    try:
        node = client.create_roadmap(
            name=name, body=extra, description=description, ownerId=owner_id
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] roadmap [bold]{node.get('name')}[/bold]")


@roadmaps_app.command("update")
def roadmaps_update(
    roadmap_id: Annotated[str, typer.Argument(help="Roadmap ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a roadmap."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": roadmap_id})
        return
    client = Client()
    try:
        node = client.update_roadmap(
            roadmap_id, body=extra, name=name, description=description, ownerId=owner_id
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] roadmap [bold]{node.get('name')}[/bold]")


@roadmaps_app.command("delete")
def roadmaps_delete(
    roadmap_id: Annotated[str, typer.Argument(help="Roadmap ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a roadmap."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": roadmap_id})
        return
    if not confirm:
        typer.confirm(f"Delete roadmap {roadmap_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_roadmap(roadmap_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": roadmap_id}})
        return
    console.print(f"[green]Deleted[/green] roadmap {roadmap_id}.")


@roadmaps_app.command("archive")
def roadmaps_archive(
    roadmap_id: Annotated[str, typer.Argument(help="Roadmap ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive a roadmap."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": roadmap_id})
        return
    client = Client()
    try:
        ok = client.archive_roadmap(roadmap_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": roadmap_id}})
        return
    console.print(f"[green]Archived[/green] roadmap {roadmap_id}.")


@roadmaps_app.command("unarchive")
def roadmaps_unarchive(
    roadmap_id: Annotated[str, typer.Argument(help="Roadmap ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Unarchive a roadmap."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": roadmap_id})
        return
    client = Client()
    try:
        ok = client.unarchive_roadmap(roadmap_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"unarchived": ok, "id": roadmap_id}})
        return
    console.print(f"[green]Unarchived[/green] roadmap {roadmap_id}.")


# ===========================================================================
# 13. webhooks
# ===========================================================================

webhooks_app = typer.Typer(help="Webhook commands.", no_args_is_help=True)
app.add_typer(webhooks_app, name="webhooks")


@webhooks_app.command("list")
def webhooks_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List webhooks.

    Examples:
        linear webhooks list
        linear webhooks list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_webhooks(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Webhooks ({len(nodes)})", show_lines=False)
    table.add_column("Label")
    table.add_column("URL")
    table.add_column("Enabled")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            node.get("label", "") or "",
            node.get("url", ""),
            "Yes" if node.get("enabled") else "No",
            (node.get("team") or {}).get("key", ""),
        )
    console.print(table)


@webhooks_app.command("get")
def webhooks_get(
    webhook_id: Annotated[str, typer.Argument(help="Webhook ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a webhook by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_webhook(webhook_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('label') or node.get('id')}[/bold]")
    console.print(f"URL: {node.get('url')}")
    console.print(f"Enabled: {node.get('enabled')}")


@webhooks_app.command("create")
def webhooks_create(
    url: Annotated[str, typer.Argument(help="Webhook URL")],
    label: Annotated[str | None, typer.Option("--label")] = None,
    team_id: Annotated[str | None, typer.Option("--team")] = None,
    resource_types: Annotated[
        str | None, typer.Option("--resource-types", help="Comma-separated resource types")
    ] = None,
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a webhook."""
    _require_auth(json_output)
    rt_list = (
        [r.strip() for r in resource_types.split(",") if r.strip()] if resource_types else None
    )
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"url": url, "label": label, "enabled": enabled}})
        return
    client = Client()
    try:
        node = client.create_webhook(
            url=url,
            label=label,
            team_id=team_id,
            resource_types=rt_list,
            enabled=enabled,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] webhook {node.get('id')}")
    console.print(f"URL: {node.get('url')}")


@webhooks_app.command("update")
def webhooks_update(
    webhook_id: Annotated[str, typer.Argument(help="Webhook ID")],
    url: Annotated[str | None, typer.Option("--url")] = None,
    label: Annotated[str | None, typer.Option("--label")] = None,
    enabled: Annotated[bool | None, typer.Option("--enabled/--disabled")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a webhook."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": webhook_id})
        return
    client = Client()
    try:
        node = client.update_webhook(webhook_id, body=extra, url=url, label=label, enabled=enabled)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] webhook {node.get('id')}")


@webhooks_app.command("delete")
def webhooks_delete(
    webhook_id: Annotated[str, typer.Argument(help="Webhook ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a webhook."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": webhook_id})
        return
    if not confirm:
        typer.confirm(f"Delete webhook {webhook_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_webhook(webhook_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": webhook_id}})
        return
    console.print(f"[green]Deleted[/green] webhook {webhook_id}.")


# ===========================================================================
# 14. states
# ===========================================================================

states_app = typer.Typer(help="Workflow state commands.", no_args_is_help=True)
app.add_typer(states_app, name="states")


@states_app.command("list")
def states_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    team: Annotated[str | None, typer.Option("--team", help="Filter by team ID")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List workflow states.

    Examples:
        linear states list --team TEAM_ID
        linear states list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_states(team_id=team, limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"States ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Color")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""),
            node.get("type", ""),
            node.get("color", ""),
            (node.get("team") or {}).get("key", ""),
        )
    console.print(table)


@states_app.command("create")
def states_create(
    name: Annotated[str, typer.Argument(help="State name")],
    team_id: Annotated[str, typer.Option("--team", help="Team ID (required)")],
    state_type: Annotated[
        str,
        typer.Option(
            "--type", help="State type: triage/backlog/unstarted/started/completed/cancelled"
        ),
    ],
    color: Annotated[str | None, typer.Option("--color")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    position: Annotated[float | None, typer.Option("--position")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a workflow state."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json(
            {"dry_run": True, "payload": {"name": name, "teamId": team_id, "type": state_type}}
        )
        return
    client = Client()
    try:
        node = client.create_state(
            name=name,
            team_id=team_id,
            type=state_type,
            color=color,
            description=description,
            position=position,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(
        f"[green]Created[/green] state [bold]{node.get('name')}[/bold] ({node.get('type')})"
    )


@states_app.command("update")
def states_update(
    state_id: Annotated[str, typer.Argument(help="State ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    color: Annotated[str | None, typer.Option("--color")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    position: Annotated[float | None, typer.Option("--position")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a workflow state."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": state_id})
        return
    client = Client()
    try:
        node = client.update_state(
            state_id, body=extra, name=name, color=color, description=description, position=position
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] state [bold]{node.get('name')}[/bold]")


@states_app.command("archive")
def states_archive(
    state_id: Annotated[str, typer.Argument(help="State ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive a workflow state."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": state_id})
        return
    client = Client()
    try:
        ok = client.archive_state(state_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": state_id}})
        return
    console.print(f"[green]Archived[/green] state {state_id}.")


# ===========================================================================
# 15. customers
# ===========================================================================

customers_app = typer.Typer(help="Customer commands.", no_args_is_help=True)
app.add_typer(customers_app, name="customers")


@customers_app.command("list")
def customers_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List customers.

    Examples:
        linear customers list
        linear customers list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_customers(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Customers ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Domains")
    table.add_column("Owner")
    for node in nodes:
        domains = ", ".join(node.get("domains") or [])
        table.add_row(node.get("name", ""), domains, (node.get("owner") or {}).get("name", ""))
    console.print(table)


@customers_app.command("get")
def customers_get(
    customer_id: Annotated[str, typer.Argument(help="Customer ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a customer by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_customer(customer_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold]")
    console.print(f"Domains: {', '.join(node.get('domains') or [])}")


@customers_app.command("create")
def customers_create(
    name: Annotated[str, typer.Argument(help="Customer name")],
    domains: Annotated[
        str | None, typer.Option("--domains", help="Comma-separated domains")
    ] = None,
    owner_id: Annotated[str | None, typer.Option("--owner")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a customer."""
    _require_auth(json_output)
    domain_list = [d.strip() for d in domains.split(",") if d.strip()] if domains else None
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, "domains": domain_list}})
        return
    client = Client()
    try:
        node = client.create_customer(name=name, body=extra, domains=domain_list, ownerId=owner_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] customer [bold]{node.get('name')}[/bold]")


@customers_app.command("update")
def customers_update(
    customer_id: Annotated[str, typer.Argument(help="Customer ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    domains: Annotated[str | None, typer.Option("--domains")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a customer."""
    _require_auth(json_output)
    domain_list = [d.strip() for d in domains.split(",") if d.strip()] if domains else None
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": customer_id})
        return
    client = Client()
    try:
        node = client.update_customer(
            customer_id, body=extra, name=name, domains=domain_list, ownerId=owner_id
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] customer [bold]{node.get('name')}[/bold]")


@customers_app.command("delete")
def customers_delete(
    customer_id: Annotated[str, typer.Argument(help="Customer ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a customer."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": customer_id})
        return
    if not confirm:
        typer.confirm(f"Delete customer {customer_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_customer(customer_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": customer_id}})
        return
    console.print(f"[green]Deleted[/green] customer {customer_id}.")


# ===========================================================================
# 16. attachments
# ===========================================================================

attachments_app = typer.Typer(help="Attachment commands.", no_args_is_help=True)
app.add_typer(attachments_app, name="attachments")


@attachments_app.command("list")
def attachments_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List attachments.

    Examples:
        linear attachments list
        linear attachments list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_attachments(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Attachments ({len(nodes)})", show_lines=False)
    table.add_column("Title")
    table.add_column("URL")
    table.add_column("Source")
    table.add_column("Issue", style="dim")
    for node in nodes:
        table.add_row(
            node.get("title", "") or "",
            node.get("url", ""),
            node.get("sourceType", "") or "",
            (node.get("issue") or {}).get("identifier", ""),
        )
    console.print(table)


@attachments_app.command("get")
def attachments_get(
    attachment_id: Annotated[str, typer.Argument(help="Attachment ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get an attachment by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_attachment(attachment_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('title') or node.get('id')}[/bold]")
    console.print(f"URL: {node.get('url')}")


@attachments_app.command("create")
def attachments_create(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    url: Annotated[str, typer.Argument(help="Attachment URL")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    subtitle: Annotated[str | None, typer.Option("--subtitle")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create an attachment on an issue."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json(
            {"dry_run": True, "payload": {"issueId": issue_id, "url": url, "title": title}}
        )
        return
    client = Client()
    try:
        node = client.create_attachment(
            issue_id=issue_id, url=url, title=title, subtitle=subtitle, body=extra
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] attachment {node.get('id')}")


@attachments_app.command("delete")
def attachments_delete(
    attachment_id: Annotated[str, typer.Argument(help="Attachment ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete an attachment."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": attachment_id})
        return
    if not confirm:
        typer.confirm(f"Delete attachment {attachment_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_attachment(attachment_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": attachment_id}})
        return
    console.print(f"[green]Deleted[/green] attachment {attachment_id}.")


@attachments_app.command("link-url")
def attachments_link_url(
    issue_id: Annotated[str, typer.Argument(help="Issue ID")],
    url: Annotated[str, typer.Argument(help="URL to link")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Link a URL to an issue (auto-detects integration type)."""
    _require_auth(json_output)
    if dry_run:
        _output_json(
            {"dry_run": True, "payload": {"issueId": issue_id, "url": url, "title": title}}
        )
        return
    client = Client()
    try:
        node = client.link_url_to_issue(issue_id=issue_id, url=url, title=title)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Linked[/green] URL to issue {issue_id}")


# ===========================================================================
# 17. notifications
# ===========================================================================

notifications_app = typer.Typer(help="Notification commands.", no_args_is_help=True)
app.add_typer(notifications_app, name="notifications")


@notifications_app.command("list")
def notifications_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List notifications.

    Examples:
        linear notifications list
        linear notifications list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_notifications(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Notifications ({len(nodes)})", show_lines=False)
    table.add_column("Type")
    table.add_column("Read")
    table.add_column("Created", style="dim")
    for node in nodes:
        table.add_row(
            node.get("type", ""),
            "Yes" if node.get("readAt") else "No",
            (node.get("createdAt") or "")[:10],
        )
    console.print(table)


@notifications_app.command("get")
def notifications_get(
    notification_id: Annotated[str, typer.Argument(help="Notification ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a notification by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_notification(notification_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"Type: {node.get('type')}  Read: {bool(node.get('readAt'))}")


@notifications_app.command("archive")
def notifications_archive(
    notification_id: Annotated[str, typer.Argument(help="Notification ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive a notification."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": notification_id})
        return
    client = Client()
    try:
        ok = client.archive_notification(notification_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": notification_id}})
        return
    console.print(f"[green]Archived[/green] notification {notification_id}.")


@notifications_app.command("unarchive")
def notifications_unarchive(
    notification_id: Annotated[str, typer.Argument(help="Notification ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Unarchive a notification."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": notification_id})
        return
    client = Client()
    try:
        ok = client.unarchive_notification(notification_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"unarchived": ok, "id": notification_id}})
        return
    console.print(f"[green]Unarchived[/green] notification {notification_id}.")


@notifications_app.command("mark-read")
def notifications_mark_read(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mark all notifications as read."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True})
        return
    client = Client()
    try:
        ok = client.mark_all_notifications_read()
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"success": ok}})
        return
    console.print("[green]Marked all notifications as read.[/green]")


# ===========================================================================
# 18. templates
# ===========================================================================

templates_app = typer.Typer(help="Template commands.", no_args_is_help=True)
app.add_typer(templates_app, name="templates")


@templates_app.command("list")
def templates_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List templates.

    Examples:
        linear templates list
        linear templates list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_templates(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Templates ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""), node.get("type", ""), (node.get("team") or {}).get("key", "")
        )
    console.print(table)


@templates_app.command("get")
def templates_get(
    template_id: Annotated[str, typer.Argument(help="Template ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a template by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_template(template_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold] ({node.get('type')})")


@templates_app.command("create")
def templates_create(
    name: Annotated[str, typer.Argument(help="Template name")],
    template_type: Annotated[
        str, typer.Option("--type", help="Template type (issue, project, etc.)")
    ],
    template_data: Annotated[str, typer.Option("--data", help="Template data as JSON string")],
    team_id: Annotated[str | None, typer.Option("--team")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a template."""
    _require_auth(json_output)
    try:
        data_dict = json.loads(template_data)
    except json.JSONDecodeError as exc:
        if json_output:
            _error_json("validation", f"Invalid JSON in --data: {exc}", exit_code=4)
        _error(f"Invalid JSON in --data: {exc}", code=4)
        return
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, "type": template_type}})
        return
    client = Client()
    try:
        node = client.create_template(
            name=name,
            type=template_type,
            template_data=data_dict,
            team_id=team_id,
            description=description,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] template [bold]{node.get('name')}[/bold]")


@templates_app.command("update")
def templates_update(
    template_id: Annotated[str, typer.Argument(help="Template ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    template_data: Annotated[
        str | None, typer.Option("--data", help="Template data as JSON string")
    ] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a template."""
    _require_auth(json_output)
    data_dict: dict | None = None
    if template_data:
        try:
            data_dict = json.loads(template_data)
        except json.JSONDecodeError as exc:
            if json_output:
                _error_json("validation", f"Invalid JSON in --data: {exc}", exit_code=4)
            _error(f"Invalid JSON in --data: {exc}", code=4)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": template_id})
        return
    client = Client()
    try:
        node = client.update_template(
            template_id, body=extra, name=name, description=description, templateData=data_dict
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] template [bold]{node.get('name')}[/bold]")


@templates_app.command("delete")
def templates_delete(
    template_id: Annotated[str, typer.Argument(help="Template ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a template."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": template_id})
        return
    if not confirm:
        typer.confirm(f"Delete template {template_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_template(template_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": template_id}})
        return
    console.print(f"[green]Deleted[/green] template {template_id}.")


# ===========================================================================
# 19. favorites
# ===========================================================================

favorites_app = typer.Typer(help="Favorite commands.", no_args_is_help=True)
app.add_typer(favorites_app, name="favorites")


@favorites_app.command("list")
def favorites_list(
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List favorites.

    Examples:
        linear favorites list
        linear favorites list --json
    """
    client = _get_client(json_output)
    try:
        nodes = client.list_favorites()
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, {})
        return
    table = Table(title=f"Favorites ({len(nodes)})", show_lines=False)
    table.add_column("Type")
    table.add_column("Name")
    for node in nodes:
        fav_type = node.get("type", "")
        name = (
            (node.get("issue") or {}).get("identifier")
            or (node.get("project") or {}).get("name")
            or (node.get("cycle") or {}).get("name")
            or (node.get("label") or {}).get("name")
            or node.get("id", "")
        )
        table.add_row(fav_type, name)
    console.print(table)


@favorites_app.command("create")
def favorites_create(
    body: Annotated[
        str, typer.Argument(help='Favorite input as JSON (e.g. \'{"issueId": "..."}\')')
    ],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    Create a favorite.

    Examples:
        linear favorites create '{"issueId": "ISSUE_ID"}'
        linear favorites create '{"projectId": "PROJECT_ID"}'
    """
    _require_auth(json_output)
    try:
        input_dict = json.loads(body)
    except json.JSONDecodeError as exc:
        if json_output:
            _error_json("validation", f"Invalid JSON: {exc}", exit_code=4)
        _error(f"Invalid JSON: {exc}", code=4)
        return
    if dry_run:
        _output_json({"dry_run": True, "payload": input_dict})
        return
    client = Client()
    try:
        node = client.create_favorite(input_dict)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] favorite {node.get('id')} ({node.get('type')})")


@favorites_app.command("delete")
def favorites_delete(
    favorite_id: Annotated[str, typer.Argument(help="Favorite ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a favorite."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": favorite_id})
        return
    if not confirm:
        typer.confirm(f"Delete favorite {favorite_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_favorite(favorite_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": favorite_id}})
        return
    console.print(f"[green]Deleted[/green] favorite {favorite_id}.")


# ===========================================================================
# 20. releases
# ===========================================================================

releases_app = typer.Typer(help="Release commands.", no_args_is_help=True)
app.add_typer(releases_app, name="releases")


@releases_app.command("list")
def releases_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List releases.

    Examples:
        linear releases list
        linear releases list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_releases(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Releases ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Created", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""), node.get("status", ""), (node.get("createdAt") or "")[:10]
        )
    console.print(table)


@releases_app.command("create")
def releases_create(
    name: Annotated[str, typer.Argument(help="Release name")],
    body: Annotated[
        str, typer.Option("--body", help="Extra fields as JSON (required for pipeline etc.)")
    ],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a release."""
    _require_auth(json_output)
    try:
        body_dict = json.loads(body)
    except json.JSONDecodeError as exc:
        if json_output:
            _error_json("validation", f"Invalid JSON in --body: {exc}", exit_code=4)
        _error(f"Invalid JSON in --body: {exc}", code=4)
        return
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, **body_dict}})
        return
    client = Client()
    try:
        node = client.create_release(name=name, body=body_dict)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] release [bold]{node.get('name')}[/bold]")


@releases_app.command("update")
def releases_update(
    release_id: Annotated[str, typer.Argument(help="Release ID")],
    body: Annotated[str, typer.Option("--body", help="Fields to update as JSON string")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a release."""
    _require_auth(json_output)
    try:
        body_dict = json.loads(body)
    except json.JSONDecodeError as exc:
        if json_output:
            _error_json("validation", f"Invalid JSON in --body: {exc}", exit_code=4)
        _error(f"Invalid JSON in --body: {exc}", code=4)
        return
    if dry_run:
        _output_json({"dry_run": True, "id": release_id})
        return
    client = Client()
    try:
        node = client.update_release(release_id, body_dict)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] release [bold]{node.get('name')}[/bold]")


@releases_app.command("delete")
def releases_delete(
    release_id: Annotated[str, typer.Argument(help="Release ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a release."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": release_id})
        return
    if not confirm:
        typer.confirm(f"Delete release {release_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_release(release_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": release_id}})
        return
    console.print(f"[green]Deleted[/green] release {release_id}.")


@releases_app.command("archive")
def releases_archive(
    release_id: Annotated[str, typer.Argument(help="Release ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Archive a release."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": release_id})
        return
    client = Client()
    try:
        ok = client.archive_release(release_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"archived": ok, "id": release_id}})
        return
    console.print(f"[green]Archived[/green] release {release_id}.")


# ===========================================================================
# 21. organization
# ===========================================================================

organization_app = typer.Typer(help="Organization commands.", no_args_is_help=True)
app.add_typer(organization_app, name="organization")


@organization_app.command("get")
def organization_get(
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    Get the current organization.

    Examples:
        linear organization get
        linear organization get --json
    """
    client = _get_client(json_output)
    try:
        node = client.get_organization()
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold] ({node.get('urlKey')})")
    console.print(f"Users: {node.get('userCount', 0)}")
    sub = node.get("subscription") or {}
    if sub:
        console.print(f"Plan: {sub.get('type')}  Seats: {sub.get('seats')}")


@organization_app.command("update")
def organization_update(
    body: Annotated[str, typer.Argument(help="Fields to update as JSON string")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    Update organization settings.

    Examples:
        linear organization update '{"name": "Acme Inc"}'
    """
    _require_auth(json_output)
    try:
        body_dict = json.loads(body)
    except json.JSONDecodeError as exc:
        if json_output:
            _error_json("validation", f"Invalid JSON: {exc}", exit_code=4)
        _error(f"Invalid JSON: {exc}", code=4)
        return
    if dry_run:
        _output_json({"dry_run": True, "payload": body_dict})
        return
    client = Client()
    try:
        node = client.update_organization(body_dict)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] organization [bold]{node.get('name')}[/bold]")


# ===========================================================================
# 22. views (custom views)
# ===========================================================================

views_app = typer.Typer(help="Custom view commands.", no_args_is_help=True)
app.add_typer(views_app, name="views")


@views_app.command("list")
def views_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List custom views.

    Examples:
        linear views list
        linear views list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_views(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Views ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Shared")
    table.add_column("Owner")
    table.add_column("Team", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""),
            "Yes" if node.get("shared") else "No",
            (node.get("owner") or {}).get("name", ""),
            (node.get("team") or {}).get("key", ""),
        )
    console.print(table)


@views_app.command("get")
def views_get(
    view_id: Annotated[str, typer.Argument(help="View ID")],
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Get a custom view by ID."""
    client = _get_client(json_output)
    try:
        node = client.get_view(view_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": _filter_fields_single(node, fields)})
        return
    console.print(f"[bold]{node.get('name')}[/bold]  Shared: {node.get('shared')}")


@views_app.command("create")
def views_create(
    name: Annotated[str, typer.Argument(help="View name")],
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    shared: Annotated[bool, typer.Option("--shared/--private")] = False,
    team_id: Annotated[str | None, typer.Option("--team")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a custom view."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name}})
        return
    client = Client()
    try:
        node = client.create_view(
            name=name, body=extra, description=description, shared=shared, teamId=team_id
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] view [bold]{node.get('name')}[/bold]")


@views_app.command("update")
def views_update(
    view_id: Annotated[str, typer.Argument(help="View ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    shared: Annotated[bool | None, typer.Option("--shared/--private")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a custom view."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": view_id})
        return
    client = Client()
    try:
        node = client.update_view(
            view_id, body=extra, name=name, description=description, shared=shared
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] view [bold]{node.get('name')}[/bold]")


@views_app.command("delete")
def views_delete(
    view_id: Annotated[str, typer.Argument(help="View ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a custom view."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": view_id})
        return
    if not confirm:
        typer.confirm(f"Delete view {view_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_view(view_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": view_id}})
        return
    console.print(f"[green]Deleted[/green] view {view_id}.")


# ===========================================================================
# 23. milestones
# ===========================================================================

milestones_app = typer.Typer(help="Project milestone commands.", no_args_is_help=True)
app.add_typer(milestones_app, name="milestones")


@milestones_app.command("list")
def milestones_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    project: Annotated[str | None, typer.Option("--project", help="Filter by project ID")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List project milestones.

    Examples:
        linear milestones list --project PROJECT_ID
        linear milestones list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_milestones(
            project_id=project, limit=limit, fetch_all=all_results
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Milestones ({len(nodes)})", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Project")
    table.add_column("Target Date", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""),
            (node.get("project") or {}).get("name", ""),
            node.get("targetDate", "") or "",
        )
    console.print(table)


@milestones_app.command("create")
def milestones_create(
    name: Annotated[str, typer.Argument(help="Milestone name")],
    project_id: Annotated[str, typer.Option("--project", help="Project ID (required)")],
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a project milestone."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, "projectId": project_id}})
        return
    client = Client()
    try:
        node = client.create_milestone(
            name=name,
            project_id=project_id,
            target_date=target_date,
            description=description,
            body=extra,
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] milestone [bold]{node.get('name')}[/bold]")


@milestones_app.command("update")
def milestones_update(
    milestone_id: Annotated[str, typer.Argument(help="Milestone ID")],
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date")] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Update a project milestone."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": milestone_id})
        return
    client = Client()
    try:
        node = client.update_milestone(
            milestone_id, body=extra, name=name, description=description, targetDate=target_date
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Updated[/green] milestone [bold]{node.get('name')}[/bold]")


@milestones_app.command("delete")
def milestones_delete(
    milestone_id: Annotated[str, typer.Argument(help="Milestone ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a project milestone."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": milestone_id})
        return
    if not confirm:
        typer.confirm(f"Delete milestone {milestone_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_milestone(milestone_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": milestone_id}})
        return
    console.print(f"[green]Deleted[/green] milestone {milestone_id}.")


# ===========================================================================
# 24. relations
# ===========================================================================

relations_app = typer.Typer(help="Issue relation commands.", no_args_is_help=True)
app.add_typer(relations_app, name="relations")


@relations_app.command("list")
def relations_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List issue relations.

    Examples:
        linear relations list
        linear relations list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_issue_relations(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Relations ({len(nodes)})", show_lines=False)
    table.add_column("Issue", style="cyan")
    table.add_column("Type")
    table.add_column("Related", style="cyan")
    for node in nodes:
        table.add_row(
            (node.get("issue") or {}).get("identifier", ""),
            node.get("type", ""),
            (node.get("relatedIssue") or {}).get("identifier", ""),
        )
    console.print(table)


@relations_app.command("create")
def relations_create(
    issue_id: Annotated[str, typer.Argument(help="Source issue ID")],
    related_issue_id: Annotated[str, typer.Argument(help="Related issue ID")],
    relation_type: Annotated[str, typer.Argument(help="Relation type: blocks/duplicate/related")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create an issue relation."""
    _require_auth(json_output)
    if dry_run:
        _output_json(
            {
                "dry_run": True,
                "payload": {
                    "issueId": issue_id,
                    "relatedIssueId": related_issue_id,
                    "type": relation_type,
                },
            }
        )
        return
    client = Client()
    try:
        node = client.create_issue_relation(
            issue_id=issue_id, related_issue_id=related_issue_id, type=relation_type
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] relation {node.get('id')} ({relation_type})")


@relations_app.command("delete")
def relations_delete(
    relation_id: Annotated[str, typer.Argument(help="Relation ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete an issue relation."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": relation_id})
        return
    if not confirm:
        typer.confirm(f"Delete relation {relation_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_issue_relation(relation_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": relation_id}})
        return
    console.print(f"[green]Deleted[/green] relation {relation_id}.")


# ===========================================================================
# 25. memberships
# ===========================================================================

memberships_app = typer.Typer(help="Team membership commands.", no_args_is_help=True)
app.add_typer(memberships_app, name="memberships")


@memberships_app.command("list")
def memberships_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    team: Annotated[str | None, typer.Option("--team", help="Filter by team ID")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List team memberships.

    Examples:
        linear memberships list
        linear memberships list --team TEAM_ID --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_team_memberships(
            team_id=team, limit=limit, fetch_all=all_results
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Memberships ({len(nodes)})", show_lines=False)
    table.add_column("User")
    table.add_column("Team")
    table.add_column("Owner")
    for node in nodes:
        table.add_row(
            (node.get("user") or {}).get("name", ""),
            (node.get("team") or {}).get("key", ""),
            "Yes" if node.get("owner") else "No",
        )
    console.print(table)


@memberships_app.command("create")
def memberships_create(
    team_id: Annotated[str, typer.Argument(help="Team ID")],
    user_id: Annotated[str, typer.Argument(help="User ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Add a user to a team."""
    _require_auth(json_output)
    _validate_id(team_id, "team-id")
    _validate_id(user_id, "user-id")
    if dry_run:
        _output_json({"dry_run": True, "payload": {"teamId": team_id, "userId": user_id}})
        return
    client = Client()
    try:
        node = client.create_team_membership(team_id=team_id, user_id=user_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Added[/green] user {user_id} to team {team_id}")


@memberships_app.command("delete")
def memberships_delete(
    membership_id: Annotated[str, typer.Argument(help="Membership ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Remove a user from a team."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": membership_id})
        return
    if not confirm:
        typer.confirm(f"Remove membership {membership_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_team_membership(membership_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": membership_id}})
        return
    console.print(f"[green]Removed[/green] membership {membership_id}.")


# ===========================================================================
# 26. project-updates
# ===========================================================================

project_updates_app = typer.Typer(help="Project update commands.", no_args_is_help=True)
app.add_typer(project_updates_app, name="project-updates")


@project_updates_app.command("list")
def project_updates_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    project: Annotated[str | None, typer.Option("--project", help="Filter by project ID")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List project updates.

    Examples:
        linear project-updates list --project PROJECT_ID
        linear project-updates list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_project_updates(
            project_id=project, limit=limit, fetch_all=all_results
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Project Updates ({len(nodes)})", show_lines=False)
    table.add_column("Project")
    table.add_column("Health")
    table.add_column("Author")
    table.add_column("Created", style="dim")
    for node in nodes:
        table.add_row(
            (node.get("project") or {}).get("name", ""),
            node.get("health", "") or "",
            (node.get("user") or {}).get("name", ""),
            (node.get("createdAt") or "")[:10],
        )
    console.print(table)


@project_updates_app.command("create")
def project_updates_create(
    project_id: Annotated[str, typer.Argument(help="Project ID")],
    body_text: Annotated[str, typer.Argument(help="Update body text")],
    health: Annotated[
        str | None, typer.Option("--health", help="Health status: onTrack/atRisk/offTrack")
    ] = None,
    body: Annotated[str | None, typer.Option("--body", help="Extra fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a project update."""
    _require_auth(json_output)
    extra = _parse_body(body, json_output)
    if dry_run:
        _output_json(
            {
                "dry_run": True,
                "payload": {"projectId": project_id, "body": body_text, "health": health},
            }
        )
        return
    client = Client()
    try:
        node = client.create_project_update(
            project_id=project_id, body_text=body_text, health=health, body=extra
        )
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] project update {node.get('id')}")


@project_updates_app.command("delete")
def project_updates_delete(
    update_id: Annotated[str, typer.Argument(help="Project update ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a project update."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": update_id})
        return
    if not confirm:
        typer.confirm(f"Delete project update {update_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_project_update(update_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": update_id}})
        return
    console.print(f"[green]Deleted[/green] project update {update_id}.")


# ===========================================================================
# 27. emojis
# ===========================================================================

emojis_app = typer.Typer(help="Custom emoji commands.", no_args_is_help=True)
app.add_typer(emojis_app, name="emojis")


@emojis_app.command("list")
def emojis_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List custom emojis.

    Examples:
        linear emojis list
        linear emojis list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_emojis(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Emojis ({len(nodes)})", show_lines=False)
    table.add_column("Name")
    table.add_column("URL")
    table.add_column("Creator", style="dim")
    for node in nodes:
        table.add_row(
            node.get("name", ""), node.get("url", ""), (node.get("creator") or {}).get("name", "")
        )
    console.print(table)


@emojis_app.command("create")
def emojis_create(
    name: Annotated[str, typer.Argument(help="Emoji name (no colons)")],
    url: Annotated[str, typer.Argument(help="Image URL for the emoji")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a custom emoji."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "payload": {"name": name, "url": url}})
        return
    client = Client()
    try:
        node = client.create_emoji(name=name, url=url)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": node})
        return
    console.print(f"[green]Created[/green] emoji :{node.get('name')}:")


@emojis_app.command("delete")
def emojis_delete(
    emoji_id: Annotated[str, typer.Argument(help="Emoji ID")],
    confirm: Annotated[bool, typer.Option("--yes", "-y")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Delete a custom emoji."""
    _require_auth(json_output)
    if dry_run:
        _output_json({"dry_run": True, "id": emoji_id})
        return
    if not confirm:
        typer.confirm(f"Delete emoji {emoji_id}?", abort=True)
    client = Client()
    try:
        ok = client.delete_emoji(emoji_id)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_json({"data": {"deleted": ok, "id": emoji_id}})
        return
    console.print(f"[green]Deleted[/green] emoji {emoji_id}.")


# ===========================================================================
# 28. integrations
# ===========================================================================

integrations_app = typer.Typer(help="Integration commands.", no_args_is_help=True)
app.add_typer(integrations_app, name="integrations")


@integrations_app.command("list")
def integrations_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List integrations.

    Examples:
        linear integrations list
        linear integrations list --json
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_integrations(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Integrations ({len(nodes)})", show_lines=False)
    table.add_column("Service", style="bold")
    table.add_column("Team", style="dim")
    table.add_column("Created", style="dim")
    for node in nodes:
        table.add_row(
            node.get("service", ""),
            (node.get("team") or {}).get("key", ""),
            (node.get("createdAt") or "")[:10],
        )
    console.print(table)


# ===========================================================================
# 29. audit
# ===========================================================================

audit_app = typer.Typer(help="Audit log commands.", no_args_is_help=True)
app.add_typer(audit_app, name="audit")


@audit_app.command("list")
def audit_list(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 20,
    all_results: Annotated[bool, typer.Option("--all")] = False,
    fields: Annotated[str | None, typer.Option("--fields")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """
    List audit log entries.

    Examples:
        linear audit list
        linear audit list --json | jq '.data[].type'
    """
    client = _get_client(json_output)
    try:
        nodes, page_info = client.list_audit_entries(limit=limit, fetch_all=all_results)
    except LinearAPIError as e:
        _handle_api_error(e, json_output)
        return
    if json_output:
        _output_list_json(nodes, fields, page_info)
        return
    table = Table(title=f"Audit Log ({len(nodes)})", show_lines=False)
    table.add_column("Type")
    table.add_column("Actor")
    table.add_column("Created", style="dim")
    for node in nodes:
        table.add_row(
            node.get("type", ""),
            (node.get("actor") or {}).get("name", ""),
            (node.get("createdAt") or "")[:10],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
