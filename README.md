# Linear

[![Forma](https://img.shields.io/badge/forma-experimental-orange.svg)](https://github.com/forma-tools/forma)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> Linear project management - issues, projects, teams, cycles.

A Forma CLI tool wrapping the [Linear GraphQL API](https://developers.linear.app/docs/graphql/working-with-the-graphql-api) for managing issues, projects, teams, and cycles from the command line.

## Install

```bash
uv pip install -e .
```

## Quick Start

```bash
linear auth login
linear issues list
linear issues list --team ENG --status "In Progress" --json
```

## Status

Scaffolded - awaiting implementation.

## Forma Protocol

This tool follows the [Forma Protocol](https://github.com/forma-tools/forma) v0.7.0.
