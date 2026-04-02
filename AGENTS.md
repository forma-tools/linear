# Linear CLI - AI Assistant Guide

> Linear project management - issues, projects, teams, cycles from the command line.

**Status:** Scaffolded - awaiting implementation.
**API:** [Linear GraphQL API](https://developers.linear.app/docs/graphql/working-with-the-graphql-api)
**Auth:** API key from [linear.app/settings/api](https://linear.app/settings/api)

## Planned Commands

| Command | Description |
|---------|-------------|
| `linear issues list [--team] [--status] [--assignee] [--json]` | List issues |
| `linear issues get <id> [--json]` | Get issue details |
| `linear issues create --title "..." --team ENG [--json]` | Create issue |
| `linear issues update <id> --status "Done" [--json]` | Update issue |
| `linear projects list [--json]` | List projects |
| `linear projects get <id> [--json]` | Get project details |
| `linear teams list [--json]` | List teams |
| `linear cycles list [--team] [--json]` | List cycles |
| `linear labels list [--json]` | List labels |
| `linear users list [--json]` | List users |
| `linear auth login` | Store API key |
| `linear auth status [--json]` | Check authentication |
| `linear auth logout` | Clear credentials |

## API Notes

- Linear uses GraphQL, not REST
- API key goes in `Authorization: Bearer <key>` header
- Endpoint: `https://api.linear.app/graphql`
- Issues have identifiers like `ENG-123` (team prefix + number)
- Pagination uses cursor-based `after` parameter
