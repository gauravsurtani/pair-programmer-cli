"""Manages pair programming sessions — one shared Claude session per group."""

from __future__ import annotations

import logging

import aiosqlite

from orchestrator import config
from orchestrator.pair.file_tracker import format_diff_summary, parse_tool_events
from orchestrator.pair.session import PairMember, PairSession
from orchestrator.sessions.claude_process import ClaudeProcess
from orchestrator.worktrees.manager import WorktreeManager

logger = logging.getLogger(__name__)


class PairManager:
    def __init__(
        self,
        db: aiosqlite.Connection,
        worktree_mgr: WorktreeManager | None = None,
        *,
        wt: WorktreeManager | None = None,
    ):
        self.db = db
        self.wt = wt if wt is not None else worktree_mgr
        self._sessions: dict[int, PairSession] = {}  # chat_id -> PairSession
        self._processes: dict[int, ClaudeProcess] = {}  # chat_id -> ClaudeProcess

    def get_session(self, chat_id: int) -> PairSession | None:
        return self._sessions.get(chat_id)

    async def _save(self, chat_id: int) -> None:
        """Persist pair session to database."""
        session = self._sessions.get(chat_id)
        if not session:
            return
        proc = self._processes.get(chat_id)
        claude_sid = proc.session_id if proc else None
        from orchestrator.storage.db import save_pair_session
        await save_pair_session(self.db, chat_id, session, claude_sid)

    async def start_pair(
        self, chat_id: int, task_name: str, user_id: int, username: str
    ) -> PairSession:
        if chat_id in self._sessions:
            raise ValueError(
                f"Pair session already active: {self._sessions[chat_id].task_name}. "
                "Use /endpair first."
            )

        worktree_path = await self.wt.create(task_name)
        branch = f"feat/{task_name}"

        session = PairSession(
            chat_id=chat_id,
            task_name=task_name,
            branch=branch,
            worktree_path=worktree_path,
        )
        session.add_member(user_id, username)

        proc = ClaudeProcess(
            worktree_path=worktree_path,
            task_name=task_name,
            budget=config.SESSION_BUDGET_USD,
        )

        self._sessions[chat_id] = session
        self._processes[chat_id] = proc
        logger.info("Pair session started: %s by @%s", task_name, username)
        await self._save(chat_id)
        return session

    async def join_pair(
        self, chat_id: int, user_id: int, username: str
    ) -> PairMember:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active. Use /pair <task> to start one.")

        if user_id in session.members:
            raise ValueError("You're already in this pair session.")

        member = session.add_member(user_id, username)
        logger.info("@%s joined pair session %s", username, session.task_name)
        await self._save(chat_id)
        return member

    async def leave_pair(self, chat_id: int, user_id: int) -> str:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if user_id not in session.members:
            raise ValueError("You're not in this pair session.")

        username = session.members[user_id].username
        session.remove_member(user_id)

        if not session.members:
            await self.end_pair(chat_id)
            return f"@{username} left. Session ended (no members left)."

        await self._save(chat_id)
        return f"@{username} left the pair session."

    async def send_message(
        self, chat_id: int, user_id: int, username: str, text: str
    ) -> str:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if not session.can_send(user_id):
            driver = session.members.get(session.driver_id)
            driver_name = f"@{driver.username}" if driver else "the driver"
            return f"Only {driver_name} can send messages in driver mode. Use /both to enable everyone."

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        # Prefix message with username so Claude knows who's talking
        attributed = f"[@{username}]: {text}"

        response = await proc.send_message(attributed)
        session.touch()
        session.total_cost_usd = proc.total_cost_usd
        return response

    async def send_message_with_tracking(
        self, chat_id: int, user_id: int, username: str, text: str
    ) -> tuple[str, str]:
        """Send message and return (response, diff_summary).

        Also updates file ownership based on what Claude edited.
        """
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if not session.can_send(user_id):
            driver = session.members.get(session.driver_id)
            driver_name = f"@{driver.username}" if driver else "the driver"
            return (
                f"Only {driver_name} can send messages in driver mode. Use /both to enable everyone.",
                "",
            )

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        attributed = f"[@{username}]: {text}"
        response = await proc.send_message(attributed)
        session.touch()
        session.total_cost_usd = proc.total_cost_usd

        # Parse file changes from tool events
        changes = parse_tool_events(proc.last_tool_events, session.worktree_path)

        # Update file ownership
        for change in changes:
            session.set_file_owner(change.filepath, user_id)

        # Format diff summary
        diff = format_diff_summary(changes, username)

        await self._save(chat_id)
        return response, diff

    async def set_driver(self, chat_id: int, user_id: int) -> PairSession:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if not session.set_driver(user_id):
            raise ValueError("That user is not in the pair session.")

        session.mode = "driver"
        return session

    async def set_both_mode(self, chat_id: int) -> PairSession:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")
        session.mode = "both"
        return session

    async def handoff(self, chat_id: int, from_user: int) -> PairSession:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if session.driver_id != from_user:
            raise ValueError("Only the current driver can handoff.")

        others = [uid for uid in session.members if uid != from_user]
        if not others:
            raise ValueError("No one to hand off to.")

        session.set_driver(others[0])
        session.mode = "driver"
        return session

    async def handoff_with_context(self, chat_id: int, from_user: int) -> str:
        """Hand off driver role with full context transfer."""
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        if session.driver_id != from_user:
            raise ValueError("Only the current driver can handoff.")

        others = [uid for uid in session.members if uid != from_user]
        if not others:
            raise ValueError("No one to hand off to.")

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        from_member = session.members[from_user]
        to_user = others[0]
        to_member = session.members[to_user]

        # Ask Claude to generate a context summary
        context_prompt = (
            "Generate a brief handoff summary for the next developer. Include:\n"
            "1. What you've built so far\n"
            "2. What's working / tests passing\n"
            "3. What's left to do\n"
            "4. Any gotchas or things to watch out for\n"
            "Keep it concise — 5-8 lines max."
        )
        context_summary = await proc.send_message(context_prompt)

        # Record the handoff
        session.add_handoff(from_member.username, to_member.username, context_summary)

        # Swap driver
        session.set_driver(to_user)
        session.mode = "driver"

        # Notify Claude about the new driver
        intro = (
            f"[@{to_member.username}] is now the driver. "
            f"Here's the handoff from @{from_member.username}:\n{context_summary}\n"
            f"Files owned by @{from_member.username}: {', '.join(fp for fp, uid in session.file_ownership.items() if uid == from_user) or 'none'}"
        )
        await proc.send_message(intro)

        await self._save(chat_id)
        return context_summary

    async def checkpoint(self, chat_id: int, message: str = "") -> str:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        commit_msg = message or f"checkpoint: {session.task_name}"
        prompt = (
            f"Stage all changed files and commit with message: '{commit_msg}'. "
            "Do NOT push. Just commit locally."
        )
        response = await proc.send_message(prompt)
        session.touch()
        return response

    async def pick_issue(
        self, chat_id: int, issue_number: int, user_id: int, username: str
    ) -> None:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        existing = session.active_issues.get(issue_number)
        if existing is not None and existing != user_id:
            other = session.members.get(existing)
            other_name = f"@{other.username}" if other else "someone"
            raise ValueError(f"Issue #{issue_number} already claimed by {other_name}.")

        session.assign_issue(issue_number, user_id)

        proc = self._processes.get(chat_id)
        if proc:
            await proc.send_message(
                f"[@{username}] is now working on issue #{issue_number}. "
                "Focus their requests on this issue."
            )

        await self._save(chat_id)

    async def complete_issue(
        self, chat_id: int, issue_number: int, user_id: int
    ) -> str:
        session = self._sessions.get(chat_id)
        if not session:
            raise ValueError("No pair session active.")

        assigned_to = session.active_issues.get(issue_number)
        if assigned_to is None:
            raise ValueError(f"Issue #{issue_number} is not active.")
        if assigned_to != user_id:
            raise ValueError(f"Issue #{issue_number} is not assigned to you.")

        proc = self._processes.get(chat_id)
        if not proc:
            raise ValueError("Session has no process.")

        commit_prompt = (
            f"Stage all changed files and commit with message: "
            f"'feat: complete issue #{issue_number} — {session.task_name}'. "
            "Do NOT push. Just commit locally."
        )
        result = await proc.send_message(commit_prompt)
        session.complete_issue(issue_number)
        session.touch()
        await self._save(chat_id)

        return result

    async def end_pair(self, chat_id: int) -> str:
        session = self._sessions.pop(chat_id, None)
        if not session:
            raise ValueError("No pair session active.")

        proc = self._processes.pop(chat_id, None)
        if proc:
            await proc.kill()

        from orchestrator.storage.db import delete_pair_session
        await delete_pair_session(self.db, chat_id)

        ok, push_msg = await self.wt.push_branch(session.task_name)
        if not ok:
            return f"Session ended. Push failed: {push_msg}"

        pr_ok, pr_msg = await self.wt.create_pr(
            session.task_name,
            title=f"feat: {session.task_name}",
            body=f"Pair session by {session.member_list_str()}\nCost: ${session.total_cost_usd:.2f}",
        )

        await self.wt.remove(session.task_name)

        if pr_ok:
            return f"Session ended. PR: {pr_msg}"
        return f"Session ended. Branch pushed but PR failed: {pr_msg}"

    async def restore_pair_sessions(self) -> int:
        """Restore pair sessions from database after restart."""
        from orchestrator.storage.db import load_all_pair_sessions
        results = await load_all_pair_sessions(self.db)
        count = 0
        for session, claude_session_id in results:
            proc = ClaudeProcess(
                worktree_path=session.worktree_path,
                task_name=session.task_name,
                budget=config.SESSION_BUDGET_USD,
            )
            if claude_session_id:
                proc.session_id = claude_session_id
            self._sessions[session.chat_id] = session
            self._processes[session.chat_id] = proc
            count += 1
            logger.info("Restored pair session: %s", session.task_name)
        return count
