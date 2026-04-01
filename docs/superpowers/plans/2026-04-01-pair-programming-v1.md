# Pair Programming V1 — Smart Telegram Pair Mode

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the existing Telegram pair programming mode with GitHub Issues integration, file ownership tracking, context handoff, diff summaries, and auto-commit — so two devs can build one app without git friction.

**Architecture:** Extend the existing `PairSession` model with ownership/issues state. Add a new `issues.py` module for `gh` CLI integration. Modify `ClaudeProcess` to emit structured file-change events. Wire new Telegram commands (`/issues`, `/pick`, `/done`) into the pair router.

**Tech Stack:** Python 3.12, aiogram 3, aiosqlite, Pydantic 2, `gh` CLI, `git` CLI

---

## File Map

| File | Action | Responsibility |
|-|-|-|
| `orchestrator/pair/session.py` | Modify | Add `file_ownership`, `active_issues`, `handoff_history` fields |
| `orchestrator/pair/issues.py` | Create | GitHub Issues integration via `gh` CLI |
| `orchestrator/pair/file_tracker.py` | Create | Parse Claude output for file changes, track ownership, detect conflicts |
| `orchestrator/pair/manager.py` | Modify | Add file tracking, conflict checking, handoff context, auto-commit |
| `orchestrator/pair/handlers.py` | Modify | Add `/issues`, `/pick`, `/done` commands |
| `orchestrator/sessions/claude_process.py` | Modify | Emit file-change events from stream-json parsing |
| `tests/test_pair_session.py` | Create | Unit tests for PairSession model extensions |
| `tests/test_issues.py` | Create | Unit tests for GitHub Issues module |
| `tests/test_file_tracker.py` | Create | Unit tests for file tracking and conflict detection |
| `tests/test_pair_manager.py` | Create | Integration tests for enhanced PairManager |

---

### Task 1: Extend PairSession Model

**Files:**
- Modify: `orchestrator/pair/session.py:28-76`
- Create: `tests/test_pair_session.py`

- [ ] **Step 1: Write failing tests for new PairSession fields**

```python
# tests/test_pair_session.py
"""Tests for PairSession model extensions."""

from orchestrator.pair.session import PairSession


def test_file_ownership_default_empty():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    assert session.file_ownership == {}


def test_track_file_ownership():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.add_member(100, "alice")
    session.set_file_owner("app/api.py", 100)
    assert session.file_ownership["app/api.py"] == 100


def test_get_file_owner():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.add_member(100, "alice")
    session.set_file_owner("app/api.py", 100)
    assert session.get_file_owner("app/api.py") == 100
    assert session.get_file_owner("unknown.py") is None


def test_check_file_conflict_no_conflict():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.add_member(100, "alice")
    session.set_file_owner("app/api.py", 100)
    # Same user — no conflict
    conflicts = session.check_conflicts(["app/api.py"], 100)
    assert conflicts == []


def test_check_file_conflict_detected():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.add_member(100, "alice")
    session.add_member(200, "bob")
    session.set_file_owner("app/api.py", 100)
    # Different user — conflict
    conflicts = session.check_conflicts(["app/api.py"], 200)
    assert conflicts == [("app/api.py", 100)]


def test_active_issues_default_empty():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    assert session.active_issues == {}


def test_assign_issue():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.assign_issue(12, 100)
    assert session.active_issues[12] == 100


def test_complete_issue():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.assign_issue(12, 100)
    session.complete_issue(12)
    assert 12 not in session.active_issues


def test_handoff_history():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.add_handoff("alice", "bob", "Built login API, tests passing")
    assert len(session.handoff_history) == 1
    assert session.handoff_history[0]["from_user"] == "alice"
    assert session.handoff_history[0]["to_user"] == "bob"
    assert session.handoff_history[0]["summary"] == "Built login API, tests passing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_session.py -v`
Expected: FAIL — `set_file_owner`, `get_file_owner`, `check_conflicts`, `assign_issue`, `complete_issue`, `add_handoff` not defined

- [ ] **Step 3: Implement PairSession extensions**

Add these fields and methods to `orchestrator/pair/session.py` in the `PairSession` class:

```python
# Add these fields after total_cost_usd in PairSession:
    file_ownership: dict[str, int] = Field(default_factory=dict)  # filepath -> user_id
    active_issues: dict[int, int] = Field(default_factory=dict)  # issue_number -> user_id
    handoff_history: list[dict] = Field(default_factory=list)

    def set_file_owner(self, filepath: str, user_id: int) -> None:
        self.file_ownership[filepath] = user_id

    def get_file_owner(self, filepath: str) -> int | None:
        return self.file_ownership.get(filepath)

    def check_conflicts(self, filepaths: list[str], user_id: int) -> list[tuple[str, int]]:
        """Return list of (filepath, owner_id) for files owned by someone else."""
        conflicts = []
        for fp in filepaths:
            owner = self.file_ownership.get(fp)
            if owner is not None and owner != user_id:
                conflicts.append((fp, owner))
        return conflicts

    def assign_issue(self, issue_number: int, user_id: int) -> None:
        self.active_issues[issue_number] = user_id

    def complete_issue(self, issue_number: int) -> None:
        self.active_issues.pop(issue_number, None)

    def add_handoff(self, from_user: str, to_user: str, summary: str) -> None:
        self.handoff_history.append({
            "from_user": from_user,
            "to_user": to_user,
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_session.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pair/session.py tests/test_pair_session.py
git commit -m "feat: extend PairSession with file ownership, issues, and handoff tracking"
```

---

### Task 2: GitHub Issues Module

**Files:**
- Create: `orchestrator/pair/issues.py`
- Create: `tests/test_issues.py`

- [ ] **Step 1: Write failing tests for GitHub Issues module**

```python
# tests/test_issues.py
"""Tests for GitHub Issues integration.

These tests mock the `gh` CLI subprocess calls.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.pair.issues import GitHubIssues


@pytest.fixture
def issues():
    return GitHubIssues(repo_root="/tmp/test-repo")


SAMPLE_GH_OUTPUT = json.dumps([
    {"number": 12, "title": "Add login API", "labels": [{"name": "backend"}], "assignees": []},
    {"number": 15, "title": "Build signup form", "labels": [{"name": "frontend"}], "assignees": []},
    {"number": 18, "title": "Fix CSS on mobile", "labels": [{"name": "bug"}], "assignees": []},
])


@pytest.mark.asyncio
async def test_list_issues(issues):
    with patch("orchestrator.pair.issues._run_gh", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, SAMPLE_GH_OUTPUT, "")
        result = await issues.list_issues()
        assert len(result) == 3
        assert result[0]["number"] == 12
        assert result[1]["title"] == "Build signup form"


@pytest.mark.asyncio
async def test_list_issues_empty(issues):
    with patch("orchestrator.pair.issues._run_gh", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "[]", "")
        result = await issues.list_issues()
        assert result == []


@pytest.mark.asyncio
async def test_format_issue_board(issues):
    with patch("orchestrator.pair.issues._run_gh", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, SAMPLE_GH_OUTPUT, "")
        board = await issues.format_board(picked={12: "alice", 15: "bob"})
        assert "#12" in board
        assert "alice" in board
        assert "#18" in board


@pytest.mark.asyncio
async def test_list_issues_gh_failure(issues):
    with patch("orchestrator.pair.issues._run_gh", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (1, "", "gh: not logged in")
        with pytest.raises(RuntimeError, match="gh: not logged in"):
            await issues.list_issues()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_issues.py -v`
Expected: FAIL — `orchestrator.pair.issues` module not found

- [ ] **Step 3: Implement GitHub Issues module**

```python
# orchestrator/pair/issues.py
"""GitHub Issues integration via gh CLI."""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


async def _run_gh(*args: str, cwd: str | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode().strip(), stderr.decode().strip()


class GitHubIssues:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root

    async def list_issues(self, state: str = "open", limit: int = 20) -> list[dict]:
        """Fetch open issues from the repo via gh CLI."""
        rc, out, err = await _run_gh(
            "issue", "list",
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,labels,assignees",
            cwd=self.repo_root,
        )
        if rc != 0:
            raise RuntimeError(f"Failed to list issues: {err}")
        return json.loads(out) if out else []

    async def format_board(self, picked: dict[int, str] | None = None) -> str:
        """Format issues as a readable board for Telegram."""
        issues = await self.list_issues()
        picked = picked or {}

        if not issues:
            return "No open issues."

        lines = ["# | Title | Labels | Claimed"]
        lines.append("-|-|-|-")
        for issue in issues:
            num = issue["number"]
            title = issue["title"]
            labels = ", ".join(lb["name"] for lb in issue.get("labels", []))
            claimed = f"@{picked[num]}" if num in picked else ""
            lines.append(f"#{num} | {title} | {labels} | {claimed}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_issues.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pair/issues.py tests/test_issues.py
git commit -m "feat: add GitHub Issues integration module"
```

---

### Task 3: File Change Tracker

**Files:**
- Create: `orchestrator/pair/file_tracker.py`
- Create: `tests/test_file_tracker.py`

- [ ] **Step 1: Write failing tests for file tracker**

```python
# tests/test_file_tracker.py
"""Tests for file change tracker — parses Claude stream-json for file edits."""

from orchestrator.pair.file_tracker import FileChange, parse_tool_events, format_diff_summary


def test_parse_edit_tool_event():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": "/tmp/repo/app/api.py", "old_string": "x", "new_string": "y"},
                    }
                ]
            },
        }
    ]
    changes = parse_tool_events(events, worktree_path="/tmp/repo")
    assert len(changes) == 1
    assert changes[0].filepath == "app/api.py"
    assert changes[0].action == "edit"


def test_parse_write_tool_event():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/tmp/repo/app/new_file.py", "content": "hello"},
                    }
                ]
            },
        }
    ]
    changes = parse_tool_events(events, worktree_path="/tmp/repo")
    assert len(changes) == 1
    assert changes[0].filepath == "app/new_file.py"
    assert changes[0].action == "create"


def test_parse_ignores_non_file_tools():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/repo/x.py"}},
                ]
            },
        }
    ]
    changes = parse_tool_events(events, worktree_path="/tmp/repo")
    assert changes == []


def test_parse_deduplicates_files():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/repo/app/api.py", "old_string": "a", "new_string": "b"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/repo/app/api.py", "old_string": "c", "new_string": "d"}},
                ]
            },
        }
    ]
    changes = parse_tool_events(events, worktree_path="/tmp/repo")
    assert len(changes) == 1
    assert changes[0].edit_count == 2


def test_format_diff_summary():
    changes = [
        FileChange(filepath="app/api.py", action="edit", edit_count=2),
        FileChange(filepath="app/new_file.py", action="create", edit_count=1),
    ]
    summary = format_diff_summary(changes, username="alice")
    assert "@alice" in summary
    assert "app/api.py" in summary
    assert "app/new_file.py" in summary
    assert "2 files changed" in summary


def test_format_diff_summary_empty():
    summary = format_diff_summary([], username="alice")
    assert summary == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_file_tracker.py -v`
Expected: FAIL — `orchestrator.pair.file_tracker` module not found

- [ ] **Step 3: Implement file tracker**

```python
# orchestrator/pair/file_tracker.py
"""Parse Claude stream-json events for file changes and format diff summaries."""

from __future__ import annotations

from dataclasses import dataclass, field

# Tools that modify files
_WRITE_TOOLS = {"Write", "write"}
_EDIT_TOOLS = {"Edit", "edit"}


@dataclass
class FileChange:
    filepath: str
    action: str  # "edit" or "create"
    edit_count: int = 1


def parse_tool_events(
    events: list[dict], worktree_path: str
) -> list[FileChange]:
    """Extract file changes from Claude stream-json tool_use events."""
    seen: dict[str, FileChange] = {}  # filepath -> FileChange

    for event in events:
        if event.get("type") != "assistant":
            continue
        content = event.get("message", {}).get("content", [])
        for block in content:
            if block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            filepath = tool_input.get("file_path", "")
            if not filepath:
                continue

            # Strip worktree prefix to get relative path
            if filepath.startswith(worktree_path):
                filepath = filepath[len(worktree_path):].lstrip("/")

            if tool_name in _EDIT_TOOLS:
                if filepath in seen:
                    seen[filepath].edit_count += 1
                else:
                    seen[filepath] = FileChange(filepath=filepath, action="edit")
            elif tool_name in _WRITE_TOOLS:
                if filepath not in seen:
                    seen[filepath] = FileChange(filepath=filepath, action="create")

    return list(seen.values())


def format_diff_summary(changes: list[FileChange], username: str) -> str:
    """Format file changes as a Telegram-friendly summary."""
    if not changes:
        return ""

    file_count = len(changes)
    lines = [f"[@{username}] requested -> {file_count} files changed:"]
    for c in changes:
        action_label = "new" if c.action == "create" else f"{c.edit_count} edits"
        lines.append(f"  {c.filepath}  ({action_label})")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_file_tracker.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pair/file_tracker.py tests/test_file_tracker.py
git commit -m "feat: add file change tracker for Claude stream-json parsing"
```

---

### Task 4: Extend ClaudeProcess to Emit File Change Events

**Files:**
- Modify: `orchestrator/sessions/claude_process.py:83-118`

- [ ] **Step 1: Write failing test for tool event capture**

```python
# tests/test_claude_process.py
"""Tests for ClaudeProcess tool event capture."""

import json

import pytest

from orchestrator.sessions.claude_process import ClaudeProcess


def test_tool_events_collected():
    """Verify that _read_response collects tool_use events."""
    proc = ClaudeProcess(worktree_path="/tmp/test", task_name="test")
    # After parsing, tool_events should be accessible
    assert proc.last_tool_events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_claude_process.py::test_tool_events_collected -v`
Expected: FAIL — `last_tool_events` not defined

- [ ] **Step 3: Add tool event capture to ClaudeProcess**

In `orchestrator/sessions/claude_process.py`:

Add field after `self._lock`:
```python
        self.last_tool_events: list[dict] = []
```

In `_read_response`, add a new `elif` block after the `elif etype == "assistant":` block to capture tool events. Also modify the existing `assistant` handler to store raw events:

```python
    async def _read_response(self) -> str:
        assert self._proc and self._proc.stdout
        parts: list[str] = []
        self.last_tool_events = []  # Reset for this invocation

        async for raw_line in self._proc.stdout:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")
            subtype = event.get("subtype", "")

            if etype == "system" and subtype == "init":
                sid = event.get("session_id")
                if sid:
                    self.session_id = sid
                    logger.info("Session ID: %s", sid[:16])

            elif etype == "assistant":
                content = event.get("message", {}).get("content", [])
                has_tool_use = False
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            parts.append(text)
                    elif block.get("type") == "tool_use":
                        has_tool_use = True
                if has_tool_use:
                    self.last_tool_events.append(event)

            elif etype == "result":
                cost = event.get("total_cost_usd", 0)
                if cost:
                    self.total_cost_usd = cost

        return "\n".join(parts) if parts else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_claude_process.py::test_tool_events_collected -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/sessions/claude_process.py tests/test_claude_process.py
git commit -m "feat: capture tool_use events in ClaudeProcess for file tracking"
```

---

### Task 5: Enhance PairManager with File Tracking, Conflict Detection, and Diff Summaries

**Files:**
- Modify: `orchestrator/pair/manager.py:89-111`
- Create: `tests/test_pair_manager.py`

- [ ] **Step 1: Write failing tests for enhanced send_message**

```python
# tests/test_pair_manager.py
"""Tests for enhanced PairManager — file tracking and conflict detection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.pair.manager import PairManager
from orchestrator.pair.session import PairSession


@pytest.fixture
def manager():
    db = AsyncMock()
    wt = AsyncMock()
    mgr = PairManager(db=db, wt=wt)

    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/repo"
    )
    session.add_member(100, "alice")
    session.add_member(200, "bob")

    mock_proc = MagicMock()
    mock_proc.send_message = AsyncMock(return_value="Done!")
    mock_proc.total_cost_usd = 0.01
    mock_proc.last_tool_events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/repo/app/api.py", "old_string": "x", "new_string": "y"}},
                ]
            },
        }
    ]

    mgr._sessions[1] = session
    mgr._processes[1] = mock_proc
    return mgr


@pytest.mark.asyncio
async def test_send_message_tracks_file_ownership(manager):
    response, diff = await manager.send_message_with_tracking(1, 100, "alice", "build the API")
    session = manager.get_session(1)
    assert session.file_ownership.get("app/api.py") == 100


@pytest.mark.asyncio
async def test_send_message_returns_diff_summary(manager):
    response, diff = await manager.send_message_with_tracking(1, 100, "alice", "build the API")
    assert "app/api.py" in diff
    assert "@alice" in diff


@pytest.mark.asyncio
async def test_send_message_warns_on_conflict(manager):
    session = manager.get_session(1)
    session.set_file_owner("app/api.py", 100)  # alice owns it

    # Bob's process will touch the same file
    response, diff = await manager.send_message_with_tracking(1, 200, "bob", "edit the API")
    # Should still work but diff should mention the conflict
    assert response == "Done!"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_manager.py -v`
Expected: FAIL — `send_message_with_tracking` not defined

- [ ] **Step 3: Implement send_message_with_tracking in PairManager**

Add to `orchestrator/pair/manager.py`:

```python
# Add import at top:
from orchestrator.pair.file_tracker import format_diff_summary, parse_tool_events
```

Add this new method after the existing `send_message` method (keep the old one for backwards compat):

```python
    async def send_message_with_tracking(
        self, chat_id: int, user_id: int, username: str, text: str
    ) -> tuple[str, str]:
        """Send message and return (response, diff_summary).

        Also updates file ownership based on what Claude edited.
        """
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if not session.can_send(user_id):
            driver = session.members.get(session.driver_id)
            driver_name = f"@{driver.username}" if driver else "the driver"
            return (
                f"Only {driver_name} can send messages in driver mode. Use /both to enable everyone.",
                "",
            )

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        attributed = f"[@{username}]: {text}"
        response = await proc.send_message(attributed)
        session.touch()
        session.total_cost_usd = proc.total_cost_usd

        # Parse file changes from tool events
        changes = parse_tool_events(proc.last_tool_events, session.worktree_path)

        # Update file ownership
        for change in changes:
            session.set_file_owner(change.filepath, user_id)

        # Format diff summary
        diff = format_diff_summary(changes, username)

        return response, diff
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_manager.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pair/manager.py tests/test_pair_manager.py
git commit -m "feat: add file tracking and diff summaries to PairManager"
```

---

### Task 6: Enhanced Context Handoff

**Files:**
- Modify: `orchestrator/pair/manager.py:131-145`

- [ ] **Step 1: Write failing test for context handoff**

Add to `tests/test_pair_manager.py`:

```python
@pytest.mark.asyncio
async def test_handoff_with_context(manager):
    proc = manager._processes[1]
    proc.send_message = AsyncMock(return_value="Context: Built login endpoint. Tests pass. TODO: add rate limiting.")

    session = manager.get_session(1)
    session.set_file_owner("app/api.py", 100)
    session.driver_id = 100
    session.mode = "driver"

    result = await manager.handoff_with_context(1, 100)
    assert "Context:" in result
    assert session.driver_id == 200  # handed off to bob
    assert len(session.handoff_history) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_manager.py::test_handoff_with_context -v`
Expected: FAIL — `handoff_with_context` not defined

- [ ] **Step 3: Implement handoff_with_context**

Add to `orchestrator/pair/manager.py`:

```python
    async def handoff_with_context(self, chat_id: int, from_user: int) -> str:
        """Hand off driver role with full context transfer."""
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if session.driver_id != from_user:
            raise ValueError("Only the current driver can handoff.")

        others = [uid for uid in session.members if uid != from_user]
        if not others:
            raise ValueError("No one to hand off to.")

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        from_member = session.members[from_user]
        to_user = others[0]
        to_member = session.members[to_user]

        # Ask Claude to generate a context summary
        context_prompt = (
            "Generate a brief handoff summary for the next developer. Include:\n"
            "1. What you've built so far\n"
            "2. What's working / tests passing\n"
            "3. What's left to do\n"
            "4. Any gotchas or things to watch out for\n"
            "Keep it concise — 5-8 lines max."
        )
        context_summary = await proc.send_message(context_prompt)

        # Record the handoff
        session.add_handoff(from_member.username, to_member.username, context_summary)

        # Swap driver
        session.set_driver(to_user)
        session.mode = "driver"

        # Notify Claude about the new driver
        intro = (
            f"[@{to_member.username}] is now the driver. "
            f"Here's the handoff from @{from_member.username}:\n{context_summary}\n"
            f"Files owned by @{from_member.username}: {', '.join(fp for fp, uid in session.file_ownership.items() if uid == from_user) or 'none'}"
        )
        await proc.send_message(intro)

        return context_summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_manager.py::test_handoff_with_context -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pair/manager.py tests/test_pair_manager.py
git commit -m "feat: add context-aware handoff with summary generation"
```

---

### Task 7: Auto-Commit on Issue Completion

**Files:**
- Modify: `orchestrator/pair/manager.py`

- [ ] **Step 1: Write failing test for auto-commit**

Add to `tests/test_pair_manager.py`:

```python
@pytest.mark.asyncio
async def test_complete_issue_auto_commits(manager):
    session = manager.get_session(1)
    session.assign_issue(12, 100)

    proc = manager._processes[1]
    proc.send_message = AsyncMock(return_value="Committed: feat: add login API (#12)")

    result = await manager.complete_issue(1, 12, 100)
    assert "Committed" in result or "#12" in result
    assert 12 not in session.active_issues


@pytest.mark.asyncio
async def test_complete_issue_wrong_user(manager):
    session = manager.get_session(1)
    session.assign_issue(12, 100)

    with pytest.raises(ValueError, match="not assigned to you"):
        await manager.complete_issue(1, 12, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_manager.py::test_complete_issue_auto_commits tests/test_pair_manager.py::test_complete_issue_wrong_user -v`
Expected: FAIL — `complete_issue` not defined

- [ ] **Step 3: Implement complete_issue with auto-commit**

Add to `orchestrator/pair/manager.py`:

```python
    async def pick_issue(
        self, chat_id: int, issue_number: int, user_id: int, username: str
    ) -> None:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        # Check if already picked by someone else
        existing = session.active_issues.get(issue_number)
        if existing is not None and existing != user_id:
            other = session.members.get(existing)
            other_name = f"@{other.username}" if other else "someone"
            raise ValueError(f"Issue #{issue_number} already claimed by {other_name}.")

        session.assign_issue(issue_number, user_id)

        # Tell Claude about the assignment
        proc = self._processes.get(chat_id)
        if proc:
            await proc.send_message(
                f"[@{username}] is now working on issue #{issue_number}. "
                "Focus their requests on this issue."
            )

    async def complete_issue(
        self, chat_id: int, issue_number: int, user_id: int
    ) -> str:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        assigned_to = session.active_issues.get(issue_number)
        if assigned_to is None:
            raise ValueError(f"Issue #{issue_number} is not active.")
        if assigned_to != user_id:
            raise ValueError(f"Issue #{issue_number} is not assigned to you.")

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        # Ask Claude to commit with issue reference
        commit_prompt = (
            f"Stage all changed files and commit with message: "
            f"'feat: complete issue #{issue_number} — {session.task_name}'. "
            "Do NOT push. Just commit locally."
        )
        result = await proc.send_message(commit_prompt)
        session.complete_issue(issue_number)
        session.touch()

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_manager.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pair/manager.py tests/test_pair_manager.py
git commit -m "feat: add issue picking and auto-commit on completion"
```

---

### Task 8: New Telegram Handlers

**Files:**
- Modify: `orchestrator/pair/handlers.py`

- [ ] **Step 1: Add `/issues` command handler**

Add to `orchestrator/pair/handlers.py`:

```python
# Add import at top:
from orchestrator.pair.issues import GitHubIssues
from orchestrator import config

# Add module-level variable:
_issues: GitHubIssues | None = None
```

Update `register_pair` to accept and store the issues instance:

```python
def register_pair(dp, pair_mgr: PairManager, bot: Bot, issues: GitHubIssues | None = None) -> None:
    global _pair_mgr, _bot_ref, _issues
    _pair_mgr = pair_mgr
    _bot_ref = bot
    _issues = issues or GitHubIssues(repo_root=str(config.REPO_ROOT))
    dp.include_router(pair_router)
```

Add the `/issues` handler:

```python
@pair_router.message(Command("issues"))
async def cmd_issues(msg: Message) -> None:
    assert _pair_mgr and _issues

    session = _pair_mgr.get_session(_chat_id(msg))
    picked = {}
    if session:
        picked = {
            num: session.members[uid].username
            for num, uid in session.active_issues.items()
            if uid in session.members
        }

    try:
        board = await _issues.format_board(picked=picked)
    except RuntimeError as e:
        await msg.reply(f"Failed to fetch issues: {e}")
        return

    for chunk in chunk_message(board):
        await msg.reply(chunk)
```

- [ ] **Step 2: Add `/pick` command handler**

```python
@pair_router.message(Command("pick"))
async def cmd_pick(msg: Message) -> None:
    assert _pair_mgr

    text = (msg.text or "").strip()
    # Parse issue number from "/pick #12" or "/pick 12"
    parts = text.split()
    if len(parts) < 2:
        await msg.reply("Usage: /pick #12 or /pick 12")
        return

    raw = parts[1].lstrip("#")
    try:
        issue_number = int(raw)
    except ValueError:
        await msg.reply(f"Invalid issue number: {parts[1]}")
        return

    try:
        await _pair_mgr.pick_issue(
            _chat_id(msg), issue_number, _user_id(msg), _username(msg)
        )
    except ValueError as e:
        await msg.reply(str(e))
        return

    await msg.reply(f"@{_username(msg)} picked issue #{issue_number}")
```

- [ ] **Step 3: Add `/done` command handler**

```python
@pair_router.message(Command("done"))
async def cmd_done(msg: Message) -> None:
    assert _pair_mgr

    session = _pair_mgr.get_session(_chat_id(msg))
    if not session:
        await msg.reply("No pair session active.")
        return

    uid = _user_id(msg)
    # Find the issue this user is working on
    user_issues = [num for num, assigned in session.active_issues.items() if assigned == uid]
    if not user_issues:
        await msg.reply("You don't have any active issues. Use /pick #N first.")
        return

    issue_number = user_issues[0]  # Complete the first one
    await msg.reply(f"Completing issue #{issue_number}...")

    try:
        result = await _pair_mgr.complete_issue(_chat_id(msg), issue_number, uid)
    except ValueError as e:
        await msg.reply(str(e))
        return

    for chunk in chunk_message(f"Issue #{issue_number} completed.\n{result}"):
        await msg.reply(chunk)
```

- [ ] **Step 4: Update `route_pair_message` to use tracking and post diffs**

Replace the existing `route_pair_message` handler:

```python
@pair_router.message(F.text & ~F.text.startswith("/"))
async def route_pair_message(msg: Message) -> None:
    assert _pair_mgr

    chat_id = _chat_id(msg)
    session = _pair_mgr.get_session(chat_id)
    if not session:
        return

    text = (msg.text or "").strip()
    if not text:
        return

    uid = _user_id(msg)
    if uid not in session.members:
        return

    try:
        response, diff = await _pair_mgr.send_message_with_tracking(
            chat_id, uid, _username(msg), text
        )
    except ValueError as e:
        await msg.reply(str(e))
        return

    if not response:
        await msg.reply("[No response from Claude]")
        return

    for chunk in chunk_message(f"[{session.task_name}]\n{response}"):
        await msg.reply(chunk)

    # Post diff summary if files changed
    if diff:
        await msg.reply(diff)
```

- [ ] **Step 5: Update `/handoff` to use context-aware handoff**

Replace the existing `cmd_handoff` handler:

```python
@pair_router.message(Command("handoff"))
async def cmd_handoff(msg: Message) -> None:
    assert _pair_mgr

    await msg.reply("Generating handoff context...")

    try:
        context = await _pair_mgr.handoff_with_context(_chat_id(msg), _user_id(msg))
    except ValueError as e:
        await msg.reply(str(e))
        return

    session = _pair_mgr.get_session(_chat_id(msg))
    driver = session.members.get(session.driver_id) if session else None
    name = f"@{driver.username}" if driver else "?"

    for chunk in chunk_message(f"Driver handed off to {name}.\n\nContext:\n{context}"):
        await msg.reply(chunk)
```

- [ ] **Step 6: Commit**

```bash
git add orchestrator/pair/handlers.py
git commit -m "feat: add /issues, /pick, /done commands and diff summaries in chat"
```

---

### Task 9: Wire Everything Together in main.py

**Files:**
- Modify: `orchestrator/main.py`

- [ ] **Step 1: Read current main.py**

Read the file first to understand current wiring.

- [ ] **Step 2: Update imports and initialization**

Add the `GitHubIssues` import and pass it to `register_pair`:

```python
from orchestrator.pair.issues import GitHubIssues
```

In the setup section where `register_pair` is called, add:

```python
issues = GitHubIssues(repo_root=str(config.REPO_ROOT))
register_pair(dp, pair_mgr, bot, issues=issues)
```

- [ ] **Step 3: Verify the bot starts without errors**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -c "from orchestrator.main import *; print('Import OK')"`
Expected: "Import OK" (no import errors)

- [ ] **Step 4: Commit**

```bash
git add orchestrator/main.py
git commit -m "feat: wire GitHub Issues into pair mode startup"
```

---

### Task 10: Integration Test — Full Pair Session Flow

**Files:**
- Create: `tests/test_pair_integration.py`

- [ ] **Step 1: Write integration test for full session flow**

```python
# tests/test_pair_integration.py
"""Integration test for full pair programming session flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.pair.manager import PairManager
from orchestrator.pair.session import PairSession


@pytest.fixture
def full_setup():
    db = AsyncMock()
    wt = AsyncMock()
    wt.create = AsyncMock(return_value="/tmp/test-wt")
    wt.push_branch = AsyncMock(return_value=(True, "pushed"))
    wt.create_pr = AsyncMock(return_value=(True, "https://github.com/test/pr/1"))
    wt.remove = AsyncMock()

    mgr = PairManager(db=db, wt=wt)
    return mgr


@pytest.mark.asyncio
async def test_full_pair_flow(full_setup):
    mgr = full_setup

    with patch("orchestrator.pair.manager.ClaudeProcess") as MockProc:
        mock_proc = MagicMock()
        mock_proc.send_message = AsyncMock(return_value="Built the API")
        mock_proc.total_cost_usd = 0.05
        mock_proc.last_tool_events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/test-wt/app/api.py", "content": "code"}},
                    ]
                },
            }
        ]
        mock_proc.kill = AsyncMock()
        MockProc.return_value = mock_proc

        # 1. Start pair session
        session = await mgr.start_pair(1, "login-feature", 100, "alice")
        assert session.task_name == "login-feature"

        # 2. Bob joins
        member = await mgr.join_pair(1, 200, "bob")
        assert member.username == "bob"

        # 3. Alice picks issue #12
        await mgr.pick_issue(1, 12, 100, "alice")
        assert session.active_issues[12] == 100

        # 4. Alice sends message — file ownership tracked
        response, diff = await mgr.send_message_with_tracking(1, 100, "alice", "build login")
        assert response == "Built the API"
        assert session.file_ownership.get("app/api.py") == 100
        assert "app/api.py" in diff

        # 5. Alice completes issue — auto-commits
        mock_proc.send_message = AsyncMock(return_value="Committed: feat: login (#12)")
        result = await mgr.complete_issue(1, 12, 100)
        assert 12 not in session.active_issues

        # 6. Alice hands off to Bob
        mock_proc.send_message = AsyncMock(return_value="Built login API. Tests pass.")
        context = await mgr.handoff_with_context(1, 100)
        assert session.driver_id == 200
        assert len(session.handoff_history) == 1

        # 7. End pair session
        result = await mgr.end_pair(1)
        assert "PR" in result
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/test_pair_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run all tests**

Run: `cd /Users/gauravsurtani/projects/japan_hackathon && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_pair_integration.py
git commit -m "test: add integration test for full pair programming flow"
```

---

## Summary

| Task | What it adds | Files |
|-|-|-|
| 1 | PairSession model extensions | `session.py`, `test_pair_session.py` |
| 2 | GitHub Issues via `gh` CLI | `issues.py`, `test_issues.py` |
| 3 | File change parser + diff formatter | `file_tracker.py`, `test_file_tracker.py` |
| 4 | Tool event capture in ClaudeProcess | `claude_process.py`, `test_claude_process.py` |
| 5 | File tracking in PairManager | `manager.py`, `test_pair_manager.py` |
| 6 | Context-aware handoff | `manager.py` |
| 7 | Auto-commit on issue completion | `manager.py` |
| 8 | `/issues`, `/pick`, `/done` handlers + diff summaries | `handlers.py` |
| 9 | Wire into main.py | `main.py` |
| 10 | Integration test for full flow | `test_pair_integration.py` |

**Total new files:** 5 (issues.py, file_tracker.py, + 4 test files)
**Modified files:** 4 (session.py, manager.py, claude_process.py, handlers.py, main.py)
**Estimated commits:** 10
