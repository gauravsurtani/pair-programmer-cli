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
