from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from orchestrator.models import Session, SessionStatus

_SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


async def init_db(db_path: Path) -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(db_path))
    await db.executescript(_SCHEMA)
    await db.commit()
    return db


async def save_session(db: aiosqlite.Connection, s: Session) -> None:
    await db.execute(
        """INSERT OR REPLACE INTO sessions
           (user_id, username, task_name, branch, worktree_path, status,
            claude_session_id, created_at, last_activity,
            total_cost_usd, max_budget_usd, error_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            s.user_id,
            s.username,
            s.task_name,
            s.branch,
            s.worktree_path,
            s.status.value,
            s.claude_session_id,
            s.created_at.isoformat(),
            s.last_activity.isoformat(),
            s.total_cost_usd,
            s.max_budget_usd,
            s.error_count,
        ),
    )
    await db.commit()


async def load_session(db: aiosqlite.Connection, user_id: int) -> Session | None:
    async with db.execute(
        "SELECT * FROM sessions WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    return _row_to_session(row)


async def load_all_sessions(db: aiosqlite.Connection) -> list[Session]:
    async with db.execute("SELECT * FROM sessions") as cursor:
        rows = await cursor.fetchall()
    return [_row_to_session(r) for r in rows]


async def delete_session(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    await db.commit()


def _row_to_session(row: tuple) -> Session:
    return Session(
        user_id=row[0],
        username=row[1],
        task_name=row[2],
        branch=row[3],
        worktree_path=row[4],
        status=SessionStatus(row[5]),
        claude_session_id=row[6],
        created_at=datetime.fromisoformat(row[7]),
        last_activity=datetime.fromisoformat(row[8]),
        total_cost_usd=row[9],
        max_budget_usd=row[10],
        error_count=row[11],
    )
