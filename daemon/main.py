#!/usr/bin/env python3
"""Main entry point for the website blocker daemon."""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import List

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api import app, set_session_factory
from config import get_config, get_config_path
from database import init_database, create_session_factory, Block
from heartbeat_tracker import get_heartbeat_tracker
from hyprland_monitor import init_hyprland_monitor, get_hyprland_monitor
from lock_manager import init_lock_manager, get_lock_manager
from scheduler import init_scheduler, get_scheduler

# Set up logging
def setup_logging():
    """Configure logging for the daemon."""
    config = get_config()
    log_level = getattr(logging, config.daemon.log_level.upper(), logging.INFO)

    # Create log directory
    log_dir = os.path.expanduser("~/.config/website-blocker")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "daemon.log")

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger(__name__)


logger = setup_logging()

# Global state
_scheduler: AsyncIOScheduler = None
_session_factory = None
_shutdown_event = asyncio.Event()
_is_locked_cache: bool = False  # Cached lock state for signal handler


async def get_all_blocks() -> List[Block]:
    """Get all blocks from the database."""
    async with _session_factory() as session:
        result = await session.execute(select(Block))
        return list(result.scalars().all())


async def schedule_check_job():
    """Job that runs periodically to check schedules."""
    global _is_locked_cache
    try:
        scheduler = get_scheduler()
        if scheduler:
            await scheduler.check_schedules()

        lock_manager = get_lock_manager()
        if lock_manager:
            await lock_manager.check_transitions()
            # Update cached lock state for signal handler
            _is_locked_cache = await lock_manager.is_locked()

    except Exception as e:
        logger.error(f"Error in schedule check job: {e}")


async def monitor_check_job():
    """Job that runs periodically to check windows and browsers."""
    try:
        monitor = get_hyprland_monitor()
        if monitor:
            result = await monitor.run_check()
            if result["apps_closed"] > 0 or result["browsers_closed"] > 0:
                logger.info(
                    f"Monitor check: closed {result['apps_closed']} apps, "
                    f"{result['browsers_closed']} browsers"
                )
    except Exception as e:
        logger.error(f"Error in monitor check job: {e}")


def handle_signal(signum, frame):
    """Handle termination signals."""
    global _is_locked_cache

    # Use cached lock state to avoid async issues in signal handler
    if _is_locked_cache:
        logger.warning("Ignoring stop signal during lock period")
        try:
            import subprocess
            subprocess.run(
                ["notify-send", "Website Blocker", "Cannot stop daemon during locked period"],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass
        return  # Refuse to stop

    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown_event.set()


@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for FastAPI."""
    global _scheduler, _session_factory

    logger.info("Starting Website Blocker Daemon")
    config = get_config()
    logger.info(f"Configuration loaded from {get_config_path()}")

    # Initialize database
    engine = await init_database()
    _session_factory = create_session_factory(engine)
    set_session_factory(_session_factory)
    logger.info("Database initialized")

    # Initialize components
    init_scheduler(_session_factory)
    init_lock_manager(get_all_blocks)
    init_hyprland_monitor(_session_factory)
    logger.info("Components initialized")

    # Set up APScheduler
    _scheduler = AsyncIOScheduler()

    # Schedule check job (every 10 seconds)
    _scheduler.add_job(
        schedule_check_job,
        'interval',
        seconds=config.monitoring.schedule_check_interval_seconds,
        id='schedule_check'
    )

    # Monitor check job (every 5 seconds)
    _scheduler.add_job(
        monitor_check_job,
        'interval',
        seconds=config.monitoring.check_interval_seconds,
        id='monitor_check'
    )

    _scheduler.start()
    logger.info("Scheduler started")

    # Run initial checks
    await schedule_check_job()
    await monitor_check_job()

    yield

    # Shutdown
    logger.info("Shutting down daemon")
    if _scheduler:
        _scheduler.shutdown()
    await engine.dispose()


# Set the lifespan on the app
app.router.lifespan_context = lifespan


def main():
    """Main entry point."""
    config = get_config()

    # Set up signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info(f"Starting daemon on {config.daemon.host}:{config.daemon.port}")

    try:
        uvicorn.run(
            app,
            host=config.daemon.host,
            port=config.daemon.port,
            log_level=config.daemon.log_level.lower(),
            access_log=False
        )
    except OSError as e:
        if "Address already in use" in str(e):
            logger.critical(f"Cannot bind to port {config.daemon.port}: Address already in use")
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
