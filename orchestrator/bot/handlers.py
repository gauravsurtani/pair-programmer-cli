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
        "Hey! I'm your pair programming bot. "
        "I let you and a teammate share one AI coding session — no git headaches.\n\n"
        "Quick start: /pair my-feature\n"
        "Full guide: /help"
    )


@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.reply(
        "PAIR PROGRAMMER — share AI coding sessions\n\n"
        "GUIDES\n"
        "  /help-pair — pair mode commands\n"
        "  /help-split — solo mode commands\n"
        "  /help-flow — walkthrough of a typical session\n"
        "  /help-tips — pro tips\n\n"
        "QUICK START\n"
        "  1. /pair my-feature — start a session\n"
        "  2. Teammate sends /join\n"
        "  3. Both of you type messages — AI sees who said what\n"
        "  4. /issues to see tasks, /pick #N to claim one\n"
        "  5. /done when finished, /endpair to wrap up\n\n"
        "That's it. No git branches, no merge conflicts, no setup."
    )


@router.message(Command("help-pair"))
async def cmd_help_pair(msg: Message) -> None:
    await msg.reply(
        "PAIR MODE — shared AI session\n\n"
        "Start a session:\n"
        "  /pair my-feature\n\n"
        "Your teammate joins:\n"
        "  /join\n\n"
        "Now both of you just type messages — the AI sees who said what.\n\n"
        "Pick issues to work on:\n"
        "  /issues — see open GitHub issues\n"
        "  /pick #12 — claim an issue\n"
        "  /done — auto-commit and close your issue\n\n"
        "Hand off context:\n"
        "  /handoff — AI summarizes your work, passes it to your teammate\n\n"
        "Control who talks:\n"
        "  /driver @user — only that person can talk to AI\n"
        "  /both — everyone can talk (default)\n\n"
        "Save progress:\n"
        "  /checkpoint [msg] — commit without ending\n"
        "  /endpair — push, create PR, cleanup\n\n"
        "Leave anytime:\n"
        "  /leave — exit without ending the session"
    )


@router.message(Command("help-split"))
async def cmd_help_split(msg: Message) -> None:
    await msg.reply(
        "SPLIT MODE — solo sessions\n\n"
        "Each person gets their own AI session on their own branch.\n\n"
        "  /claim my-task — start a solo session\n"
        "  /status — see all active sessions\n"
        "  /park — pause (saves context)\n"
        "  /resume — pick up where you left off\n"
        "  /sync — rebase on main\n"
        "  /merge — push + create PR + cleanup\n"
        "  /kill — force-stop and remove"
    )


@router.message(Command("help-flow"))
async def cmd_help_flow(msg: Message) -> None:
    await msg.reply(
        "TYPICAL SESSION FLOW\n\n"
        "1. You: /pair auth-system\n"
        "2. Teammate: /join\n"
        "3. You: /issues\n"
        "   Bot shows open GitHub issues\n"
        "4. You: /pick #12\n"
        "   Teammate: /pick #15\n"
        "5. You type: \"build the login API\"\n"
        "   AI builds it. Bot posts what files changed.\n"
        "6. You: /done\n"
        "   AI auto-commits with issue reference.\n"
        "7. You: /handoff\n"
        "   AI summarizes your work for teammate.\n"
        "8. When done: /endpair\n"
        "   Pushes branch, creates PR, cleans up."
    )


@router.message(Command("help-tips"))
async def cmd_help_tips(msg: Message) -> None:
    await msg.reply(
        "TIPS\n\n"
        "Works solo — /pair works with just 1 person. "
        "Teammate can /join later anytime.\n\n"
        "File ownership — the bot tracks who's editing what. "
        "If you touch a file your teammate owns, it warns you.\n\n"
        "Diff summaries — after every AI change, the bot posts "
        "which files changed so everyone stays in sync.\n\n"
        "Context is preserved — /handoff doesn't just swap who types. "
        "The AI generates a full summary of what was done, "
        "what worked, and what's left.\n\n"
        "No git commands needed — the bot handles branches, "
        "commits, pushes, and PRs for you."
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


