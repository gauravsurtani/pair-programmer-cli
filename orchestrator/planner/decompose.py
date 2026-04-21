"""AI-powered task decomposition — breaks a product idea into parallelizable tasks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from orchestrator.sessions.claude_process import ClaudeProcess

logger = logging.getLogger(__name__)


@dataclass
class Task:
    id: int
    title: str
    description: str
    files: list[str] = field(default_factory=list)  # files this task will create/modify
    blocked_by: list[int] = field(default_factory=list)  # task IDs that must complete first
    assigned_to: str | None = None  # username
    status: str = "open"  # open, in_progress, done


DECOMPOSE_PROMPT = """\
You are a senior software architect. Decompose the following product idea into \
concrete, parallelizable development tasks.

PRODUCT IDEA:
{idea}

RULES:
1. Each task must list the specific files it will create or modify
2. Tasks must NOT share files — if two tasks need the same file, merge them or split the file
3. Identify dependencies: which tasks must complete before others can start
4. Keep tasks small (1-2 hours each, max 5 files per task)
5. Include setup/infrastructure tasks if needed
6. Order tasks so maximum parallelism is possible

Respond with ONLY valid JSON in this exact format, no other text:
{{
  "tasks": [
    {{
      "id": 1,
      "title": "Short task name",
      "description": "What to build and how",
      "files": ["path/to/file1.py", "path/to/file2.py"],
      "blocked_by": []
    }},
    {{
      "id": 2,
      "title": "Another task",
      "description": "Details",
      "files": ["path/to/other.py"],
      "blocked_by": [1]
    }}
  ]
}}
"""


async def decompose(proc: ClaudeProcess, idea: str) -> list[Task]:
    """Use Claude to decompose a product idea into tasks."""
    prompt = DECOMPOSE_PROMPT.format(idea=idea)
    raw = await proc.send_message(prompt)

    # Extract JSON from response (Claude may wrap in markdown code blocks)
    json_str = raw.strip()
    if json_str.startswith("```"):
        # Strip markdown code fences
        lines = json_str.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        json_str = "\n".join(lines)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.error("Failed to parse decomposition JSON: %s", raw[:200])
        raise ValueError(
            "Claude returned invalid JSON for task decomposition. "
            "Try rephrasing your product idea."
        )

    tasks = []
    for t in data.get("tasks", []):
        tasks.append(Task(
            id=t["id"],
            title=t["title"],
            description=t["description"],
            files=t.get("files", []),
            blocked_by=t.get("blocked_by", []),
        ))

    # Validate no file overlaps
    all_files: dict[str, int] = {}
    warnings = []
    for task in tasks:
        for f in task.files:
            if f in all_files:
                warnings.append(f"File {f} claimed by task #{all_files[f]} and #{task.id}")
            all_files[f] = task.id

    if warnings:
        logger.warning("File overlap warnings: %s", warnings)

    return tasks


def format_task_board(tasks: list[Task]) -> str:
    """Format tasks as a readable board for Telegram."""
    if not tasks:
        return "No tasks."

    lines = ["TASK BOARD", ""]

    # Group by status
    open_tasks = [t for t in tasks if t.status == "open"]
    in_progress = [t for t in tasks if t.status == "in_progress"]
    done = [t for t in tasks if t.status == "done"]

    if in_progress:
        lines.append("IN PROGRESS:")
        for t in in_progress:
            lines.append(f"  #{t.id} {t.title} — @{t.assigned_to}")

    if open_tasks:
        lines.append("\nOPEN:")
        for t in open_tasks:
            blocked = ""
            if t.blocked_by:
                # Check if blockers are done
                done_ids = {d.id for d in done}
                pending_blockers = [b for b in t.blocked_by if b not in done_ids]
                if pending_blockers:
                    blocked = f" [blocked by #{', #'.join(str(b) for b in pending_blockers)}]"
                else:
                    blocked = " [ready]"
            else:
                blocked = " [ready]"
            lines.append(f"  #{t.id} {t.title}{blocked}")
            if t.files:
                lines.append(f"      files: {', '.join(t.files[:3])}")

    if done:
        lines.append(f"\nDONE: {len(done)}/{len(tasks)} tasks")
        for t in done:
            lines.append(f"  #{t.id} {t.title} — @{t.assigned_to}")

    return "\n".join(lines)


def get_unblocked_tasks(tasks: list[Task]) -> list[Task]:
    """Return tasks that are open and have no pending blockers."""
    done_ids = {t.id for t in tasks if t.status == "done"}
    unblocked = []
    for t in tasks:
        if t.status != "open":
            continue
        pending_blockers = [b for b in t.blocked_by if b not in done_ids]
        if not pending_blockers:
            unblocked.append(t)
    return unblocked
