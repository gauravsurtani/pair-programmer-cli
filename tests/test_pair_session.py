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
    conflicts = session.check_conflicts(["app/api.py"], 100)
    assert conflicts == []


def test_check_file_conflict_detected():
    session = PairSession(
        chat_id=1, task_name="test", branch="feat/test", worktree_path="/tmp/test"
    )
    session.add_member(100, "alice")
    session.add_member(200, "bob")
    session.set_file_owner("app/api.py", 100)
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
