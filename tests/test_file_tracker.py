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
