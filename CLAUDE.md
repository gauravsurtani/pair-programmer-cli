# Pair Programmer CLI

## Overview
Multiplayer middleware for AI coding agents. Share AI coding sessions with your team — no git friction.

## Stack
- **Python 3.12** — async throughout
- **aiogram 3** — Telegram bot framework
- **aiosqlite** — session persistence
- **Pydantic 2** — data models
- **Claude Code CLI** — AI coding agent (pluggable)
- **gh CLI** — GitHub Issues + PR creation

## Architecture
Telegram bot manages shared Claude Code sessions. Two modes:
- **Split mode** — isolated per-user sessions with worktrees
- **Pair mode** — shared session, driver/navigator, file ownership, context handoff

## Branch Strategy
- Main branch: `main`
- Feature branches: `feat/<name>`

## Testing
- `python -m pytest tests/ -v`
- All tests use mocks (no real Claude/gh calls)
