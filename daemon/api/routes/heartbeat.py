"""Heartbeat and grace period API routes."""

from fastapi import APIRouter

from heartbeat_tracker import get_heartbeat_tracker
from ..schemas import HeartbeatRequest, HeartbeatResponse, GracePeriodResponse

router = APIRouter(prefix="/api", tags=["heartbeat"])


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def receive_heartbeat(heartbeat: HeartbeatRequest):
    """Receive a heartbeat from a browser extension."""
    tracker = get_heartbeat_tracker()
    tracker.register_heartbeat(
        pid=heartbeat.pid,
        browser=heartbeat.browser,
        incognito=heartbeat.incognito,
        incognito_enabled=heartbeat.incognito_enabled,
        extension_id=heartbeat.extension_id,
        window_count=heartbeat.window_count
    )
    return HeartbeatResponse(status="ok")


@router.post("/grace-period", response_model=GracePeriodResponse)
async def start_grace_period():
    """Start a 30-second grace period for adding browser extensions."""
    tracker = get_heartbeat_tracker()
    expires_at = tracker.start_grace_period(duration_seconds=30)

    return GracePeriodResponse(
        active=True,
        expires_at=expires_at.isoformat(),
        remaining_seconds=30
    )


@router.get("/grace-period", response_model=GracePeriodResponse)
async def get_grace_period_status():
    """Get the current grace period status."""
    tracker = get_heartbeat_tracker()

    if tracker.is_grace_period_active():
        return GracePeriodResponse(
            active=True,
            expires_at=tracker._grace_period_until.isoformat() if tracker._grace_period_until else None,
            remaining_seconds=tracker.get_grace_period_remaining()
        )

    return GracePeriodResponse(
        active=False,
        expires_at=None,
        remaining_seconds=None
    )
