from __future__ import annotations

from orchestrator.models import Session, SessionStatus

MAX_TG_LENGTH = 4096
CHUNK_SIZE = 4000

_STATUS_ICON = {
    SessionStatus.ACTIVE: "ON",
    SessionStatus.PARKED: "||",
    SessionStatus.MERGING: "..",
    SessionStatus.DONE: "OK",
    SessionStatus.ERROR: "!!",
}


def format_status(sessions: list[Session]) -> str:
    if not sessions:
        return "No active sessions."

    lines = ["Task | User | Status | Cost"]
    lines.append("-|-|-|-")
    for s in sessions:
        icon = _STATUS_ICON.get(s.status, "??")
        lines.append(
            f"{s.task_name} | @{s.username} | {icon} | ${s.total_cost_usd:.2f}"
        )
    return "\n".join(lines)


def format_response(task_name: str, text: str) -> str:
    return f"[feat/{task_name}]\n{text}"


def chunk_message(text: str) -> list[str]:
    if len(text) <= MAX_TG_LENGTH:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:CHUNK_SIZE])
        text = text[CHUNK_SIZE:]
    return chunks
