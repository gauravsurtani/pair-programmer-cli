from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PARKED = "parked"
    MERGING = "merging"
    DONE = "done"
    ERROR = "error"


class Session(BaseModel):
    user_id: int
    username: str
    task_name: str
    branch: str
    worktree_path: str
    status: SessionStatus = SessionStatus.ACTIVE
    claude_session_id: str | None = None
    pid: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_cost_usd: float = 0.0
    max_budget_usd: float = 5.0
    error_count: int = 0

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)


class MergeResult(BaseModel):
    branch: str
    test_passed: bool
    conflict_files: list[str] = Field(default_factory=list)
    pr_url: str | None = None
    message: str = ""
