"""Integration test for full pair programming session flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.pair.manager import PairManager


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
