from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from orchestrator import config
from orchestrator.models import MergeResult, Session, SessionStatus
from orchestrator.sessions.claude_process import ClaudeProcess, OutputCallback
from orchestrator.storage.db import (
    delete_session,
    load_all_sessions,
    load_session,
    save_session,
)
from orchestrator.worktrees.manager import WorktreeManager

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(
        self,
        db: aiosqlite.Connection,
        worktree_mgr: WorktreeManager,
        output_callback: OutputCallback | None = None,
    ):
        self.db = db
        self.wt = worktree_mgr
        self._output_callback = output_callback
        self._sessions: dict[int, Session] = {}
        self._processes: dict[int, ClaudeProcess] = {}

    async def restore_from_db(self) -> None:
        sessions = await load_all_sessions(self.db)
        for s in sessions:
            self._sessions[s.user_id] = s
            if s.status == SessionStatus.ACTIVE:
                s.status = SessionStatus.ERROR
                await save_session(self.db, s)
                logger.warning(
                    "Session %s was active but has no process — marked as error",
                    s.task_name,
                )

    async def claim(self, user_id: int, username: str, task_name: str) -> Session:
        if user_id in self._sessions and self._sessions[user_id].status in (
            SessionStatus.ACTIVE,
            SessionStatus.PARKED,
        ):
            raise ValueError(
                f"You already have a session: {self._sessions[user_id].task_name}. "
                "Use /park or /kill first."
            )

        existing_tasks = {s.task_name for s in self._sessions.values()}
        if task_name in existing_tasks:
            raise ValueError(f"Task '{task_name}' is already claimed.")

        active_count = sum(
            1 for s in self._sessions.values() if s.status == SessionStatus.ACTIVE
        )
        if active_count >= config.MAX_SESSIONS:
            raise ValueError(f"Max sessions ({config.MAX_SESSIONS}) reached.")

        worktree_path = await self.wt.create(task_name)

        session = Session(
            user_id=user_id,
            username=username,
            task_name=task_name,
            branch=f"feat/{task_name}",
            worktree_path=worktree_path,
            status=SessionStatus.ACTIVE,
            max_budget_usd=config.SESSION_BUDGET_USD,
        )

        proc = ClaudeProcess(
            worktree_path=worktree_path,
            task_name=task_name,
            budget=config.SESSION_BUDGET_USD,
            output_callback=self._output_callback,
        )
        self._sessions[user_id] = session
        self._processes[user_id] = proc
        await save_session(self.db, session)
        return session

    async def send_message(self, user_id: int, text: str) -> str:
        session = self._sessions.get(user_id)
        if not session or session.status != SessionStatus.ACTIVE:
            raise ValueError("No active session. Use /claim <task> to start.")

        proc = self._processes.get(user_id)
        if not proc:
            raise ValueError("Session has no process. Try /resume.")

        try:
            response = await proc.send_message(text)
        except Exception as e:
            session.error_count += 1
            if session.error_count >= config.MAX_CRASH_RETRIES:
                session.status = SessionStatus.ERROR
                await save_session(self.db, session)
                raise ValueError(f"Session crashed {session.error_count} times: {e}")
            logger.error("Claude process error (attempt %d): %s", session.error_count, e)
            response = f"[Error — retrying on next message: {e}]"

        session.touch()
        session.claude_session_id = proc.session_id
        session.total_cost_usd = proc.total_cost_usd
        await save_session(self.db, session)
        return response

    async def park(self, user_id: int) -> Session:
        session = self._sessions.get(user_id)
        if not session:
            raise ValueError("No session to park.")

        proc = self._processes.pop(user_id, None)
        if proc:
            session.claude_session_id = proc.session_id
            await proc.kill()

        session.status = SessionStatus.PARKED
        await save_session(self.db, session)
        return session

    async def resume(self, user_id: int) -> Session:
        session = self._sessions.get(user_id)
        if not session:
            raise ValueError("No session to resume.")
        if session.status == SessionStatus.ACTIVE and user_id in self._processes:
            raise ValueError("Session is already active.")

        proc = ClaudeProcess(
            worktree_path=session.worktree_path,
            task_name=session.task_name,
            budget=session.max_budget_usd,
            output_callback=self._output_callback,
        )
        proc.session_id = session.claude_session_id

        session.status = SessionStatus.ACTIVE
        session.error_count = 0
        self._processes[user_id] = proc
        await save_session(self.db, session)
        return session

    async def merge(self, user_id: int) -> MergeResult:
        session = self._sessions.get(user_id)
        if not session:
            raise ValueError("No session to merge.")

        proc = self._processes.pop(user_id, None)
        if proc:
            await proc.kill()

        session.status = SessionStatus.MERGING
        await save_session(self.db, session)

        other_tasks = [
            s.task_name
            for s in self._sessions.values()
            if s.task_name != session.task_name
            and s.status in (SessionStatus.ACTIVE, SessionStatus.PARKED)
        ]
        overlaps = await self.wt.detect_overlaps(session.task_name, other_tasks)

        ok, push_msg = await self.wt.push_branch(session.task_name)
        if not ok:
            session.status = SessionStatus.ERROR
            await save_session(self.db, session)
            return MergeResult(
                branch=session.branch,
                test_passed=False,
                message=f"Push failed: {push_msg}",
            )

        body = f"Automated PR from orchestrator.\nTask: {session.task_name}"
        if overlaps:
            body += "\n\nFile overlaps detected:\n"
            for other, files in overlaps.items():
                body += f"- {other}: {', '.join(files)}\n"

        pr_ok, pr_msg = await self.wt.create_pr(
            session.task_name,
            title=f"feat: {session.task_name}",
            body=body,
        )

        await self.wt.remove(session.task_name)
        session.status = SessionStatus.DONE
        await save_session(self.db, session)
        del self._sessions[user_id]
        await delete_session(self.db, user_id)

        return MergeResult(
            branch=session.branch,
            test_passed=True,
            conflict_files=[f for files in overlaps.values() for f in files],
            pr_url=pr_msg if pr_ok else None,
            message=pr_msg,
        )

    async def sync(self, user_id: int) -> str:
        session = self._sessions.get(user_id)
        if not session:
            raise ValueError("No session to sync.")
        return await self.wt.sync(session.task_name)

    async def kill_session(self, user_id: int) -> None:
        proc = self._processes.pop(user_id, None)
        if proc:
            await proc.kill()

        session = self._sessions.pop(user_id, None)
        if session:
            try:
                await self.wt.remove(session.task_name)
            except Exception:
                logger.warning("Failed to remove worktree for %s", session.task_name)
            await delete_session(self.db, user_id)

    def get_all_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def get_session(self, user_id: int) -> Session | None:
        return self._sessions.get(user_id)

    async def check_idle(self) -> list[Session]:
        now = datetime.now(timezone.utc)
        parked: list[Session] = []
        for uid, session in list(self._sessions.items()):
            if session.status != SessionStatus.ACTIVE:
                continue
            idle = (now - session.last_activity).total_seconds()
            if idle > config.IDLE_TIMEOUT_SECONDS:
                await self.park(uid)
                parked.append(session)
                logger.info("Auto-parked idle session: %s", session.task_name)
        return parked
