---
name: linear-issues
description: "Linear issue workflows: triage, bulk operations, search, state transitions, sprint management. Use when: (1) finding/filtering issues, (2) creating issues from lists or specs, (3) bulk state changes, (4) sprint/cycle management, (5) issue triage. Triggers: linear issues, find issues, create issue, move issues, triage, sprint, my issues, assigned to me, backlog."
version: 1.0.0
category: productivity
requires:
  bins: ["linear"]
cli-help: "linear issues --help"
allowed-tools: "Read Bash Grep Glob"
---

# Linear Issues

Issue lifecycle management - find, create, triage, transition, and bulk-operate on Linear issues.

## When to Use

- Finding issues by state, assignee, label, team, project, or text search
- Creating one or many issues
- Moving issues between states (triage, start, complete, archive)
- Bulk operations across multiple issues
- Sprint/cycle planning

## When NOT to Use

- Project-level planning - use `linear-projects` skill
- Reporting/analytics - use `linear-reporting` skill
- Workspace setup (teams, labels, states) - use `linear-ops` skill

## Quick Reference

```bash
# List issues (default 20, most recently updated first)
linear issues list --json

# Filter by state type (backlog/unstarted/started/completed/canceled)
linear issues list --state-type started --json

# Filter by exact state name
linear issues list --state "In Progress" --json

# Filter by team, assignee, label, priority
linear issues list --team TEAM_ID --assignee USER_ID --label "Bug" --priority 1

# Search by text
linear issues search "login bug" --json

# Get full issue detail
linear issues get ROA-123 --json

# Minimal fields (protects context window)
linear issues list --fields identifier,title,state --json
```

## Create Issues

```bash
# Simple
linear issues create "Fix login page timeout" --team TEAM_ID

# With all options
linear issues create "Redesign dashboard" \
  --team TEAM_ID \
  --description "New layout per Figma specs" \
  --assignee USER_ID \
  --priority 2 \
  --labels "LABEL_ID1,LABEL_ID2" \
  --project PROJECT_ID \
  --due-date 2026-04-30 \
  --estimate 5 \
  --json

# Dry-run (validate without creating)
linear issues create "Test" --team TEAM_ID --dry-run --json

# From raw JSON (full API access)
linear issues create "Advanced" --team TEAM_ID \
  --body '{"subscriberIds": ["USER_ID"], "sortOrder": 1.5}'
```

## State Transitions

```bash
# Get available states for a team
linear states list --json | jq '.data[] | {id, name, type}'

# Move issue to a state
STATE_ID=$(linear states list --json | jq -r '.data[] | select(.name=="Done") | .id')
linear issues update ROA-123 --state-id "$STATE_ID" --json

# Archive completed issues
linear issues archive ROA-123
linear issues unarchive ROA-123
```

## Bulk Operations

```bash
# Find all backlog issues and extract IDs
linear issues list --state-type backlog --all --json | jq -r '.data[].id'

# Bulk update: assign all unassigned to someone
IDS=$(linear issues list --state-type unstarted --all --json | \
  jq -r '.data[] | select(.assignee == null) | .identifier')
for id in $IDS; do
  linear issues update "$id" --assignee USER_ID --json
done

# Bulk label: add "Sprint 5" label to issues
for id in ROA-101 ROA-102 ROA-103; do
  linear issues add-label "$id" LABEL_ID
done
```

## Labels

```bash
# Add/remove labels
linear issues add-label ROA-123 LABEL_ID
linear issues remove-label ROA-123 LABEL_ID

# Find label IDs
linear labels list --json | jq '.data[] | {id, name}'
```

## Search Patterns

```bash
# Text search
linear issues search "payment" --json | jq '.data[] | {identifier, title}'

# Find my issues (get your user ID first)
MY_ID=$(linear users me --json | jq -r '.data.id')
linear issues list --assignee "$MY_ID" --json

# Issues in a project
linear issues list --project PROJECT_ID --json

# Issues in a cycle
linear issues list --cycle CYCLE_ID --json

# High priority issues
linear issues list --priority 1 --json
linear issues list --priority 2 --json
```

## Pipe Patterns

| From | To | Pattern |
|------|----|---------|
| List IDs | Bulk update | `linear issues list --json \| jq -r '.data[].identifier' \| xargs -I{} linear issues update {} --state-id X` |
| Search | Get detail | `linear issues search "bug" --json \| jq -r '.data[0].identifier' \| xargs linear issues get --json` |
| List | Count by state | `linear issues list --all --json \| jq '.data \| group_by(.state.name) \| map({state: .[0].state.name, count: length})'` |
| List | CSV export | `linear issues list --all --fields identifier,title,state --json \| jq -r '.data[] \| [.identifier, .title, .state.name] \| @csv'` |

## Gotchas

- Issue IDs accept both UUIDs and identifiers (e.g., `ROA-123`)
- `--state` matches state NAME (case-insensitive), `--state-type` matches TYPE (backlog/unstarted/started/completed/canceled)
- `--priority` is 0-4: 0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low
- `--all` fetches every page - use `--limit` for bounded queries
- Delete is permanent - use `--dry-run` first, then `--yes` to confirm
- `--fields` only affects JSON output, not human-readable tables
- Cache TTL is 5 minutes for issues - use `--no-cache` for guaranteed fresh data
