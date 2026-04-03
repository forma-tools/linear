---
name: linear-triage
description: "Linear issue triage and workflow automation: review backlogs, prioritize, assign, label, estimate, sprint planning. Use when: (1) triaging new issues, (2) reviewing backlog, (3) sprint planning, (4) assigning work, (5) prioritizing issues. Triggers: triage, backlog review, sprint planning, assign issues, prioritize, estimate, unassigned issues, groom backlog."
version: 1.0.0
category: productivity
requires:
  bins: ["linear"]
cli-help: "linear issues list --help"
allowed-tools: "Read Bash Grep Glob"
---

# Linear Triage

Triage workflows - review backlogs, prioritize, assign, label, and plan sprints.

## When to Use

- Reviewing and triaging new/backlog issues
- Sprint or cycle planning sessions
- Assigning unassigned work
- Bulk prioritization and labeling
- Estimating story points

## When NOT to Use

- Creating individual issues - use `linear-issues`
- Project-level planning - use `linear-projects`
- Generating reports - use `linear-reporting`

## Backlog Review

```bash
# See all backlog issues
linear issues list --state-type backlog --all --json | \
  jq '.data[] | {identifier, title, priority: .priorityLabel, labels: [.labels.nodes[].name]}'

# Unassigned issues (need triage)
MY_TEAM=$(linear teams list --json | jq -r '.data[0].id')
linear issues list --team "$MY_TEAM" --state-type backlog --json | \
  jq '.data[] | select(.assignee == null) | {identifier, title}'

# Issues without priority
linear issues list --state-type backlog --priority 0 --json | \
  jq '.data[] | {identifier, title}'

# Issues without labels
linear issues list --state-type backlog --all --json | \
  jq '.data[] | select(.labels.nodes | length == 0) | {identifier, title}'
```

## Prioritize

```bash
# Set priority (1=Urgent, 2=High, 3=Medium, 4=Low)
linear issues update ROA-123 --priority 1 --json   # Urgent
linear issues update ROA-124 --priority 2 --json   # High
linear issues update ROA-125 --priority 3 --json   # Medium

# Bulk prioritize: set all unprioritzed backlog to Medium
linear issues list --state-type backlog --priority 0 --all --json | \
  jq -r '.data[].identifier' | \
  xargs -I{} linear issues update {} --priority 3 --json
```

## Assign

```bash
# List team members
linear users list --json | jq '.data[] | select(.active) | {id, name, email}'

# Assign an issue
linear issues update ROA-123 --assignee USER_ID --json

# Bulk assign unassigned issues
ASSIGNEE=$(linear users me --json | jq -r '.data.id')
linear issues list --state-type unstarted --all --json | \
  jq -r '.data[] | select(.assignee == null) | .identifier' | \
  xargs -I{} linear issues update {} --assignee "$ASSIGNEE" --json
```

## Label

```bash
# List available labels
linear labels list --json | jq '.data[] | {id, name}'

# Add labels
linear issues add-label ROA-123 LABEL_ID

# Bulk label: tag all issues matching a search
linear issues search "auth" --json | \
  jq -r '.data[].identifier' | \
  xargs -I{} linear issues add-label {} SECURITY_LABEL_ID
```

## Estimate

```bash
# Set story points
linear issues update ROA-123 --estimate 3 --json
linear issues update ROA-124 --estimate 5 --json

# Bulk estimate: set unestimated backlog to 1 (triage estimate)
linear issues list --state-type backlog --all --json | \
  jq -r '.data[] | select(.estimate == null) | .identifier' | \
  xargs -I{} linear issues update {} --estimate 1 --json
```

## Sprint Planning

```bash
# Get current cycle
TEAM_ID=$(linear teams list --json | jq -r '.data[0].id')
linear teams get "$TEAM_ID" --json | jq '.data.activeCycle'

# List cycle issues
CYCLE_ID=$(linear teams get "$TEAM_ID" --json | jq -r '.data.activeCycle.id')
linear issues list --cycle "$CYCLE_ID" --json | \
  jq '.data[] | {identifier, title, state: .state.name, assignee: .assignee.name}'

# Move issues into a cycle
linear issues update ROA-123 --cycle-id CYCLE_ID --json
linear issues update ROA-124 --cycle-id CYCLE_ID --json

# Move to "In Progress"
STATE_ID=$(linear states list --json | jq -r '.data[] | select(.name=="In Progress") | .id')
linear issues update ROA-123 --state-id "$STATE_ID" --json
```

## Triage Session Workflow

A complete triage session in 5 steps:

```bash
# 1. Get context
TEAM=$(linear teams list --json | jq -r '.data[0].id')
echo "Team: $(linear teams get $TEAM --json | jq -r '.data.name')"

# 2. Count by state
linear issues list --team "$TEAM" --all --json | \
  jq '[.data[] | .state.type] | group_by(.) | map({type: .[0], count: length})'

# 3. Review unprioritized backlog
linear issues list --team "$TEAM" --state-type backlog --priority 0 --json | \
  jq '.data[] | {identifier, title, created: .createdAt}'

# 4. Prioritize and assign (interactive - review each)
for ISSUE in $(linear issues list --team "$TEAM" --state-type backlog --priority 0 --json | jq -r '.data[].identifier'); do
  echo "Issue: $ISSUE"
  linear issues get "$ISSUE" --json | jq '{title: .data.title, description: .data.description}'
  # Set priority and assignee based on review
done

# 5. Summary
linear issues list --team "$TEAM" --state-type backlog --json | jq '.meta.count'
echo "remaining in backlog"
```

## Gotchas

- `--state-type` is more useful than `--state` for triage (works across teams with different state names)
- Priority 0 means "No priority" - these are your triage candidates
- Issues without estimates show `estimate: null` in JSON
- `--all` can be slow on large backlogs - use `--limit 50` for iterative triage
- Always `--dry-run` before bulk updates to verify the scope
- Cycle assignment uses `--cycle-id` (UUID), not cycle name or number
