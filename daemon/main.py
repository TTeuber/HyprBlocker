#!/usr/bin/env python3
"""Main entry point for the website blocker daemon."""

import logging
import os
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from daemon.api import app, set_session_factory
from daemon.config import get_config, get_config_path
from daemon.database import Block, create_session_factory, init_database
from daemon.hyprland_monitor import (
    CompositorIPCError,
    get_hyprland_monitor,
    init_hyprland_monitor,
)
from daemon.lock_manager import get_lock_manager, init_lock_manager
from daemon.scheduler import get_scheduler, init_scheduler
from daemon.service_enforcer import enforce_user_side
from daemon.watchdog import WatchdogManager


# Set up logging
def setup_logging():
    """Configure logging for the daemon."""
    config = get_config()
    log_level = getattr(logging, config.daemon.log_level.upper(), logging.INFO)

    # Create log directory
    from daemon import paths

    log_dir = str(paths.ensure_dir(paths.log_dir()))
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
_monitor_healthy = True


async def get_all_blocks() -> list[Block]:
    """Get all blocks from the database."""
    async with _session_factory() as session:
        result = await session.execute(select(Block))
        return list(result.scalars().all())


async def schedule_check_job():
    """Job that runs periodically to check schedules."""
    global _monitor_healthy, _shutdown_prevention_cache
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

        # Prevent `systemctl --user disable` from sticking, and (root layout) delete
        # any user-writable shadow unit / native-messaging manifest that would
        # override the root-owned copies.
        if _shutdown_prevention_cache:
            enforce_user_side()

        # Re-evaluate the watchdog-mesh fallback every tick, not just at startup:
        # if the root enforcer was healthy at boot (mesh not spawned) and later
        # dies, the mesh must come up now so protection never silently regresses
        # in the post-startup window (review finding R6).
        _ensure_mesh_fallback(config)

        # Expire overdue tier-1 grants so they stop being overlaid onto
        # blocked-sites even across daemon restarts (grants also self-expire at
        # read time; this keeps the store from growing unbounded).
        try:
            from datetime import UTC, datetime

            from daemon.grants import store as grant_store

            grant_store.prune_expired(datetime.now(UTC))
        except Exception as e:
            logger.debug(f"Grant prune skipped: {e}")

        # Root layout: answer the enforcer's liveness challenge (R4). We echo the
        # current challenge nonce into the user-writable heartbeat so the enforcer
        # can attest "the real daemon is alive and enforcing". A write failure is
        # loud (M4) — it means the enforcer will fail closed.
        from daemon import paths

        if paths.layout() == "root":
            try:
                from enforcer import heartbeat as hb

                nonce = hb.read_challenge()
                if nonce is not None and _monitor_healthy:
                    hb.write_echo(nonce, os.getpid())
                elif nonce is not None:
                    logger.error("Skipping heartbeat echo while compositor monitoring is unhealthy")
            except Exception as e:
                logger.error("Heartbeat echo FAILED (enforcer may fail closed): %s", e)

    except Exception as e:
        logger.error(f"Error in schedule check job: {e}")


async def monitor_check_job():
    """Job that runs periodically to check windows and browsers."""
    global _monitor_healthy
    try:
        monitor = get_hyprland_monitor()
        if monitor:
            result = await monitor.run_check()
            _monitor_healthy = True
            if result["apps_closed"] > 0 or result["browsers_closed"] > 0:
                logger.info(
                    f"Monitor check: closed {result['apps_closed']} apps, "
                    f"{result['browsers_closed']} browsers"
                )
    except CompositorIPCError as e:
        _monitor_healthy = False
        logger.error("Compositor monitoring unavailable; enforcement heartbeat withheld: %s", e)
    except Exception as e:
        _monitor_healthy = False
        logger.error(f"Error in monitor check job; enforcement heartbeat withheld: {e}")


def handle_signal(signum, frame):
    """Handle termination signals."""
    global _shutdown_prevention_cache

    # Use cached shutdown prevention state to avoid async issues in signal handler
    if _shutdown_prevention_cache:
        logger.warning("Ignoring stop signal - shutdown prevention is active")
        try:
            import subprocess
            subprocess.run(
                ["notify-send", "HyprBlocker", "Cannot stop daemon - shutdown prevention is active"],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass
        return  # Refuse to stop — uvicorn loop keeps running because we own the signal handlers

    logger.info(f"Received signal {signum}, shutting down...")
    if _server is not None:
        _server.should_exit = True


def _ensure_mesh_fallback(config) -> None:
    """Spawn the watchdog mesh if it should run now but isn't already.

    Called every schedule tick. Under the root layout this brings the mesh up as
    a fallback when the enforcer transitions healthy→down mid-session; under the
    user layout the mesh is spawned at startup and this is a no-op once running.
    """
    global _watchdog_manager
    from daemon import enforcer_link

    if not enforcer_link.should_run_watchdog_mesh(
        config.security.shutdown_prevention_enabled,
        config.security.watchdog_enabled,
    ):
        return
    # Already have live watchdogs? Then nothing to do.
    if _watchdog_manager is not None and _watchdog_manager.get_active_watchdogs():
        return
    logger.warning("Spawning watchdog mesh fallback (enforcer down or user layout)")
    _watchdog_manager = WatchdogManager(
        watchdog_count=config.security.watchdog_count,
        daemon_port=config.daemon.port,
    )
    _watchdog_manager.spawn_watchdogs()


def _root_layout_startup() -> None:
    """One-shot reconciliation at the first root-layout boot after install.

    Review R9: the installer *copies* the live ``~/.config/hyprblocker`` state so
    the running daemon is never disturbed, which opens a divergence window — any
    config/DB change the user makes between install and reboot lands in the old
    files. Here, on the first root-layout startup, we re-copy those files if the
    ``~/.config`` source is newer than the ``/var/lib`` copy, closing that window
    before the DB is opened. Then we delete the user-dir shadow unit the installer
    left in place so the root-owned ``/etc/systemd/user`` unit wins thereafter.

    Entirely best-effort and guarded: a no-op under the user layout, and any error
    is logged rather than blocking daemon startup.
    """
    from daemon import paths

    if paths.layout() != "root":
        return

    import shutil
    from pathlib import Path

    legacy = Path.home() / ".config" / "hyprblocker"
    try:
        dest = paths.user_dir()
        paths.ensure_dir(dest)
        for name in ("config.json", "blocker.db", "blocker.db-wal", "blocker.db-shm"):
            src = legacy / name
            tgt = dest / name
            if src.exists() and (not tgt.exists() or src.stat().st_mtime > tgt.stat().st_mtime):
                shutil.copy2(src, tgt)
                logger.info("Re-synced %s from legacy user state", name)
    except Exception as e:
        logger.error("Root-layout state re-sync failed: %s", e)

    try:
        from daemon.service_enforcer import delete_shadow_units

        delete_shadow_units()
    except Exception as e:
        logger.error("Shadow-unit deletion failed: %s", e)


@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for FastAPI."""
    global _scheduler, _session_factory, _watchdog_manager

    logger.info("Starting HyprBlocker Daemon")

    # Root layout: reconcile with the just-installed root tree before touching
    # any state (re-sync live user state that changed between install and reboot,
    # then delete the user-dir shadow unit so /etc/systemd/user wins). Guarded so
    # it is a no-op in the user layout. Must run BEFORE the DB is opened (R9).
    # main() already ran this before the first config read; repeating here is
    # idempotent (copy2 preserves mtimes) and covers non-main() entrypoints.
    _root_layout_startup()

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

    # Spawn watchdog processes if both shutdown prevention AND watchdog are enabled.
    # Under the root layout the root enforcer supersedes the mesh — but only while
    # it is actually alive; if its snapshot is stale/absent the mesh runs as a
    # fallback so protection never silently regresses (review finding R6).
    from daemon import enforcer_link

    if enforcer_link.should_run_watchdog_mesh(
        config.security.shutdown_prevention_enabled,
        config.security.watchdog_enabled,
    ):
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

    # R9: reconcile root-layout state BEFORE the first config read. get_config()
    # creates a defaults file when none exists, and that fresh file would
    # mtime-beat the legacy config the re-sync is supposed to carry over —
    # silently booting the daemon with default (weakest) security settings.
    _root_layout_startup()

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
