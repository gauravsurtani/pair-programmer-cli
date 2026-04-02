"""Tests for pair session persistence."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import aiosqlite

from orchestrator.pair.session import PairSession
from orchestrator.storage.db import (
    init_db,
    save_pair_session,
    load_pair_session,
    delete_pair_session,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    db = await init_db(db_path)
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_save_and_load_pair_session(db):
    session = PairSession(
        chat_id=42, task_name="test-task", branch="feat/test-task", worktree_path="/tmp/wt"
    )
    session.add_member(100, "alice")
    session.add_member(200, "bob")
    session.set_file_owner("app/api.py", 100)
    session.assign_issue(12, 100)
    session.add_handoff("alice", "bob", "Built the API")

    await save_pair_session(db, 42, session, claude_session_id="sess-abc-123")

    result = await load_pair_session(db, 42)
    assert result is not None
    loaded, claude_sid = result

    assert loaded.chat_id == 42
    assert loaded.task_name == "test-task"
    assert 100 in loaded.members
    assert loaded.members[100].username == "alice"
    assert loaded.file_ownership["app/api.py"] == 100
    assert loaded.active_issues[12] == 100
    assert len(loaded.handoff_history) == 1
    assert claude_sid == "sess-abc-123"


@pytest.mark.asyncio
async def test_delete_pair_session(db):
    session = PairSession(
        chat_id=42, task_name="test-task", branch="feat/test-task", worktree_path="/tmp/wt"
    )
    session.add_member(100, "alice")

    await save_pair_session(db, 42, session)
    await delete_pair_session(db, 42)

    result = await load_pair_session(db, 42)
    assert result is None


@pytest.mark.asyncio
async def test_load_nonexistent_pair_session(db):
    result = await load_pair_session(db, 999)
    assert result is None
