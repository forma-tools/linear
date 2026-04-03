---
name: linear-ops
description: "Linear workspace administration: team setup, label management, webhook configuration, workflow states, user management, templates. Use when: (1) setting up new teams, (2) creating/managing labels, (3) configuring webhooks, (4) customizing workflow states, (5) managing users, (6) creating templates. Triggers: linear admin, setup team, create labels, configure webhooks, manage users, workflow states, workspace setup, linear ops, team setup."
version: 1.0.0
category: infra
requires:
  bins: ["linear"]
cli-help: "linear teams --help"
allowed-tools: "Read Bash Grep Glob"
---

# Linear Ops

Workspace administration - teams, labels, states, webhooks, users, templates.

## When to Use

- Setting up new teams with states and labels
- Creating or reorganizing label taxonomies
- Configuring webhooks for integrations
- Customizing workflow states per team
- Managing users (invite, suspend, role changes)
- Creating issue and project templates

## When NOT to Use

- Issue-level work - use `linear-issues`
- Project planning - use `linear-projects`
- Sprint triage - use `linear-triage`
- Generating reports - use `linear-reporting`

## Teams

```bash
# List teams
linear teams list --json | jq '.data[] | {id, name, key, issueCount}'

# Get team detail (includes states, labels, members, active cycle)
linear teams get TEAM_ID --json

# Create a team
linear teams create "Backend" --key BE --json
linear teams create "Design" --key DSN --description "Product design team" --json

# Update team
linear teams update TEAM_ID --name "Backend Engineering" --json

# Delete team (destructive!)
linear teams delete TEAM_ID --yes
```

## Workflow States

Each team has its own workflow states. The `type` determines behavior:

| Type | Meaning | Default states |
|------|---------|----------------|
| `backlog` | Not yet triaged | Backlog |
| `unstarted` | Triaged, not started | Todo |
| `started` | Work in progress | In Progress |
| `completed` | Done | Done |
| `canceled` | Won't do | Canceled |

```bash
# List states (all teams)
linear states list --json | jq '.data[] | {id, name, type, team: .team.key}'

# Create custom states
TEAM_ID=$(linear teams list --json | jq -r '.data[0].id')
linear states create "In Review" --team "$TEAM_ID" --type started --color "#f2c94c" --json
linear states create "Blocked" --team "$TEAM_ID" --type started --color "#eb5757" --json
linear states create "QA" --team "$TEAM_ID" --type started --color "#6fcf97" --json

# Update state
linear states update STATE_ID --name "Code Review" --color "#bb87fc" --json

# Archive state (only if no active issues use it)
linear states archive STATE_ID
```

## Labels

Labels are workspace-wide or team-scoped.

```bash
# List all labels
linear labels list --all --json | jq '.data[] | {id, name, color, team: .team.key}'

# Create workspace label (no --team)
linear labels create "Bug" --color "#eb5757" --json
linear labels create "Feature" --color "#bb87fc" --json
linear labels create "Improvement" --color "#6fcf97" --json
linear labels create "Tech Debt" --color "#f2994a" --json

# Create team-scoped label
linear labels create "Sprint Goal" --team TEAM_ID --color "#f2c94c" --json

# Create label hierarchy (parent-child)
PARENT=$(linear labels create "Priority" --color "#4ea7fc" --json | jq -r '.data.id')
linear labels create "P0 - Critical" --parent-id "$PARENT" --color "#eb5757" --json
linear labels create "P1 - High" --parent-id "$PARENT" --color "#f2994a" --json
linear labels create "P2 - Medium" --parent-id "$PARENT" --color "#f2c94c" --json

# Update label
linear labels update LABEL_ID --name "Bugfix" --color "#ff6b6b" --json

# Delete label
linear labels delete LABEL_ID --yes
```

## Standard Label Set

Quick setup for a new workspace:

```bash
# Bug lifecycle
linear labels create "Bug" --color "#eb5757"
linear labels create "Regression" --color "#eb5757"

# Work type
linear labels create "Feature" --color "#bb87fc"
linear labels create "Improvement" --color "#6fcf97"
linear labels create "Tech Debt" --color "#f2994a"
linear labels create "Documentation" --color "#4ea7fc"

# Process
linear labels create "Needs Review" --color "#f2c94c"
linear labels create "Blocked" --color "#95a2b3"
linear labels create "Quick Win" --color "#27ae60"
```

## Webhooks

```bash
# List webhooks
linear webhooks list --json | jq '.data[] | {id, label, url, enabled}'

# Create webhook
linear webhooks create "https://example.com/webhook" \
  --label "My Integration" \
  --resource-types Issue,Comment,Project \
  --json

# Team-scoped webhook
linear webhooks create "https://example.com/webhook" \
  --label "Team webhook" \
  --team TEAM_ID \
  --json

# Disable/enable
linear webhooks update WEBHOOK_ID --enabled false --json
linear webhooks update WEBHOOK_ID --enabled true --json

# Delete
linear webhooks delete WEBHOOK_ID --yes
```

### Resource Types for Webhooks

`Comment`, `Cycle`, `Issue`, `IssueLabel`, `IssueSLA`, `Project`, `ProjectUpdate`, `Reaction`, `User`

## Users

```bash
# List workspace users
linear users list --json | jq '.data[] | {id, name, email, active, admin}'

# Get current user
linear users me --json

# Get user detail
linear users get USER_ID --json

# Suspend/unsuspend (admin only)
linear users suspend USER_ID
linear users unsuspend USER_ID
```

## Team Memberships

```bash
# List memberships
linear memberships list --json | jq '.data[] | {user: .user.name, team: .team.key}'

# Add user to team
linear memberships create --team TEAM_ID --user USER_ID

# Remove user from team
linear memberships delete MEMBERSHIP_ID --yes
```

## Templates

```bash
# List templates
linear templates list --json | jq '.data[] | {id, name, type, team: .team.key}'

# Get template detail (includes template data)
linear templates get TEMPLATE_ID --json

# Create issue template
linear templates create "Bug Report" --type issue \
  --team TEAM_ID \
  --description "Standard bug report template" \
  --template-data '{"title": "Bug: ", "priority": 2}' \
  --json

# Update template
linear templates update TEMPLATE_ID --name "Bug Report v2" --json

# Delete template
linear templates delete TEMPLATE_ID --yes
```

## Organization

```bash
# View org settings
linear organization get --json | jq '.data | {name, urlKey, userCount, subscription}'

# Update org (admin only)
linear organization update --body '{"name": "New Org Name"}' --json
```

## Workspace Bootstrap

Complete setup for a new Linear workspace:

```bash
# 1. Create team
TEAM=$(linear teams create "Engineering" --key ENG --json | jq -r '.data.id')

# 2. Add custom states
linear states create "In Review" --team "$TEAM" --type started --color "#bb87fc"
linear states create "QA" --team "$TEAM" --type started --color "#6fcf97"

# 3. Create labels
for label in "Bug:#eb5757" "Feature:#bb87fc" "Tech Debt:#f2994a" "Quick Win:#27ae60"; do
  NAME="${label%%:*}"
  COLOR="${label##*:}"
  linear labels create "$NAME" --color "$COLOR"
done

# 4. Set up webhook
linear webhooks create "https://your-app.com/linear-webhook" \
  --label "Production webhook" \
  --resource-types Issue,Comment,Project

# 5. Verify
linear teams get "$TEAM" --json | jq '{name: .data.name, states: [.data.states.nodes[].name], labels: [.data.labels.nodes[].name]}'
```

## Gotchas

- State `type` is fixed after creation - you can rename states but not change their type
- Workspace labels (no `--team`) are visible across all teams
- Team-scoped labels are only visible within that team
- Deleting a team deletes all its issues - use with extreme caution
- Webhooks require HTTPS URLs (no localhost)
- Template `--template-data` must be valid JSON matching the entity type
- Admin role required for: user suspend/unsuspend, org updates, some webhook operations
- Cache TTL for teams/labels/users is 30 minutes - use `--no-cache` after making changes
