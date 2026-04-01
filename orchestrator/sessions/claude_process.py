from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from orchestrator import config

logger = logging.getLogger(__name__)

OutputCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


class ClaudeProcess:
    """Wraps a Claude Code CLI subprocess.

    Uses text-input with ``--resume`` for multi-turn statefulness.
    Each ``send_message`` spawns a fresh ``claude --print --resume <id>``
    call because the bidirectional stream-json interface is unreliable.
    """

    def __init__(
        self,
        worktree_path: str,
        task_name: str,
        budget: float = config.SESSION_BUDGET_USD,
        output_callback: OutputCallback | None = None,
    ):
        self.worktree_path = worktree_path
        self.task_name = task_name
        self.budget = budget
        self.session_id: str | None = None
        self.total_cost_usd: float = 0.0
        self._output_callback = output_callback
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self.last_tool_events: list[dict] = []

    async def send_message(self, text: str) -> str:
        """Send a message and return the assistant's text response."""
        async with self._lock:
            return await self._invoke(text)

    async def _invoke(self, prompt: str) -> str:
        cmd = [
            config.CLAUDE_BIN,
            "--print",
            "--output-format", "stream-json",
            "--permission-mode", "bypassPermissions",
            "--max-budget-usd", str(self.budget),
        ]

        if self.session_id:
            cmd.extend(["--resume", self.session_id])
        else:
            system_extra = (
                f"You are working on task: {self.task_name}. "
                f"Branch: feat/{self.task_name}. "
                "Keep changes focused on this task only."
            )
            cmd.extend(["--append-system-prompt", system_extra])

        cmd.append(prompt)

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.worktree_path,
        )

        assistant_text = await self._read_response()

        await self._proc.wait()
        self._proc = None

        if self._output_callback and assistant_text:
            await self._output_callback(assistant_text, {"task": self.task_name})

        return assistant_text

    async def _read_response(self) -> str:
        assert self._proc and self._proc.stdout
        parts: list[str] = []
        self.last_tool_events = []  # Reset for this invocation

        async for raw_line in self._proc.stdout:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")
            subtype = event.get("subtype", "")

            if etype == "system" and subtype == "init":
                sid = event.get("session_id")
                if sid:
                    self.session_id = sid
                    logger.info("Session ID: %s", sid[:16])

            elif etype == "assistant":
                content = event.get("message", {}).get("content", [])
                has_tool_use = False
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            parts.append(text)
                    elif block.get("type") == "tool_use":
                        has_tool_use = True
                if has_tool_use:
                    self.last_tool_events.append(event)

            elif etype == "result":
                cost = event.get("total_cost_usd", 0)
                if cost:
                    self.total_cost_usd = cost

        return "\n".join(parts) if parts else ""

    @property
    def pid(self) -> int | None:
        if self._proc and self._proc.returncode is None:
            return self._proc.pid
        return None

    async def kill(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
