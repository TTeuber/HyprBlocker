"""Shared dependencies for the website blocker API."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lock_manager import get_lock_manager

# Session factory - will be set during startup
_session_factory = None


def set_session_factory(factory):
    """Set the session factory for API routes."""
    global _session_factory
    _session_factory = factory


async def get_session():
    """Dependency to get a database session."""
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    async with _session_factory() as session:
        yield session


async def check_block_lock(block_id: int):
    """Check if a specific block is locked.

    Raises:
        HTTPException: 403 if block is locked
    """
    lock_manager = get_lock_manager()
    if lock_manager and await lock_manager.is_block_locked(block_id):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot modify block {block_id}: currently locked"
        )
