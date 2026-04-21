"""Tests for task board database persistence."""

import pytest
import pytest_asyncio
import aiosqlite

from orchestrator.planner.decompose import Task
from orchestrator.storage.db import (
    init_db,
    save_task_board,
    load_task_board,
    update_task_status,
    delete_task_board,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    db = await init_db(db_path)
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_save_and_load_task_board(db):
    tasks = [
        Task(id=1, title="Setup DB", description="Create schema", files=["db.py"]),
        Task(id=2, title="Build API", description="REST", files=["api.py"], blocked_by=[1]),
    ]
    await save_task_board(db, chat_id=42, tasks=tasks)

    loaded = await load_task_board(db, chat_id=42)
    assert len(loaded) == 2
    assert loaded[0].title == "Setup DB"
    assert loaded[0].files == ["db.py"]
    assert loaded[1].blocked_by == [1]


@pytest.mark.asyncio
async def test_update_task_status(db):
    tasks = [Task(id=1, title="Setup", description="x")]
    await save_task_board(db, chat_id=42, tasks=tasks)

    await update_task_status(db, chat_id=42, task_id=1, status="in_progress", assigned_to="alice")

    loaded = await load_task_board(db, chat_id=42)
    assert loaded[0].status == "in_progress"
    assert loaded[0].assigned_to == "alice"


@pytest.mark.asyncio
async def test_delete_task_board(db):
    tasks = [Task(id=1, title="Setup", description="x")]
    await save_task_board(db, chat_id=42, tasks=tasks)
    await delete_task_board(db, chat_id=42)

    loaded = await load_task_board(db, chat_id=42)
    assert loaded == []


@pytest.mark.asyncio
async def test_load_empty_board(db):
    loaded = await load_task_board(db, chat_id=999)
    assert loaded == []


@pytest.mark.asyncio
async def test_save_replaces_existing(db):
    tasks_v1 = [Task(id=1, title="Old", description="x")]
    await save_task_board(db, chat_id=42, tasks=tasks_v1)

    tasks_v2 = [Task(id=1, title="New", description="y"), Task(id=2, title="Extra", description="z")]
    await save_task_board(db, chat_id=42, tasks=tasks_v2)

    loaded = await load_task_board(db, chat_id=42)
    assert len(loaded) == 2
    assert loaded[0].title == "New"
