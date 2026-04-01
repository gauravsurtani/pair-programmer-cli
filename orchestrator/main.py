from __future__ import annotations

import asyncio
import logging
import signal
import sys

from aiogram import Bot, Dispatcher

from orchestrator import config
from orchestrator.bot.handlers import register
from orchestrator.pair.handlers import register_pair
from orchestrator.pair.issues import GitHubIssues
from orchestrator.pair.manager import PairManager
from orchestrator.sessions.manager import SessionManager
from orchestrator.storage.db import init_db
from orchestrator.worktrees.manager import WorktreeManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def idle_checker(mgr: SessionManager, bot: Bot, chat_id: int | None) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            parked = await mgr.check_idle()
            if parked and bot and chat_id:
                from orchestrator.activity.feed import broadcast

                for s in parked:
                    await broadcast(bot, chat_id, "idle", s, "auto-parked (idle)")
        except Exception as e:
            logger.error("Idle checker error: %s", e)


async def main() -> None:
    if not config.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Export it or add to .env")
        sys.exit(1)

    config.WORKTREE_BASE.mkdir(parents=True, exist_ok=True)

    db = await init_db(config.DB_PATH)
    wt_mgr = WorktreeManager(
        repo_root=config.REPO_ROOT,
        worktree_base=config.WORKTREE_BASE,
        base_branch=config.DEFAULT_BASE_BRANCH,
    )

    bot = Bot(token=config.TELEGRAM_TOKEN)
    dp = Dispatcher()

    session_mgr = SessionManager(db=db, worktree_mgr=wt_mgr)
    await session_mgr.restore_from_db()

    pair_mgr = PairManager(db=db, worktree_mgr=wt_mgr)

    # Pair mode handlers registered FIRST — they take priority for message routing.
    # If no pair session is active, messages fall through to split mode.
    issues = GitHubIssues(repo_root=str(config.REPO_ROOT))
    register_pair(dp, pair_mgr, bot, issues=issues)
    register(dp, session_mgr, bot)

    idle_task = asyncio.create_task(idle_checker(session_mgr, bot, chat_id=None))

    async def shutdown(*_: object) -> None:
        logger.info("Shutting down — parking all active sessions...")
        for s in session_mgr.get_all_sessions():
            if s.status.value == "active":
                try:
                    await session_mgr.park(s.user_id)
                except Exception:
                    pass
        idle_task.cancel()
        await db.close()
        logger.info("Shutdown complete.")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    logger.info("Orchestrator starting — polling Telegram...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
