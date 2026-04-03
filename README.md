# Pair Programmer CLI

Multiplayer middleware for AI coding agents. Two devs, one AI session, zero merge conflicts.

Share a Claude Code session with your teammate via Telegram. No git branches, no merge headaches — just chat and build.

## Quick Setup

### 1. Create a Telegram Bot

Open Telegram, message `@BotFather`, send `/newbot`, pick a name, grab the token.

### 2. Clone and Configure

```bash
git clone https://github.com/gauravsurtani/pair-programmer-cli.git
cd pair-programmer-cli
pip install -r requirements.txt

echo "TELEGRAM_BOT_TOKEN=your-token-here" > .env
```

### 3. Point to Your Repo

By default it uses the current git repo. To work on a different project:

```bash
echo "REPO_ROOT=/path/to/your/project" >> .env
```

### 4. Start the Bot

```bash
python -m orchestrator.main
```

## How It Works

DM the bot or add it to a group chat with your teammate.

```
You:       /pair auth-feature
Bot:       Pair session started: auth-feature
           Branch: feat/auth-feature

Teammate:  /join
Bot:       @teammate joined! Members: @you, @teammate

You:       /issues
Bot:       #12 | Add login API | backend |
           #15 | Build signup form | frontend |

You:       /pick #12
Teammate:  /pick #15

You:       build the login endpoint with JWT auth
Bot:       [auth-feature]
           Built login endpoint at app/api/auth.py...

           [@you] requested -> 2 files changed:
             app/api/auth.py  (new)
             tests/test_auth.py  (new)

You:       /done
Bot:       Issue #12 completed.
           Committed: feat: complete issue #12 — auth-feature

You:       /handoff
Bot:       Driver handed off to @teammate.
           Context: Built JWT login endpoint. Tests pass.
           TODO: add refresh token support.

Teammate:  now build the signup form
Bot:       [auth-feature] Built signup component...

Teammate:  /done
           /endpair
Bot:       Session ended. PR: github.com/you/app/pull/3
```

## Commands

### Pair Mode (shared session)

| Command | What it does |
|-|-|
| `/pair <name>` | Start a shared session |
| `/join` | Join the active session |
| `/leave` | Leave without ending |
| `/issues` | See open GitHub issues |
| `/pick #N` | Claim an issue |
| `/done` | Auto-commit + close your issue |
| `/handoff` | Transfer full context to teammate |
| `/driver @user` | Only that person talks to AI |
| `/both` | Everyone can talk (default) |
| `/code file.py` | View a file in chat |
| `/test [args]` | Run tests, share results |
| `/undo` | Revert last change |
| `/checkpoint [msg]` | Commit without ending |
| `/session-info` | Session state + Claude session ID |
| `/endpair` | Push + create PR + cleanup |

### Split Mode (solo sessions)

| Command | What it does |
|-|-|
| `/claim <task>` | Start an isolated session |
| `/status` | See all active sessions |
| `/park` | Pause (saves context) |
| `/resume` | Pick up where you left off |
| `/sync` | Rebase on main |
| `/merge` | Push + create PR + cleanup |
| `/kill` | Force-stop and remove |

### Help

| Command | What it does |
|-|-|
| `/help` | Overview with interactive buttons |
| `/help-pair` | Pair mode guide |
| `/help-split` | Solo mode guide |
| `/help-flow` | Step-by-step walkthrough |
| `/help-tips` | Pro tips |

## Features

- **File ownership tracking** — the bot knows who's editing what and warns about conflicts
- **Diff summaries** — after every AI change, both devs see what files changed
- **Context handoff** — AI generates a full summary when you swap drivers
- **Auto-commit** — completes issues with proper commit messages
- **Session persistence** — pair sessions survive bot restarts
- **Process timeout** — 120s timeout prevents hung sessions
- **GitHub Issues** — pull issues from your repo, claim and complete them

## Configuration

All settings via environment variables in `.env`:

| Variable | Default | Description |
|-|-|-|
| `TELEGRAM_BOT_TOKEN` | (required) | Your Telegram bot token |
| `REPO_ROOT` | current git repo | Path to the project repo |
| `WORKTREE_BASE` | `/tmp/orchestrator` | Where git worktrees are created |
| `CLAUDE_BIN` | `claude` | Path to Claude Code CLI |
| `SESSION_BUDGET_USD` | `5.0` | Max cost per session |
| `IDLE_TIMEOUT_SECONDS` | `600` | Auto-park after this many idle seconds |
| `CLAUDE_TIMEOUT_SECONDS` | `120` | Kill Claude process after this timeout |
| `MAX_SESSIONS` | `5` | Max concurrent split-mode sessions |

## Requirements

- Python 3.12+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- [GitHub CLI](https://cli.github.com/) (`gh`) for issues and PRs
- A Telegram bot token

## Tech Stack

- **aiogram 3** — async Telegram bot framework
- **aiosqlite** — session persistence
- **Pydantic 2** — data models
- **Claude Code CLI** — AI coding agent

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

MIT
