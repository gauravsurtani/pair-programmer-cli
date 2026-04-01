import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _git_root() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


REPO_ROOT = Path(os.getenv("REPO_ROOT", _git_root()))
WORKTREE_BASE = Path(os.getenv("WORKTREE_BASE", "/tmp/orchestrator"))
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DB_PATH = Path(os.getenv("DB_PATH", str(REPO_ROOT / "orchestrator" / "state.db")))
DEFAULT_BASE_BRANCH = os.getenv("DEFAULT_BASE_BRANCH", "main")
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "5"))
SESSION_BUDGET_USD = float(os.getenv("SESSION_BUDGET_USD", "5.0"))
IDLE_TIMEOUT_SECONDS = int(os.getenv("IDLE_TIMEOUT_SECONDS", "600"))
MAX_CRASH_RETRIES = int(os.getenv("MAX_CRASH_RETRIES", "3"))
ALLOWED_CHAT_IDS: set[int] = set()

_raw = os.getenv("ALLOWED_CHAT_IDS", "")
if _raw:
    ALLOWED_CHAT_IDS = {int(x.strip()) for x in _raw.split(",") if x.strip()}
