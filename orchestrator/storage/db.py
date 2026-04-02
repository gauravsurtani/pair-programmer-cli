from __future__ import annotations

import json
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


async def save_pair_session(db: aiosqlite.Connection, chat_id: int, session, claude_session_id: str | None = None) -> None:
    """Save a PairSession to the database."""
    members_json = json.dumps({
        str(uid): {"user_id": m.user_id, "username": m.username, "role": m.role.value}
        for uid, m in session.members.items()
    })
    await db.execute(
        """INSERT OR REPLACE INTO pair_sessions
           (chat_id, task_name, branch, worktree_path, driver_id, mode,
            created_at, last_activity, total_cost_usd, claude_session_id,
            members_json, file_ownership_json, active_issues_json, handoff_history_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            chat_id,
            session.task_name,
            session.branch,
            session.worktree_path,
            session.driver_id,
            session.mode,
            session.created_at.isoformat(),
            session.last_activity.isoformat(),
            session.total_cost_usd,
            claude_session_id,
            members_json,
            json.dumps({k: v for k, v in session.file_ownership.items()}),
            json.dumps({str(k): v for k, v in session.active_issues.items()}),
            json.dumps(session.handoff_history),
        ),
    )
    await db.commit()


async def load_pair_session(db: aiosqlite.Connection, chat_id: int):
    """Load a PairSession from the database. Returns (PairSession, claude_session_id) or None."""
    from orchestrator.pair.session import PairMember, PairRole, PairSession

    async with db.execute(
        "SELECT * FROM pair_sessions WHERE chat_id = ?", (chat_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None

    session = PairSession(
        chat_id=row[0],
        task_name=row[1],
        branch=row[2],
        worktree_path=row[3],
        driver_id=row[4],
        mode=row[5],
        created_at=datetime.fromisoformat(row[6]),
        last_activity=datetime.fromisoformat(row[7]),
        total_cost_usd=row[8],
    )
    claude_session_id = row[9]

    # Restore members
    members_data = json.loads(row[10])
    for uid_str, mdata in members_data.items():
        member = PairMember(
            user_id=mdata["user_id"],
            username=mdata["username"],
            role=PairRole(mdata["role"]),
        )
        session.members[int(uid_str)] = member

    # Restore file ownership
    session.file_ownership = json.loads(row[11])

    # Restore active issues (keys are ints)
    raw_issues = json.loads(row[12])
    session.active_issues = {int(k): v for k, v in raw_issues.items()}

    # Restore handoff history
    session.handoff_history = json.loads(row[13])

    return session, claude_session_id


async def load_all_pair_sessions(db: aiosqlite.Connection):
    """Load all pair sessions from the database."""
    async with db.execute("SELECT * FROM pair_sessions") as cursor:
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        result = await load_pair_session(db, row[0])
        if result:
            results.append(result)
    return results


async def delete_pair_session(db: aiosqlite.Connection, chat_id: int) -> None:
    await db.execute("DELETE FROM pair_sessions WHERE chat_id = ?", (chat_id,))
    await db.commit()
