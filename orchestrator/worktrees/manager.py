from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def _run(
    *args: str, cwd: str | Path | None = None
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode().strip(), stderr.decode().strip()


class WorktreeManager:
    def __init__(self, repo_root: Path, worktree_base: Path, base_branch: str = "main"):
        self.repo_root = repo_root
        self.worktree_base = worktree_base
        self.base_branch = base_branch
        self.worktree_base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, task_name: str) -> Path:
        safe_name = task_name.replace("/", "-")
        return self.worktree_base / f"feat-{safe_name}"

    async def create(self, task_name: str) -> str:
        branch = f"feat/{task_name}"
        wt_path = self._path_for(task_name)

        rc, _, err = await _run(
            "git", "fetch", "origin", self.base_branch, cwd=self.repo_root
        )
        if rc != 0:
            raise RuntimeError(f"git fetch failed: {err}")

        rc, _, err = await _run(
            "git", "worktree", "add", str(wt_path), "-b", branch,
            f"origin/{self.base_branch}",
            cwd=self.repo_root,
        )
        if rc != 0:
            raise RuntimeError(f"git worktree add failed: {err}")

        logger.info("Created worktree %s on branch %s", wt_path, branch)
        return str(wt_path)

    async def remove(self, task_name: str) -> None:
        wt_path = self._path_for(task_name)
        branch = f"feat/{task_name}"

        await _run(
            "git", "worktree", "remove", str(wt_path), "--force",
            cwd=self.repo_root,
        )
        await _run("git", "branch", "-D", branch, cwd=self.repo_root)
        logger.info("Removed worktree %s and branch %s", wt_path, branch)

    async def sync(self, task_name: str) -> str:
        wt_path = self._path_for(task_name)

        rc, _, err = await _run(
            "git", "fetch", "origin", self.base_branch, cwd=wt_path
        )
        if rc != 0:
            return f"Fetch failed: {err}"

        rc, out, err = await _run(
            "git", "rebase", f"origin/{self.base_branch}", cwd=wt_path
        )
        if rc != 0:
            await _run("git", "rebase", "--abort", cwd=wt_path)
            return f"Rebase conflict — aborted. Resolve manually:\n{err}"

        return out or "Already up to date."

    async def push_branch(self, task_name: str) -> tuple[bool, str]:
        wt_path = self._path_for(task_name)
        branch = f"feat/{task_name}"

        rc, out, err = await _run(
            "git", "push", "-u", "origin", branch, cwd=wt_path
        )
        if rc != 0:
            return False, err
        return True, out

    async def get_changed_files(self, task_name: str) -> list[str]:
        wt_path = self._path_for(task_name)

        rc, out, _ = await _run(
            "git", "diff", "--name-only", f"origin/{self.base_branch}...HEAD",
            cwd=wt_path,
        )
        if rc != 0 or not out:
            return []
        return [f for f in out.split("\n") if f]

    async def detect_overlaps(
        self, task_name: str, other_tasks: list[str]
    ) -> dict[str, list[str]]:
        my_files = set(await self.get_changed_files(task_name))
        overlaps: dict[str, list[str]] = {}
        for other in other_tasks:
            if other == task_name:
                continue
            their_files = set(await self.get_changed_files(other))
            common = my_files & their_files
            if common:
                overlaps[other] = sorted(common)
        return overlaps

    async def create_pr(
        self, task_name: str, title: str, body: str
    ) -> tuple[bool, str]:
        wt_path = self._path_for(task_name)
        branch = f"feat/{task_name}"

        rc, out, err = await _run(
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--base", self.base_branch,
            "--head", branch,
            cwd=wt_path,
        )
        if rc != 0:
            return False, err
        return True, out.strip()
