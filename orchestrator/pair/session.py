"""Pair programming session — multiple users share one Claude session."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from orchestrator.sessions.claude_process import ClaudeProcess

logger = logging.getLogger(__name__)


class PairRole(str, Enum):
    DRIVER = "driver"
    NAVIGATOR = "navigator"


class PairMember(BaseModel):
    user_id: int
    username: str
    role: PairRole = PairRole.DRIVER


class PairSession(BaseModel):
    chat_id: int
    task_name: str
    branch: str
    worktree_path: str
    members: dict[int, PairMember] = Field(default_factory=dict)
    driver_id: int | None = None
    mode: str = "both"  # "both" = everyone can talk, "driver" = only driver
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_cost_usd: float = 0.0
    file_ownership: dict[str, int] = Field(default_factory=dict)
    active_issues: dict[int, int] = Field(default_factory=dict)
    handoff_history: list[dict] = Field(default_factory=list)

    def add_member(self, user_id: int, username: str) -> PairMember:
        member = PairMember(user_id=user_id, username=username)
        self.members[user_id] = member
        if len(self.members) == 1:
            self.driver_id = user_id
            member.role = PairRole.DRIVER
        return member

    def remove_member(self, user_id: int) -> None:
        self.members.pop(user_id, None)
        if self.driver_id == user_id:
            self.driver_id = next(iter(self.members), None)

    def set_driver(self, user_id: int) -> bool:
        if user_id not in self.members:
            return False
        for uid, m in self.members.items():
            m.role = PairRole.DRIVER if uid == user_id else PairRole.NAVIGATOR
        self.driver_id = user_id
        return True

    def can_send(self, user_id: int) -> bool:
        if user_id not in self.members:
            return False
        if self.mode == "both":
            return True
        return user_id == self.driver_id

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)

    def set_file_owner(self, filepath: str, user_id: int) -> None:
        self.file_ownership[filepath] = user_id

    def get_file_owner(self, filepath: str) -> int | None:
        return self.file_ownership.get(filepath)

    def check_conflicts(self, filepaths: list[str], user_id: int) -> list[tuple[str, int]]:
        conflicts = []
        for fp in filepaths:
            owner = self.file_ownership.get(fp)
            if owner is not None and owner != user_id:
                conflicts.append((fp, owner))
        return conflicts

    def assign_issue(self, issue_number: int, user_id: int) -> None:
        self.active_issues[issue_number] = user_id

    def complete_issue(self, issue_number: int) -> None:
        self.active_issues.pop(issue_number, None)

    def add_handoff(self, from_user: str, to_user: str, summary: str) -> None:
        self.handoff_history.append({
            "from_user": from_user,
            "to_user": to_user,
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def member_list_str(self) -> str:
        lines = []
        for m in self.members.values():
            tag = " (driver)" if m.user_id == self.driver_id and self.mode == "driver" else ""
            lines.append(f"@{m.username}{tag}")
        return ", ".join(lines)
