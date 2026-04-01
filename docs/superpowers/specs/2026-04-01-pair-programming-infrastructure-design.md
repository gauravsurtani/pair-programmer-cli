# Pair Programming Infrastructure — Design Spec

**Date:** 2026-04-01
**Status:** Approved
**Author:** Gaurav Surtani

## Problem

Two developers building one app together face constant git friction — branches, merges, rebases, conflicts. AI coding agents (Claude Code, Codex) are single-user by design. No tool exists today that lets 2+ devs share an AI coding session seamlessly.

## Vision

Multiplayer middleware for AI coding agents — the collaboration layer that lets 2+ devs share one AI session without git pain. Started as a hackathon project, intended to become an open-source tool and eventually a product.

## Core Insight

The Session Broker is the product. Everything else — clients, agents, workspaces — is pluggable.

```
┌─────────────────────────────────────────────────┐
│              CLIENTS (any transport)             │
│  Telegram | Web UI | CLI Plugin | VS Code Ext   │
└─────────┬───────────┬──────────────┬────────────┘
          |           |              |
          v           v              v
┌─────────────────────────────────────────────────┐
│            SESSION BROKER (the core)             │
│                                                  │
│  Input Queue    Output Broadcast   Identity &    │
│  (mux)          (fan-out)          Attribution   │
│                                                  │
│  File           Context            Conflict      │
│  Ownership      Handoff            Prevention    │
└──────────────────┬──────────────────────────────┘
                   |
                   v
┌─────────────────────────────────────────────────┐
│           AI CODING AGENT (pluggable)            │
│  Claude Code | Codex | Gemini CLI | Cursor       │
└──────────────────┬──────────────────────────────┘
                   |
                   v
┌─────────────────────────────────────────────────┐
│              SHARED WORKSPACE                    │
│  Local worktree | Codespace | Gitpod | SSH box   │
└─────────────────────────────────────────────────┘
```

## Roadmap

### V1 — Telegram Smart Pair Mode (build now)

**Interface:** Telegram bot (existing pair mode, enhanced)
**Users:** Gaurav + co-dev (dogfooding)
**Goal:** Make existing pair mode feel like real pair programming

#### Features

1. **GitHub Issues Integration**
   - `/issues` — lists open issues from the connected repo
   - `/pick #12` — assigns issue to the dev, visible to both
   - Tracks who is working on what issue
   - Source: GitHub Issues via `gh` CLI (already used for PR creation)

2. **File Ownership Tracking**
   - Claude automatically tracks which files each dev is modifying
   - When Dev B asks Claude to edit a file Dev A owns, Claude warns: "[@devA] is working on `api/auth.py` — proceed anyway?"
   - Ownership is implicit (based on which dev requested changes to which files), not manually assigned
   - Stored in-memory on the PairSession object

3. **Context Handoff**
   - `/handoff` — packages the current dev's working context and transfers it
   - Claude generates a handoff summary: what was attempted, what worked, what failed, what's remaining
   - The receiving dev gets this context injected into the shared session
   - Replaces the existing `/handoff` command which only swaps the driver

4. **Diff Summaries in Chat**
   - After every Claude change, the bot posts a summary to the group chat:
     ```
     [@gaurav] requested -> 3 files changed:
       app/api/auth.py  (+45 -2)  new login endpoint
       app/models/user.py  (+12)  added User model
       tests/test_auth.py  (+30)  login tests
     ```
   - Both devs see what changed without reading raw Claude output
   - Implementation: parse Claude's stream-json output for file edit events

5. **Auto-Commit**
   - Claude commits after each completed task/issue automatically
   - Commit message includes issue reference: `feat: add login endpoint (#12)`
   - No manual `/checkpoint` needed
   - Still on shared branch, no merge required

#### What V1 does NOT include
- Web UI or dashboard
- Standalone broker service
- Authentication or multi-tenant support
- Multi-agent support (only Claude Code)
- Real-time code sync
- Cloud-hosted infrastructure

### V2 — Standalone Session Broker + File Locking

**Interface:** Telegram + standalone broker API
**Users:** Small teams (2-3 devs)

#### Key additions
- Extract Session Broker as a standalone daemon/service
- Agent-agnostic interface (Claude Code, Codex, Gemini CLI)
- File-level locking (not just warnings — actual lock/unlock)
- Shared session with file awareness as core primitive
- API that any client can connect to
- Web dashboard for session management

#### Architecture change
```
V1:  Telegram --> Bot --> Claude Process (monolithic)

V2:  Telegram --┐
     CLI -------+---> Session Broker (daemon) ---> Agent Interface
     Web UI ----┘           |                        |
                      File Lock                Claude | Codex | etc.
                      Context
                      Ownership
```

### V3 — Live Sync + Real-time Co-editing

**Interface:** Web UI + VS Code extension
**Users:** Broader dev community

#### Key additions
- CRDT-based file synchronization
- Both devs see code changes in real-time
- Live application preview (both devs see the running app)
- VS Code extension for native editor integration
- Potentially open source contributors and agencies as users

## V1 Technical Design

### Components to modify

#### `orchestrator/pair/session.py` — PairSession model
- Add `file_ownership: dict[str, int]` — maps file paths to user_id
- Add `active_issues: dict[int, int]` — maps issue number to user_id
- Add `handoff_history: list[dict]` — log of handoff summaries

#### `orchestrator/pair/manager.py` — PairManager
- Add `track_file_ownership()` — called after Claude edits files, updates ownership map
- Add `check_file_conflict()` — called before sending message to Claude, warns if touching owned files
- Add `generate_handoff_context()` — asks Claude to summarize current state for handoff
- Add `format_diff_summary()` — parses Claude output for file changes, formats for chat

#### New: `orchestrator/pair/issues.py` — GitHub Issues integration
- `list_issues()` — runs `gh issue list` on the repo
- `pick_issue(issue_number, user_id)` — assigns issue to dev
- `complete_issue(issue_number)` — marks done, links to commit
- `get_issue_board()` — formatted view of who's working on what

#### `orchestrator/pair/handlers.py` — new Telegram commands
- `/issues` — show issue board
- `/pick #N` — claim an issue
- `/done` — mark current issue complete + auto-commit
- Enhanced `/handoff` — full context transfer (not just driver swap)

#### `orchestrator/sessions/claude_process.py` — output parsing
- Parse stream-json for file edit events
- Extract file paths, line counts, change descriptions
- Feed into file ownership tracker and diff summary formatter

### Data flow for a typical session

```
1. Both devs in Telegram group
2. Dev A: /issues           --> bot shows open GitHub issues
3. Dev A: /pick #12         --> bot assigns #12 to Dev A
4. Dev B: /pick #15         --> bot assigns #15 to Dev B
5. Dev A: "build login API" --> Claude edits auth.py, user.py
   --> bot posts diff summary to group
   --> file ownership: auth.py->DevA, user.py->DevA
6. Dev B: "add user model"  --> Claude warns: user.py owned by Dev A
   --> Dev B confirms or picks different approach
7. Dev A: /handoff          --> Claude generates context summary
   --> Dev B receives full context of what Dev A did
8. Dev A: /done             --> auto-commit with "feat: login API (#12)"
```

### Dependencies
- `gh` CLI (already used for PR creation in worktree manager)
- No new Python packages needed
- SQLite schema unchanged (pair sessions are in-memory)

## Success Criteria

V1 is successful when:
- Two devs can pick separate issues and work on them via the same Telegram group
- Neither dev accidentally overwrites the other's work
- Context transfers cleanly when one dev hands off to another
- Both devs always know what changed and why without reading raw Claude output
- Zero manual git commands needed during a session

## Future Considerations (not V1)

- **Auth & multi-tenancy** — needed for V2 when small teams adopt
- **Session recording/replay** — useful for async teams in different timezones
- **Cost splitting** — per-dev budget tracking (partially exists)
- **Agent marketplace** — swap between Claude, Codex, Gemini per task
- **Conflict resolution UI** — when two devs DO need the same file, structured resolution flow
