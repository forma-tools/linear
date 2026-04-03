---
name: linear-projects
description: "Linear project management: create projects, track progress, milestones, updates, roadmap integration. Use when: (1) setting up new projects, (2) checking project health, (3) writing project updates, (4) managing milestones, (5) roadmap planning. Triggers: linear project, new project, project status, milestones, roadmap, project update, project health, project progress."
version: 1.0.0
category: productivity
requires:
  bins: ["linear"]
cli-help: "linear projects --help"
allowed-tools: "Read Bash Grep Glob"
---

# Linear Projects

Project lifecycle - create, track, milestone, update, and roadmap integration.

## When to Use

- Creating and configuring projects
- Checking project health and progress
- Managing milestones and target dates
- Writing and reading project updates
- Connecting projects to roadmaps and initiatives

## When NOT to Use

- Issue-level work within a project - use `linear-issues`
- Team velocity or sprint reports - use `linear-reporting`
- Team/label/state setup - use `linear-ops`

## Quick Reference

```bash
# List projects (most recently updated)
linear projects list --json

# Filter by state
linear projects list --state started --json
linear projects list --state completed --json

# Search by name
linear projects search "Q4" --json

# Get full project detail
linear projects get PROJECT_ID --json

# Minimal fields
linear projects list --fields name,state,progress,targetDate --json
```

## Create a Project

```bash
# Get your team ID
TEAM_ID=$(linear teams list --json | jq -r '.data[0].id')

# Basic project
linear projects create "Q2 Product Launch" --teams "$TEAM_ID" --json

# Full setup
linear projects create "Mobile App Rewrite" \
  --teams "$TEAM_ID" \
  --description "Complete rewrite of the iOS and Android apps" \
  --state started \
  --lead USER_ID \
  --start-date 2026-04-01 \
  --target-date 2026-09-30 \
  --priority 1 \
  --color "#5e6ad2" \
  --json

# Dry-run first
linear projects create "Test" --teams "$TEAM_ID" --dry-run --json
```

## Milestones

```bash
# List milestones for a project
linear milestones list --project PROJECT_ID --json

# Create milestones
linear milestones create "Alpha release" --project PROJECT_ID --target-date 2026-06-01
linear milestones create "Beta release" --project PROJECT_ID --target-date 2026-07-15
linear milestones create "GA launch" --project PROJECT_ID --target-date 2026-09-30

# Update milestone
linear milestones update MILESTONE_ID --name "Beta v2" --target-date 2026-08-01

# Delete milestone
linear milestones delete MILESTONE_ID --yes
```

## Project Updates

```bash
# List recent updates
linear project-updates list --project PROJECT_ID --json

# Write an update
linear project-updates create PROJECT_ID \
  "On track. Completed auth module this week. Starting API integration next." \
  --health onTrack \
  --json

# Health values: onTrack, atRisk, offTrack

# Delete an update
linear project-updates delete UPDATE_ID --yes
```

## Roadmap Integration

```bash
# List roadmaps
linear roadmaps list --json

# Get roadmap with projects
linear roadmaps get ROADMAP_ID --json | jq '.data.projects.nodes[] | {name, state, progress}'

# Create a roadmap
linear roadmaps create "H2 2026 Roadmap" --json
```

## Initiative Integration

```bash
# List initiatives
linear initiatives list --json

# Get initiative with linked projects
linear initiatives get INITIATIVE_ID --json | jq '.data.projects.nodes[]'

# Create an initiative
linear initiatives create "Platform Modernization" \
  --description "Migrate all services to new architecture" \
  --target-date 2026-12-31 \
  --json
```

## Project Lifecycle

```bash
# 1. Create project
PROJECT=$(linear projects create "New Feature" --teams "$TEAM_ID" --json | jq -r '.data.id')

# 2. Add milestones
linear milestones create "Design complete" --project "$PROJECT" --target-date 2026-05-01
linear milestones create "Development complete" --project "$PROJECT" --target-date 2026-06-15

# 3. Check progress
linear projects get "$PROJECT" --json | jq '{progress: .data.progress, scope: .data.scope}'

# 4. Write update
linear project-updates create "$PROJECT" "Kicked off. Design phase started." --health onTrack

# 5. Archive when done
linear projects archive "$PROJECT"
```

## Pipe Patterns

| From | To | Pattern |
|------|----|---------|
| Projects | Issue counts | `linear projects list --json \| jq '.data[] \| {name, state, progress}'` |
| Project | Its issues | `linear issues list --project PROJECT_ID --all --json` |
| Search | Detail | `linear projects search "mobile" --json \| jq -r '.data[0].id' \| xargs linear projects get --json` |

## Gotchas

- `--teams` is required for create (comma-separated team IDs)
- Project `state` values: `planned`, `started`, `paused`, `completed`, `canceled`
- `progress` is 0.0-1.0 (auto-calculated from issues)
- `scope` is the total number of issues in the project
- Projects are cached for 5 minutes - use `--no-cache` for fresh data
- Milestones belong to projects - always pass `--project`
- Project updates require a health status: `onTrack`, `atRisk`, `offTrack`
