#!/usr/bin/env python3
"""Main entry point for the website blocker daemon."""

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
from service_enforcer import ensure_service_enabled
from watchdog import WatchdogManager

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
_server: uvicorn.Server = None  # Uvicorn server instance; signal handler sets _server.should_exit
_shutdown_prevention_cache: bool = False  # Cached shutdown prevention state for signal handler
_watchdog_manager: WatchdogManager = None  # Watchdog manager instance


async def get_all_blocks() -> List[Block]:
    """Get all blocks from the database."""
    async with _session_factory() as session:
        result = await session.execute(select(Block))
        return list(result.scalars().all())


async def schedule_check_job():
    """Job that runs periodically to check schedules."""
    global _shutdown_prevention_cache
    try:
        scheduler = get_scheduler()
        if scheduler:
            await scheduler.check_schedules()

        lock_manager = get_lock_manager()
        if lock_manager:
            await lock_manager.check_transitions()

        # Update cached shutdown prevention state for signal handler
        config = get_config()
        _shutdown_prevention_cache = config.security.shutdown_prevention_enabled

        # Prevent `systemctl --user disable` from sticking
        if _shutdown_prevention_cache:
            ensure_service_enabled()

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
    global _shutdown_prevention_cache

    # Use cached shutdown prevention state to avoid async issues in signal handler
    if _shutdown_prevention_cache:
        logger.warning("Ignoring stop signal - shutdown prevention is active")
        try:
            import subprocess
            subprocess.run(
                ["notify-send", "Website Blocker", "Cannot stop daemon - shutdown prevention is active"],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass
        return  # Refuse to stop — uvicorn loop keeps running because we own the signal handlers

    logger.info(f"Received signal {signum}, shutting down...")
    if _server is not None:
        _server.should_exit = True


@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for FastAPI."""
    global _scheduler, _session_factory, _watchdog_manager

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
    init_lock_manager(get_all_blocks, _session_factory)
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

    # Spawn watchdog processes if both shutdown prevention AND watchdog are enabled
    if config.security.shutdown_prevention_enabled and config.security.watchdog_enabled:
        _watchdog_manager = WatchdogManager(
            watchdog_count=config.security.watchdog_count,
            daemon_port=config.daemon.port
        )
        pids = _watchdog_manager.spawn_watchdogs()
        logger.info(f"Spawned {len(pids)} watchdog processes: {pids}")

    # Run initial checks
    await schedule_check_job()
    await monitor_check_job()

    yield

    # Shutdown
    logger.info("Shutting down daemon")

    # Signal watchdogs to shutdown only when shutdown prevention is off.
    # If prevention is on, the legitimate off-switch is the settings API
    # (update_shutdown_prevention_status), which disables watchdogs directly before
    # allowing the daemon to stop.  We must not tear down watchdogs here — they are
    # the very mechanism keeping the daemon alive after an unexpected crash/kill.
    config = get_config()
    if _watchdog_manager and not config.security.shutdown_prevention_enabled:
        _watchdog_manager.signal_shutdown()
        logger.info("Signaled watchdog shutdown")

    if _scheduler:
        _scheduler.shutdown()
    await engine.dispose()


# Set the lifespan on the app
app.router.lifespan_context = lifespan


def main():
    """Main entry point."""
    global _server

    config = get_config()

    # Build the uvicorn server object before installing our signal handlers so
    # we can store it in _server first (signal handler needs the reference).
    uvicorn_config = uvicorn.Config(
        app,
        host=config.daemon.host,
        port=config.daemon.port,
        log_level=config.daemon.log_level.lower(),
        access_log=False
    )
    _server = uvicorn.Server(uvicorn_config)

    # Suppress uvicorn's own signal-handler installation so our handlers below
    # remain authoritative for the lifetime of the process.
    _server.install_signal_handlers = lambda: None

    # Install our handlers AFTER creating the server (so _server is populated).
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info(f"Starting daemon on {config.daemon.host}:{config.daemon.port}")

    try:
        _server.run()
    except OSError as e:
        if "Address already in use" in str(e):
            logger.critical(f"Cannot bind to port {config.daemon.port}: Address already in use")
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
