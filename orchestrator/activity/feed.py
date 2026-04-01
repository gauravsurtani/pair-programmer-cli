from __future__ import annotations

import logging

from aiogram import Bot

from orchestrator.models import Session

logger = logging.getLogger(__name__)

_PREFIXES = {
    "claim": ">>",
    "park": "||",
    "resume": ">>",
    "merge": "OK",
    "error": "!!",
    "sync": "<>",
    "kill": "XX",
    "idle": "ZZ",
}


async def broadcast(
    bot: Bot,
    chat_id: int,
    event: str,
    session: Session,
    detail: str = "",
) -> None:
    prefix = _PREFIXES.get(event, "--")
    parts = [f"[{prefix}]", f"@{session.username}", session.task_name]
    if detail:
        parts.append(detail)
    text = " | ".join(parts)

    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.error("Failed to broadcast: %s", e)
