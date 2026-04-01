from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from orchestrator.activity.feed import broadcast
from orchestrator.bot.formatters import chunk_message, format_response, format_status
from orchestrator.models import SessionStatus
from orchestrator.sessions.manager import SessionManager

logger = logging.getLogger(__name__)
router = Router()

_session_mgr: SessionManager | None = None
_bot_ref: Bot | None = None


def register(dp: Dispatcher, session_mgr: SessionManager, bot: Bot) -> None:
    global _session_mgr, _bot_ref
    _session_mgr = session_mgr
    _bot_ref = bot
    dp.include_router(router)


def _chat_id(msg: Message) -> int:
    return msg.chat.id


def _user_id(msg: Message) -> int:
    return msg.from_user.id if msg.from_user else 0


def _username(msg: Message) -> str:
    if msg.from_user:
        return msg.from_user.username or msg.from_user.first_name or str(msg.from_user.id)
    return "unknown"


@router.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    await msg.reply(
        "Orchestrator ready.\n\n"
        "PAIR MODE (shared session):\n"
        "/pair <task> — start pair session\n"
        "/join — join active session\n"
        "/driver @user — set driver\n"
        "/both — let everyone talk\n"
        "/handoff — swap driver\n"
        "/checkpoint [msg] — commit\n"
        "/endpair — push + PR + cleanup\n\n"
        "SPLIT MODE (solo sessions):\n"
        "/claim <task> — start solo session\n"
        "/status — show all sessions\n"
        "/park — pause session\n"
        "/resume — restart session\n"
        "/merge — create PR and cleanup\n"
        "/sync — rebase on main\n"
        "/kill — force-stop session"
    )


@router.message(Command("claim"))
async def cmd_claim(msg: Message) -> None:
    assert _session_mgr and _bot_ref

    text = (msg.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await msg.reply("Usage: /claim <task-name>")
        return

    task_name = parts[1].strip().lower().replace(" ", "-")

    try:
        session = await _session_mgr.claim(_user_id(msg), _username(msg), task_name)
    except ValueError as e:
        await msg.reply(str(e))
        return
    except RuntimeError as e:
        await msg.reply(f"Git error: {e}")
        return

    await msg.reply(
        f"Session started: {session.task_name}\n"
        f"Branch: {session.branch}\n"
        "Send messages to interact with Claude."
    )
    await broadcast(_bot_ref, _chat_id(msg), "claim", session)


@router.message(Command("status"))
async def cmd_status(msg: Message) -> None:
    assert _session_mgr
    sessions = _session_mgr.get_all_sessions()
    await msg.reply(format_status(sessions))


@router.message(Command("park"))
async def cmd_park(msg: Message) -> None:
    assert _session_mgr and _bot_ref

    try:
        session = await _session_mgr.park(_user_id(msg))
    except ValueError as e:
        await msg.reply(str(e))
        return

    await msg.reply(f"Session parked: {session.task_name}. Use /resume to continue.")
    await broadcast(_bot_ref, _chat_id(msg), "park", session)


@router.message(Command("resume"))
async def cmd_resume(msg: Message) -> None:
    assert _session_mgr and _bot_ref

    try:
        session = await _session_mgr.resume(_user_id(msg))
    except ValueError as e:
        await msg.reply(str(e))
        return

    await msg.reply(f"Session resumed: {session.task_name}. Context preserved.")
    await broadcast(_bot_ref, _chat_id(msg), "resume", session)


@router.message(Command("merge"))
async def cmd_merge(msg: Message) -> None:
    assert _session_mgr and _bot_ref

    session = _session_mgr.get_session(_user_id(msg))
    if not session:
        await msg.reply("No session to merge.")
        return

    await msg.reply(f"Merging {session.task_name}...")

    try:
        result = await _session_mgr.merge(_user_id(msg))
    except ValueError as e:
        await msg.reply(str(e))
        return

    if result.pr_url:
        reply = f"PR created: {result.pr_url}"
    else:
        reply = f"Merge result: {result.message}"

    if result.conflict_files:
        reply += f"\nOverlapping files: {', '.join(result.conflict_files)}"

    await msg.reply(reply)
    await broadcast(_bot_ref, _chat_id(msg), "merge", session, result.pr_url or "")


@router.message(Command("sync"))
async def cmd_sync(msg: Message) -> None:
    assert _session_mgr and _bot_ref

    session = _session_mgr.get_session(_user_id(msg))
    if not session:
        await msg.reply("No session to sync.")
        return

    result = await _session_mgr.sync(_user_id(msg))
    await msg.reply(f"Sync result:\n{result}")
    await broadcast(_bot_ref, _chat_id(msg), "sync", session)


@router.message(Command("kill"))
async def cmd_kill(msg: Message) -> None:
    assert _session_mgr

    session = _session_mgr.get_session(_user_id(msg))
    if not session:
        await msg.reply("No session to kill.")
        return

    task = session.task_name
    await _session_mgr.kill_session(_user_id(msg))
    await msg.reply(f"Session killed: {task}. Worktree removed.")


@router.message(F.text & ~F.text.startswith("/"))
async def route_message(msg: Message) -> None:
    assert _session_mgr

    uid = _user_id(msg)
    session = _session_mgr.get_session(uid)
    if not session or session.status != SessionStatus.ACTIVE:
        return

    text = (msg.text or "").strip()
    if not text:
        return

    try:
        response = await _session_mgr.send_message(uid, text)
    except ValueError as e:
        await msg.reply(str(e))
        return

    if not response:
        await msg.reply("[No response from Claude]")
        return

    formatted = format_response(session.task_name, response)
    for chunk in chunk_message(formatted):
        await msg.reply(chunk)


