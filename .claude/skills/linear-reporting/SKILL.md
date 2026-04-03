---
name: linear-reporting
description: "Linear reporting and analytics: team velocity, issue counts, state distribution, cycle reports, project progress. Use when: (1) generating status reports, (2) counting issues by state/priority/label, (3) team workload analysis, (4) sprint/cycle reports, (5) project health summaries. Triggers: linear report, how many issues, team velocity, sprint report, project status, workload, issue count, analytics, dashboard."
version: 1.0.0
category: data
requires:
  bins: ["linear", "jq"]
cli-help: "linear issues list --help"
allowed-tools: "Read Bash Grep Glob"
---

# Linear Reporting

Extract insights from Linear data using `--json` output and `jq` pipelines.

## When to Use

- Generating status reports for standups or stakeholders
- Counting issues by state, priority, label, or assignee
- Team workload and capacity analysis
- Sprint/cycle progress reports
- Project health summaries

## When NOT to Use

- Making changes to issues - use `linear-issues`
- Project planning - use `linear-projects`
- Triage and assignment - use `linear-triage`

## Issue Distribution

```bash
# Count by state type
linear issues list --all --json | \
  jq '[.data[] | .state.type] | group_by(.) | map({type: .[0], count: length}) | sort_by(-.count)'

# Count by state name
linear issues list --all --json | \
  jq '[.data[] | .state.name] | group_by(.) | map({state: .[0], count: length}) | sort_by(-.count)'

# Count by priority
linear issues list --all --json | \
  jq '[.data[] | .priorityLabel] | group_by(.) | map({priority: .[0], count: length}) | sort_by(-.count)'

# Count by assignee
linear issues list --all --json | \
  jq '[.data[] | (.assignee.name // "Unassigned")] | group_by(.) | map({assignee: .[0], count: length}) | sort_by(-.count)'

# Count by label
linear issues list --all --json | \
  jq '[.data[].labels.nodes[].name] | group_by(.) | map({label: .[0], count: length}) | sort_by(-.count)'
```

## Team Workload

```bash
# Issues per team member (active issues only)
linear issues list --state-type started --all --json | \
  jq '[.data[] | (.assignee.name // "Unassigned")] | group_by(.) | map({person: .[0], active: length}) | sort_by(-.active)'

# Workload summary: active + backlog per person
linear issues list --all --json | \
  jq '.data | group_by(.assignee.name // "Unassigned") | map({
    person: .[0].assignee.name // "Unassigned",
    total: length,
    active: [.[] | select(.state.type == "started")] | length,
    backlog: [.[] | select(.state.type == "backlog" or .state.type == "unstarted")] | length,
    done: [.[] | select(.state.type == "completed")] | length
  }) | sort_by(-.active)'
```

## Sprint/Cycle Report

```bash
# Get active cycle
TEAM_ID=$(linear teams list --json | jq -r '.data[0].id')
CYCLE=$(linear teams get "$TEAM_ID" --json | jq -r '.data.activeCycle')
echo "$CYCLE" | jq '{name, number, startsAt, endsAt}'

# Cycle issue breakdown
CYCLE_ID=$(echo "$CYCLE" | jq -r '.id')
linear issues list --cycle "$CYCLE_ID" --all --json | \
  jq '{
    total: (.data | length),
    by_state: ([.data[] | .state.name] | group_by(.) | map({state: .[0], count: length})),
    by_assignee: ([.data[] | (.assignee.name // "Unassigned")] | group_by(.) | map({person: .[0], count: length}))
  }'

# Completed in cycle
linear issues list --cycle "$CYCLE_ID" --state-type completed --all --json | \
  jq '.data[] | {identifier, title, completedAt}'
```

## Project Health

```bash
# All projects with progress
linear projects list --all --json | \
  jq '.data[] | {name, state, progress: (.progress * 100 | floor | tostring + "%"), targetDate}'

# Single project deep dive
linear projects get PROJECT_ID --json | \
  jq '{
    name: .data.name,
    state: .data.state,
    progress: (.data.progress * 100 | floor | tostring + "%"),
    scope: .data.scope,
    targetDate: .data.targetDate,
    lead: .data.lead.name,
    teams: [.data.teams.nodes[].name],
    milestones: [.data.milestones.nodes[] | {name, targetDate}]
  }'

# Recent project updates
linear project-updates list --project PROJECT_ID --json | \
  jq '.data[] | {health, date: .createdAt, author: .user.name, body: .body[:100]}'
```

## Quick Dashboards

### Daily Standup

```bash
echo "=== My Issues ===" 
MY_ID=$(linear users me --json | jq -r '.data.id')
linear issues list --assignee "$MY_ID" --state-type started --json | \
  jq -r '.data[] | "  \(.identifier): \(.title)"'

echo ""
echo "=== Recently Completed ==="
linear issues list --assignee "$MY_ID" --state-type completed --limit 5 --json | \
  jq -r '.data[] | "  \(.identifier): \(.title)"'
```

### Weekly Summary

```bash
echo "=== Issue Counts ==="
linear issues list --all --no-cache --json | \
  jq '{
    total: (.data | length),
    backlog: [.data[] | select(.state.type == "backlog")] | length,
    todo: [.data[] | select(.state.type == "unstarted")] | length,
    in_progress: [.data[] | select(.state.type == "started")] | length,
    done: [.data[] | select(.state.type == "completed")] | length,
    canceled: [.data[] | select(.state.type == "canceled")] | length
  }'

echo ""
echo "=== High Priority ==="
linear issues list --priority 1 --json | jq -r '.data[] | "\(.identifier): \(.title)"'
linear issues list --priority 2 --json | jq -r '.data[] | "\(.identifier): \(.title)"'
```

## Export Patterns

```bash
# CSV export
linear issues list --all --fields identifier,title,state,assignee,priority --json | \
  jq -r '.data[] | [.identifier, .title, .state.name, (.assignee.name // ""), .priorityLabel] | @csv'

# Markdown table
linear issues list --state-type started --json | \
  jq -r '"| Identifier | Title | Assignee | Priority |", "| --- | --- | --- | --- |", (.data[] | "| \(.identifier) | \(.title) | \(.assignee.name // "-") | \(.priorityLabel) |")'
```

## Gotchas

- Always use `--all` for accurate counts - default limit is 20
- Use `--no-cache` for reports that need real-time data
- `progress` on projects is 0.0-1.0 (multiply by 100 for percentage)
- `completedAt` is null for non-completed issues
- Priority values: 0=None, 1=Urgent, 2=High, 3=Medium, 4=Low
- `jq` is required for all reporting patterns - install via `brew install jq`
- Large workspaces may hit rate limits with `--all` - space queries apart
