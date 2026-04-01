"""Tests for ClaudeProcess tool event capture."""

from orchestrator.sessions.claude_process import ClaudeProcess


def test_tool_events_collected():
    """Verify that last_tool_events is initialized as empty list."""
    proc = ClaudeProcess(worktree_path="/tmp/test", task_name="test")
    assert proc.last_tool_events == []
