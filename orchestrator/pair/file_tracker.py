"""Parse Claude stream-json events for file changes and format diff summaries."""

from __future__ import annotations

from dataclasses import dataclass, field

_WRITE_TOOLS = {"Write", "write"}
_EDIT_TOOLS = {"Edit", "edit"}


@dataclass
class FileChange:
    filepath: str
    action: str  # "edit" or "create"
    edit_count: int = 1


def parse_tool_events(
    events: list[dict], worktree_path: str
) -> list[FileChange]:
    seen: dict[str, FileChange] = {}

    for event in events:
        if event.get("type") != "assistant":
            continue
        content = event.get("message", {}).get("content", [])
        for block in content:
            if block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            filepath = tool_input.get("file_path", "")
            if not filepath:
                continue

            if filepath.startswith(worktree_path):
                filepath = filepath[len(worktree_path):].lstrip("/")

            if tool_name in _EDIT_TOOLS:
                if filepath in seen:
                    seen[filepath].edit_count += 1
                else:
                    seen[filepath] = FileChange(filepath=filepath, action="edit")
            elif tool_name in _WRITE_TOOLS:
                if filepath not in seen:
                    seen[filepath] = FileChange(filepath=filepath, action="create")

    return list(seen.values())


def format_diff_summary(changes: list[FileChange], username: str) -> str:
    if not changes:
        return ""

    file_count = len(changes)
    lines = [f"[@{username}] requested -> {file_count} files changed:"]
    for c in changes:
        action_label = "new" if c.action == "create" else f"{c.edit_count} edits"
        lines.append(f"  {c.filepath}  ({action_label})")
    return "\n".join(lines)
