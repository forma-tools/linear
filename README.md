# linear

[![Forma](https://img.shields.io/badge/forma-experimental-orange.svg)](https://github.com/forma-tools/forma)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/v0.1.0-blue.svg)](CHANGELOG.md)

> Linear project management CLI — issues, projects, cycles, teams, roadmaps, initiatives, customers, and more.

## Install

```bash
uv pip install -e .
```

## Quick Start

```bash
# Authenticate
linear auth login

# List your open issues
linear issues list --limit 10

# Get a specific issue
linear issues get LIN-42 --json

# Pipe JSON to jq
linear issues list --json 2>/dev/null | jq '.data[0]'

# Create an issue
linear issues create "Fix login redirect" --team TEAM_ID --priority 2

# Search across all issues
linear issues search "auth bug" --json 2>/dev/null | jq '.data[].identifier'
```

## Commands

### Update

```bash
linear update                          # Self-update from git remote
linear update --check                  # Check for updates without installing
linear update --check --json           # Machine-readable update check
```

### Describe

```bash
linear describe                        # List all 134 commands as JSON
linear describe issues                 # List actions for a resource
linear describe issues list            # Full schema for a single command
```

### Issues

```bash
# List with filters
linear issues list
linear issues list --team TEAM_ID --state "In Progress" --limit 50
linear issues list --state-type started --json 2>/dev/null | jq '.data[].identifier'
linear issues list --assignee USER_ID --priority 1 --json 2>/dev/null | jq '.data[].identifier'
linear issues list --all --fields id,identifier,title,state
linear issues list --no-cache          # Bypass file-based TTL cache

# Get, create, update, delete
linear issues get LIN-42
linear issues get LIN-42 --json
linear issues create "New feature" --team TEAM_ID --priority 2 --description "Details here"
linear issues update LIN-42 --title "Updated title" --state-id STATE_ID
linear issues delete LIN-42 --yes

# Archive / unarchive
linear issues archive LIN-42
linear issues unarchive LIN-42

# Search
linear issues search "login bug" --json 2>/dev/null | jq '.data[].identifier'

# Labels
linear issues add-label LIN-42 LABEL_ID
linear issues remove-label LIN-42 LABEL_ID
```

### Projects

```bash
linear projects list
linear projects list --no-cache        # Force fresh fetch, bypass TTL cache
linear projects list --state backlog --json 2>/dev/null | jq '.data[].name'
linear projects get PROJECT_ID --json
linear projects create "Q3 Launch" --teams TEAM_ID --target-date 2026-09-30
linear projects update PROJECT_ID --state started
linear projects delete PROJECT_ID --yes
linear projects archive PROJECT_ID
linear projects search "launch" --json
```

### Teams

```bash
linear teams list
linear teams list --json 2>/dev/null | jq '.data[].key'
linear teams get TEAM_ID --json
linear teams create "Platform" --key PLT
linear teams update TEAM_ID --name "Platform Engineering"
linear teams delete TEAM_ID --yes
```

### Cycles

```bash
linear cycles list --team TEAM_ID
linear cycles get CYCLE_ID --json
linear cycles create --team TEAM_ID --name "Sprint 12" --start-date 2026-04-07 --end-date 2026-04-18
linear cycles update CYCLE_ID --name "Sprint 12 (revised)"
linear cycles archive CYCLE_ID
```

### Labels

```bash
linear labels list
linear labels list --json 2>/dev/null | jq '.data[] | {id, name}'
linear labels create "bug" --team TEAM_ID --color "#ff0000"
linear labels update LABEL_ID --name "regression"
linear labels delete LABEL_ID --yes
```

### Users

```bash
linear users list --json 2>/dev/null | jq '.data[] | {id, name, email}'
linear users get USER_ID --json
linear users me --json
linear users suspend USER_ID
linear users unsuspend USER_ID
```

### Comments

```bash
linear comments list --issue LIN-42
linear comments create --issue LIN-42 --body "Fixed in PR #341"
linear comments update COMMENT_ID --body "Updated: fixed in PR #341"
linear comments delete COMMENT_ID --yes
linear comments resolve COMMENT_ID
linear comments unresolve COMMENT_ID
```

### Documents

```bash
linear documents list
linear documents get DOCUMENT_ID --json
linear documents create "Architecture Decision Record" --body '{"content": "..."}'
linear documents update DOCUMENT_ID --title "Updated Title"
linear documents delete DOCUMENT_ID --yes
linear documents search "architecture" --json
```

### Initiatives

```bash
linear initiatives list --json 2>/dev/null | jq '.data[].name'
linear initiatives get INITIATIVE_ID --json
linear initiatives create "Platform Reliability"
linear initiatives update INITIATIVE_ID --name "Platform Reliability 2026"
linear initiatives archive INITIATIVE_ID
linear initiatives unarchive INITIATIVE_ID
linear initiatives delete INITIATIVE_ID --yes
```

### Roadmaps

```bash
linear roadmaps list
linear roadmaps get ROADMAP_ID --json
linear roadmaps create "2026 Product Roadmap"
linear roadmaps update ROADMAP_ID --name "2026 Product Roadmap (v2)"
linear roadmaps archive ROADMAP_ID
linear roadmaps delete ROADMAP_ID --yes
```

### Webhooks

```bash
linear webhooks list
linear webhooks get WEBHOOK_ID --json
linear webhooks create --url https://example.com/hook --team TEAM_ID
linear webhooks update WEBHOOK_ID --url https://example.com/hook-v2
linear webhooks delete WEBHOOK_ID --yes
```

### Workflow States

```bash
linear states list --team TEAM_ID
linear states list --team TEAM_ID --json 2>/dev/null | jq '.data[] | {id, name, type}'
linear states create "Code Review" --team TEAM_ID --type started
linear states update STATE_ID --name "In Review"
linear states archive STATE_ID
```

### Customers

```bash
linear customers list
linear customers get CUSTOMER_ID --json
linear customers create "Acme Corp"
linear customers update CUSTOMER_ID --name "Acme Corporation"
linear customers delete CUSTOMER_ID --yes
```

### Attachments

```bash
linear attachments list --issue LIN-42
linear attachments get ATTACHMENT_ID --json
linear attachments link-url --issue LIN-42 --url https://github.com/org/repo/pull/99 --title "PR #99"
linear attachments delete ATTACHMENT_ID --yes
```

### Notifications

```bash
linear notifications list --json 2>/dev/null | jq '.data[].type'
linear notifications get NOTIFICATION_ID --json
linear notifications archive NOTIFICATION_ID
linear notifications mark-read
```

### Templates

```bash
linear templates list
linear templates get TEMPLATE_ID --json
linear templates create "Bug Report" --team TEAM_ID
linear templates update TEMPLATE_ID --name "Bug Report v2"
linear templates delete TEMPLATE_ID --yes
```

### Favorites

```bash
linear favorites list --json
linear favorites create --issue LIN-42
linear favorites delete FAVORITE_ID --yes
```

### Releases

```bash
linear releases list
linear releases create "v2.3.0" --release-date 2026-04-15
linear releases update RELEASE_ID --name "v2.3.1"
linear releases archive RELEASE_ID
linear releases delete RELEASE_ID --yes
```

### Organization

```bash
linear organization get --json
linear organization update --name "Acme Inc"
```

### Custom Views

```bash
linear views list
linear views get VIEW_ID --json
linear views create "My Open Issues"
linear views update VIEW_ID --name "My Open Issues (updated)"
linear views delete VIEW_ID --yes
```

### Project Milestones

```bash
linear milestones list --project PROJECT_ID
linear milestones create "Beta Launch" --project PROJECT_ID --target-date 2026-06-01
linear milestones update MILESTONE_ID --name "Beta Launch (revised)"
linear milestones delete MILESTONE_ID --yes
```

### Issue Relations

```bash
linear relations list --issue LIN-42 --json
linear relations create --issue LIN-42 --related-issue LIN-43 --type blocks
linear relations delete RELATION_ID --yes
```

Relation types: `blocks`, `blocked_by`, `duplicate_of`, `duplicated_by`, `related`

### Team Memberships

```bash
linear memberships list --team TEAM_ID --json
linear memberships create --team TEAM_ID --user USER_ID
linear memberships delete MEMBERSHIP_ID --yes
```

### Project Updates

```bash
linear project-updates list --project PROJECT_ID
linear project-updates create --project PROJECT_ID --body "On track for Q2 target"
linear project-updates delete UPDATE_ID --yes
```

### Emojis

```bash
linear emojis list --json 2>/dev/null | jq '.data[].name'
linear emojis create "rocket-launch" --url https://example.com/emoji.png
linear emojis delete EMOJI_ID --yes
```

### Integrations

```bash
linear integrations list --json 2>/dev/null | jq '.data[].name'
```

### Audit Log

```bash
linear audit list --limit 50 --json
linear audit list --json 2>/dev/null | jq '.data[] | {type, createdAt, actor: .actor.name}'
```

### Authentication

```bash
linear auth login                      # Interactive prompt
linear auth login --key lin_api_xxx    # Non-interactive
linear auth status                     # Check current status
linear auth status --json              # Machine-readable
linear auth logout                     # Clear stored key
```

### Cache

```bash
linear cache status                    # Show cache stats
linear cache status --json             # Machine-readable (shows all entries after live use)
linear cache clear                     # Delete all cached responses
```

List commands for issues, projects, teams, cycles, labels, and users support `--no-cache` (or `--refresh`) to bypass the file-based TTL cache and force a fresh API fetch.

## Authentication

The CLI looks for credentials in this order:

| Priority | Source | Notes |
|----------|--------|-------|
| 1 | `LINEAR_API_KEY` env var | Ideal for CI/CD |
| 2 | OS keyring | Default after `auth login` |
| 3 | `.env` file | Fallback when keyring unavailable |

Generate API keys at: https://linear.app/settings/api

```bash
# Check if authenticated before running scripts
if ! linear auth status --json 2>/dev/null | jq -e '.data.authenticated' > /dev/null; then
  echo "Not authenticated. Run: linear auth login"
  exit 1
fi
```

## Requirements

- Python 3.11+
- Linear API key — generate at https://linear.app/settings/api

## Recent Changes

### v0.1.0 (2026-04-02)

- 134 commands across 31 command groups
- `update` command — self-update from git remote (`--check`, `--json`)
- `describe` command — runtime JSON introspection of all 134 commands
- `--state-type` filter on `issues list` (backlog, unstarted, started, completed, canceled)
- `--no-cache` / `--refresh` flags on list commands to bypass file-based TTL cache
- `--body` passthrough on all create/update commands
- Exit code constants (EXIT_SUCCESS through EXIT_CONFLICT)
- Issues: list, get, create, update, delete, archive, unarchive, search, add-label, remove-label
- Projects: list, get, create, update, delete, archive, unarchive, search
- Teams, cycles, labels, users, comments, documents, initiatives, roadmaps
- Webhooks, states, customers, attachments, notifications, templates
- Favorites, releases, organization, views, milestones, relations, memberships
- Project updates, emojis, integrations, audit log
- Authentication via OS keyring or `LINEAR_API_KEY` environment variable
- JSON output with `{data, meta}` envelope on all commands
- Semantic exit codes 0-7
- `--dry-run` on all mutation commands
- `--fields` flag for context-window-efficient output
- Response caching with `cache status` / `cache clear`

## Forma Protocol

This tool follows the [Forma Protocol](https://github.com/forma-tools/forma) v1.2:

- `--json` on all commands with `{data, meta}` envelope
- Semantic exit codes (0-7)
- `auth login/status/logout` credential management
- stdout/stderr separation (JSON to stdout, display to stderr)
- `--dry-run` before all create/update/delete operations
- `--fields` for field selection on list and get commands
