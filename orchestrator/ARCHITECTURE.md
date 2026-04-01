# Multiplayer Claude Code Orchestrator via Telegram

## Context

Hackathon teams need to pair-program on the same codebase, but Claude Code's Telegram integration is single-session. This orchestrator lets multiple team members work in parallel — each person claims a task, gets an isolated git worktree + Claude Code session, and interacts via the shared Telegram group. The orchestrator routes messages by user, manages branches, and handles merging.

**What exists today:**
- Jizo voice agent project in `/Users/gauravsurtani/projects/japan_hackathon`
- Claude Code v2.1.81 with full headless support (`--print --output-format stream-json --input-format stream-json`)
- Telegram bot token in `.telegram/.env`, access control in `.telegram/access.json`
- FastAPI backend, Python 3.12.11, pydantic + aiosqlite already installed

**What we're building:**
A Python service (`orchestrator/`) inside the existing repo that runs as a Telegram bot, spawning isolated Claude Code subprocesses per team member.

---

## Architecture

```
Telegram Group Chat
    |
    +-- /claim, /status, /merge, /sync commands
    +-- Regular messages routed by user_id
    |
    v
Orchestrator (Python asyncio)
    |
    +-- Bot Layer (aiogram)     -- parse commands, route messages
    +-- Session Manager         -- user_id -> Claude process mapping
    +-- Worktree Manager        -- git worktree create/remove/sync
    +-- Storage (SQLite)        -- persist session state across restarts
    +-- Activity Feed           -- broadcast events to group
    |
    +-------+-------+-------+
    |       |       |       |
  Session1 Session2 Session3
  claude   claude   claude
  --print  --print  --print
  stream   stream   stream
    |       |       |
  worktree worktree worktree
  feat/ui  feat/api feat/docs
```

---

## Key Design Decisions

| Decision | Choice | Why |
|-|-|-|
| Claude mode | `--bare` + `--append-system-prompt-file CLAUDE.md` | Skip hooks/plugins in headless, explicitly pass project context |
| Permissions | `--permission-mode bypassPermissions` | Non-interactive subprocess; each worktree limits blast radius |
| Bot framework | `aiogram` v3 (async-native) | Entire system is asyncio; aiogram has best async support |
| Telegram bot | **New bot** via BotFather (separate from existing MCP plugin bot) | Avoid conflicts with the existing single-session Telegram integration |
| Session recovery | `--resume <session_id>` captured from stream-json `init` event | Enables park/resume without losing conversation context |
| Budget control | `--max-budget-usd 5.00` per session (configurable) | Prevent runaway costs during hackathon |
| Storage | aiosqlite (already installed) | Lightweight, zero-config, survives restarts |
| Location | `orchestrator/` inside the hackathon repo | Single repo deployment, shared CLAUDE.md |

---

## Directory Structure

```
orchestrator/
  __init__.py
  main.py                    # Entry point: wire bot + session manager + idle checker
  config.py                  # Env loading, constants (REPO_ROOT, WORKTREE_BASE, etc.)
  models.py                  # Pydantic: Session, SessionStatus, MergeResult
  bot/
    __init__.py
    handlers.py              # /claim, /status, /merge, /sync, /park, /resume, /kill
    middleware.py             # User identification, rate limiting
    formatters.py            # Status tables, message truncation
  sessions/
    __init__.py
    manager.py               # SessionManager: lifecycle orchestration
    claude_process.py        # ClaudeProcess: subprocess wrapper (stream-json I/O)
    stream_parser.py         # Parse stream-json events from Claude stdout
  worktrees/
    __init__.py
    manager.py               # WorktreeManager: git worktree CRUD, conflict detection
  storage/
    __init__.py
    db.py                    # aiosqlite CRUD for sessions table
    schema.sql               # CREATE TABLE sessions (...)
  activity/
    __init__.py
    feed.py                  # Broadcast events to Telegram group
  requirements.txt           # aiogram>=3.15.0 (only new dep)
```

---

## Build Phases

### Phase 0: Validate Core Loop (30 min)
**Goal:** Prove Claude CLI subprocess works with stream-json bidirectionally.

- [ ] Write a standalone test script (`orchestrator/test_claude_subprocess.py`)
- [ ] Spawn `claude --print --output-format stream-json --input-format stream-json --bare --permission-mode bypassPermissions` as asyncio subprocess
- [ ] Send `{"type":"user_message","content":"What files are in the current directory?"}` via stdin
- [ ] Read and parse stream-json lines from stdout
- [ ] Verify we get an assistant response with file listing
- [ ] Test `--resume <session_id>` with the captured session_id

**If this fails:** Pivot to `claude "prompt" --print --output-format json` (one-shot mode per message, no stateful sessions). Workable but slower.

**Files:** `orchestrator/test_claude_subprocess.py`

### Phase 1: Foundation (1 hour)
**Goal:** Config, models, storage, worktree management — all independently testable.

- [ ] `config.py` — load env vars, define constants
  - `REPO_ROOT` from `git rev-parse --show-toplevel`
  - `WORKTREE_BASE = /tmp/orchestrator`
  - `CLAUDE_BIN = claude`
  - `TELEGRAM_TOKEN` from env
  - `MAX_SESSIONS = 5`, `SESSION_BUDGET = 5.0`, `IDLE_TIMEOUT = 600`
- [ ] `models.py` — Session (user_id, username, task_name, branch, worktree_path, status, claude_session_id, pid, created_at, last_activity, total_cost_usd, max_budget_usd, error_count), SessionStatus enum (active/parked/merging/done/error)
- [ ] `storage/schema.sql` + `storage/db.py` — sessions table CRUD
- [ ] `worktrees/manager.py` — create (git worktree add -b feat/X origin/main), remove, sync (fetch + rebase), get_changed_files, detect_conflicts

**Verify:** Create a worktree, confirm with `git worktree list`, remove it.

**Files:** `config.py`, `models.py`, `storage/db.py`, `storage/schema.sql`, `worktrees/manager.py`

### Phase 2: Claude Process Wrapper (1.5 hours)
**Goal:** Reliable bidirectional communication with Claude CLI subprocesses.

- [ ] `sessions/stream_parser.py` — parse stream-json lines into typed events
  - Handle event types: `system` (init → capture session_id), `assistant` (extract text content), `result` (capture cost/tokens), `tool_use` (skip from Telegram display)
- [ ] `sessions/claude_process.py` — ClaudeProcess class
  - `start(resume_session_id=None)` — spawn subprocess with correct flags, start stdout reader
  - `send_message(text)` — write stream-json to stdin
  - `_read_stdout()` — async line reader, dispatch to output_callback
  - `kill()` — graceful terminate with timeout
  - Crash detection: catch `ProcessExited`, auto-retry up to 3x with `--resume`
  - Budget tracking: extract `total_cost_usd` from result events

**Claude CLI spawn command:**
```
claude --print \
  --output-format stream-json \
  --input-format stream-json \
  --permission-mode bypassPermissions \
  --max-budget-usd {budget} \
  --bare \
  --append-system-prompt-file {worktree}/CLAUDE.md \
  --append-system-prompt "Task: {task_name}. Branch: feat/{task_name}. Keep changes focused."
```
Run with `cwd={worktree_path}`.

**Verify:** Spawn a process, send 3 messages, get 3 responses, kill, resume, verify context preserved.

**Files:** `sessions/stream_parser.py`, `sessions/claude_process.py`

### Phase 3: Session Manager + Telegram Bot (2 hours)
**Goal:** Full user-facing system.

- [ ] `sessions/manager.py` — SessionManager
  - `claim(user_id, username, task_name)` — validate uniqueness, create worktree, spawn process, save to DB
  - `send_message(user_id, text)` — forward to user's active ClaudeProcess
  - `park(user_id)` — kill process, save session_id, update status
  - `resume(user_id)` — respawn with `--resume`
  - `merge(user_id)` — kill process, detect conflicts, push branch, create PR via `gh pr create`, cleanup
  - `sync(user_id)` — rebase on main
  - `kill(user_id)` — force cleanup
  - `get_status()` — return all sessions
  - `restore_from_db()` — on startup, load sessions, mark orphaned active sessions as error
  - `check_idle()` — auto-park sessions idle > IDLE_TIMEOUT

- [ ] `bot/handlers.py` — register with aiogram Dispatcher
  - `/claim <task>` → session_mgr.claim()
  - `/status` → format session table, reply
  - `/park` → session_mgr.park()
  - `/resume` → session_mgr.resume()
  - `/merge` → session_mgr.merge()
  - `/sync` → session_mgr.sync()
  - `/kill` → session_mgr.kill()
  - Non-command messages → check for active session → session_mgr.send_message()
  - No active session → reply "No active session. Use /claim <task>"

- [ ] `bot/formatters.py`
  - Status table formatter (task, user, branch, status, cost)
  - Message truncation (Telegram 4096 char limit → split into chunks)
  - Response prefix: `[feat/task-name] response text...`

- [ ] `bot/middleware.py` — extract user info from Telegram Update

- [ ] `activity/feed.py` — broadcast events (claim, park, resume, merge, error, sync)

- [ ] `main.py` — wire everything, start polling, start idle checker loop

**Verify:** Full E2E in Telegram — /claim, send messages, see Claude responses, /park, /resume, /merge.

**Files:** All files in `sessions/`, `bot/`, `activity/`, `main.py`

### Phase 4: Polish & Hardening (1 hour)

- [ ] Idle timeout auto-parking (asyncio periodic task every 60s)
- [ ] Conflict detection on `/merge` — cross-reference changed files across active branches
- [ ] Cost tracking in `/status` output
- [ ] Graceful shutdown handler (SIGTERM → park all sessions, close DB)
- [ ] Orphan worktree cleanup on startup (scan /tmp/orchestrator/*, cross-ref with DB)
- [ ] Error messages: clear, actionable (not stack traces)

---

## Telegram Commands Reference

| Command | Args | Behavior |
|-|-|-|
| `/claim <task>` | task slug | Create worktree + branch + Claude session for you |
| `/status` | — | Show all sessions: who, task, branch, status, cost |
| `/park` | — | Pause your session (saves context for resume) |
| `/resume` | — | Restart your paused session with full context |
| `/merge` | — | Push branch, create PR to main, cleanup |
| `/sync` | — | Rebase your branch on latest main |
| `/kill` | — | Force-stop session and delete worktree (no merge) |
| (any text) | — | Routed to your active Claude session |

---

## Data Model

```python
class SessionStatus(str, Enum):
    ACTIVE = "active"
    PARKED = "parked"
    MERGING = "merging"
    DONE = "done"
    ERROR = "error"

class Session(BaseModel):
    user_id: int
    username: str
    task_name: str
    branch: str                    # feat/<task_name>
    worktree_path: str             # /tmp/orchestrator/feat-<task_name>
    status: SessionStatus
    claude_session_id: str | None  # For --resume
    pid: int | None
    created_at: datetime
    last_activity: datetime
    total_cost_usd: float
    max_budget_usd: float          # Default 5.0
    error_count: int               # For retry logic (max 3)
```

```sql
CREATE TABLE sessions (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    task_name TEXT UNIQUE NOT NULL,
    branch TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    claude_session_id TEXT,
    created_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    total_cost_usd REAL DEFAULT 0.0,
    max_budget_usd REAL DEFAULT 5.0,
    error_count INTEGER DEFAULT 0
);
```

---

## Error Handling

| Failure | Detection | Recovery |
|-|-|-|
| Claude subprocess crashes | `proc.returncode is not None` in stdout reader | Auto-restart with `--resume`, max 3 retries, then park + notify |
| Budget exhaustion | `result` event with cost >= max_budget | Park session, notify user with cost summary |
| Git worktree create fails | Non-zero exit code | Reply with git error message |
| Merge conflict during rebase | Non-zero exit from `git rebase` | `git rebase --abort`, notify user to resolve manually |
| Telegram message too long | `len(text) > 4096` | Split into 4000-char chunks |
| Orchestrator restarts | Active sessions in DB with no running process | Mark as error on startup, user can `/resume` |
| Two users claim same task | UNIQUE constraint on task_name | Reject with clear error |

---

## Dependencies

```
# orchestrator/requirements.txt
aiogram>=3.15.0    # Only new dependency
# Already installed: aiosqlite, pydantic
```

---

## Verification Plan

### Phase 0 Test (automated)
```bash
cd /Users/gauravsurtani/projects/japan_hackathon
python orchestrator/test_claude_subprocess.py
# Expected: sends message, gets response, prints parsed events
```

### Phase 1 Test (automated)
```bash
python -c "
import asyncio
from orchestrator.worktrees.manager import WorktreeManager
wm = WorktreeManager(...)
asyncio.run(wm.create('test-worktree'))
# Verify: git worktree list shows it
asyncio.run(wm.remove('test-worktree'))
"
```

### Phase 2 Test (automated, costs ~$0.10)
```bash
python -c "
import asyncio
from orchestrator.sessions.claude_process import ClaudeProcess
# Spawn, send 3 messages, verify 3 responses, kill, resume
"
```

### Phase 3 E2E Test (manual, 2 people)
1. Start orchestrator: `python -m orchestrator.main`
2. Person A in Telegram: `/claim frontend-ui`
3. Person A: "Add a dark mode toggle to the header"
4. Verify: Claude responds with code changes in worktree A
5. Person B in Telegram: `/claim api-endpoint`
6. Person B: "Add a /health endpoint"
7. Verify: Claude responds in worktree B (independent from A)
8. `/status` — shows both sessions with branches and costs
9. Person A: `/merge` — PR created, worktree cleaned
10. Person B: `/sync` — rebases on main with Person A's changes
11. Person B: `/merge` — clean merge
12. Verify: both features on main

### Stress Test
- `/claim` 5 tasks simultaneously → verify all worktrees created
- Send messages to all 5 in rapid succession → verify no cross-contamination
- Kill orchestrator process → restart → verify sessions restore from DB
