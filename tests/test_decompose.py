"""Tests for task decomposition module."""

from orchestrator.planner.decompose import (
    Task,
    format_task_board,
    get_unblocked_tasks,
)


def test_format_task_board_empty():
    assert format_task_board([]) == "No tasks."


def test_format_task_board_with_tasks():
    tasks = [
        Task(id=1, title="Setup DB", description="Create schema", files=["db.py"]),
        Task(id=2, title="Build API", description="REST endpoints", files=["api.py"], blocked_by=[1]),
    ]
    board = format_task_board(tasks)
    assert "#1" in board
    assert "#2" in board
    assert "Setup DB" in board
    assert "blocked by #1" in board


def test_format_task_board_in_progress():
    tasks = [
        Task(id=1, title="Setup DB", description="x", status="in_progress", assigned_to="alice"),
    ]
    board = format_task_board(tasks)
    assert "@alice" in board
    assert "IN PROGRESS" in board


def test_format_task_board_done():
    tasks = [
        Task(id=1, title="Setup DB", description="x", status="done", assigned_to="alice"),
        Task(id=2, title="Build API", description="y", files=["api.py"], blocked_by=[1]),
    ]
    board = format_task_board(tasks)
    assert "DONE: 1/2" in board
    assert "ready" in board  # task 2 should be unblocked now


def test_get_unblocked_tasks():
    tasks = [
        Task(id=1, title="A", description="x", status="done"),
        Task(id=2, title="B", description="y", blocked_by=[1]),
        Task(id=3, title="C", description="z", blocked_by=[2]),
    ]
    unblocked = get_unblocked_tasks(tasks)
    assert len(unblocked) == 1
    assert unblocked[0].id == 2  # blocker #1 is done


def test_get_unblocked_no_blockers():
    tasks = [
        Task(id=1, title="A", description="x"),
        Task(id=2, title="B", description="y"),
    ]
    unblocked = get_unblocked_tasks(tasks)
    assert len(unblocked) == 2


def test_get_unblocked_all_blocked():
    tasks = [
        Task(id=1, title="A", description="x", blocked_by=[99]),
    ]
    unblocked = get_unblocked_tasks(tasks)
    assert len(unblocked) == 0
