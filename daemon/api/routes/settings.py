"""Settings API routes for browser enforcement, safe search, watchdog, and lock."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from config import get_config, save_config, reload_config
from time_verifier import get_time_verifier
from watchdog import WatchdogManager, is_settings_locked_ntp
from ..schemas import (
    BrowserEnforcementStatusResponse,
    BrowserEnforcementUpdateRequest,
    SafeSearchStatusResponse,
    SafeSearchUpdateRequest,
    WatchdogStatusResponse,
    WatchdogUpdateRequest,
    SettingsLockResponse,
    SettingsLockRequest,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)


# Browser enforcement endpoints
@router.get("/browser-enforcement", response_model=BrowserEnforcementStatusResponse)
async def get_browser_enforcement_status():
    """Get current browser enforcement status."""
    config = get_config()

    return BrowserEnforcementStatusResponse(
        enabled=config.security.browser_enforcement_enabled,
        source='config' if config.security.browser_enforcement_enabled != True else 'default'
    )


@router.put("/browser-enforcement")
async def update_browser_enforcement_status(request: BrowserEnforcementUpdateRequest):
    """Update browser enforcement setting.

    Blocked if settings are locked.
    """
    # Check if settings are locked
    if is_settings_locked_ntp():
        raise HTTPException(
            status_code=403,
            detail="Settings are locked and cannot be changed"
        )

    # Update config
    config = get_config()
    config.security.browser_enforcement_enabled = request.enabled
    save_config(config)

    # Reload config to apply changes immediately
    reload_config()

    if request.enabled:
        logger.info("Browser enforcement ENABLED via UI")
    else:
        logger.warning("Browser enforcement DISABLED via UI")

    return {"success": True, "enabled": request.enabled}


# Safe search endpoints
@router.get("/safe-search", response_model=SafeSearchStatusResponse)
async def get_safe_search_status():
    """Get current safe search enforcement status."""
    config = get_config()

    return SafeSearchStatusResponse(
        enabled=config.security.safe_search_enabled,
        source='config' if config.security.safe_search_enabled != False else 'default'
    )


@router.put("/safe-search")
async def update_safe_search_status(request: SafeSearchUpdateRequest):
    """Update safe search enforcement setting.

    Blocked if settings are locked.
    """
    # Check if settings are locked
    if is_settings_locked_ntp():
        raise HTTPException(
            status_code=403,
            detail="Settings are locked and cannot be changed"
        )

    # Update config
    config = get_config()
    config.security.safe_search_enabled = request.enabled
    save_config(config)

    # Reload config to apply changes immediately
    reload_config()

    if request.enabled:
        logger.info("Safe search enforcement ENABLED via UI")
    else:
        logger.warning("Safe search enforcement DISABLED via UI")

    return {"success": True, "enabled": request.enabled}


# Watchdog endpoints
@router.get("/watchdog", response_model=WatchdogStatusResponse)
async def get_watchdog_status():
    """Get current watchdog status and active processes."""
    config = get_config()
    manager = WatchdogManager(
        watchdog_count=config.security.watchdog_count,
        daemon_port=config.daemon.port
    )

    active = manager.get_active_watchdogs()

    return WatchdogStatusResponse(
        enabled=config.security.watchdog_enabled,
        count=config.security.watchdog_count,
        active_watchdogs=active
    )


@router.put("/watchdog")
async def update_watchdog_settings(request: WatchdogUpdateRequest):
    """Update watchdog settings.

    Blocked if settings are locked.
    """
    # Check if settings are locked
    if is_settings_locked_ntp():
        raise HTTPException(
            status_code=403,
            detail="Settings are locked and cannot be changed"
        )

    config = get_config()

    if request.enabled is not None:
        old_enabled = config.security.watchdog_enabled
        config.security.watchdog_enabled = request.enabled

        # If enabling, spawn watchdogs
        if request.enabled and not old_enabled:
            manager = WatchdogManager(
                watchdog_count=config.security.watchdog_count,
                daemon_port=config.daemon.port
            )
            manager.spawn_watchdogs()
            logger.info("Watchdog processes spawned")

        # If disabling, signal shutdown
        elif not request.enabled and old_enabled:
            manager = WatchdogManager(
                watchdog_count=config.security.watchdog_count,
                daemon_port=config.daemon.port
            )
            manager.signal_shutdown()
            logger.info("Watchdog shutdown signaled")

    if request.count is not None:
        # Clamp to valid range
        config.security.watchdog_count = max(2, min(5, request.count))

    save_config(config)
    reload_config()

    return {
        "success": True,
        "enabled": config.security.watchdog_enabled,
        "count": config.security.watchdog_count
    }


# Settings lock endpoints
@router.get("/lock", response_model=SettingsLockResponse)
async def get_settings_lock():
    """Get current settings lock status."""
    config = get_config()
    lock_until_str = config.security.settings_lock_until

    if not lock_until_str:
        return SettingsLockResponse(
            locked=False,
            lock_until=None,
            remaining_seconds=None
        )

    # Check if actually locked (NTP verified)
    is_locked = is_settings_locked_ntp()

    if not is_locked:
        return SettingsLockResponse(
            locked=False,
            lock_until=lock_until_str,
            remaining_seconds=0
        )

    # Calculate remaining time
    try:
        lock_until = datetime.fromisoformat(lock_until_str)
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        remaining = int((lock_until - now).total_seconds())
    except Exception:
        remaining = None

    return SettingsLockResponse(
        locked=True,
        lock_until=lock_until_str,
        remaining_seconds=max(0, remaining) if remaining else None
    )


@router.post("/lock")
async def lock_settings(request: SettingsLockRequest):
    """Lock settings until a specific datetime.

    Uses NTP verification to prevent clock manipulation.
    """
    # Parse and validate lock_until
    try:
        lock_until = datetime.fromisoformat(request.lock_until)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid datetime format. Use ISO format like '2024-12-25T14:30:00'"
        )

    # Ensure it's in the future (use NTP time)
    verifier = get_time_verifier()
    if not verifier.is_system_time_valid():
        raise HTTPException(
            status_code=403,
            detail="System time appears to be manipulated. Cannot set lock."
        )

    now = datetime.now(timezone.utc)
    if lock_until.tzinfo is None:
        lock_until = lock_until.replace(tzinfo=timezone.utc)

    if lock_until <= now:
        raise HTTPException(
            status_code=400,
            detail="lock_until must be in the future"
        )

    # Save the lock
    config = get_config()
    config.security.settings_lock_until = lock_until.isoformat()
    save_config(config)
    reload_config()

    logger.info(f"Settings locked until {lock_until.isoformat()}")

    return {
        "success": True,
        "lock_until": lock_until.isoformat()
    }


@router.delete("/lock")
async def unlock_settings():
    """Unlock settings.

    Only works if the lock has expired (verified via NTP).
    """
    # Check if still locked
    if is_settings_locked_ntp():
        raise HTTPException(
            status_code=403,
            detail="Settings are still locked. Cannot unlock before expiry."
        )

    # Clear the lock
    config = get_config()
    config.security.settings_lock_until = None
    save_config(config)
    reload_config()

    logger.info("Settings lock cleared")

    return {"success": True}
