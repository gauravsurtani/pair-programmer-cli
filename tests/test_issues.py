"""Tests for GitHub Issues integration. These tests mock the gh CLI subprocess calls."""

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
