"""Block CRUD API routes."""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Block
from lock_manager import get_lock_manager
from ..schemas import BlockCreate, BlockUpdate, BlockResponse
from ..deps import get_session, check_block_lock

router = APIRouter(prefix="/api", tags=["blocks"])


@router.get("/blocks", response_model=List[BlockResponse])
async def get_blocks(session: AsyncSession = Depends(get_session)):
    """Get all blocks."""
    result = await session.execute(select(Block))
    blocks = result.scalars().all()

    return [BlockResponse(**b.to_dict()) for b in blocks]


@router.post("/blocks", response_model=BlockResponse)
async def create_block(block: BlockCreate, session: AsyncSession = Depends(get_session)):
    """Create a new block."""
    if block.block_mode not in ('always', 'time_range', 'disabled'):
        raise HTTPException(status_code=400, detail="Invalid block_mode")

    if block.lock_mode not in ('none', 'time_range', 'locked_until'):
        raise HTTPException(status_code=400, detail="Invalid lock_mode")

    lock_until = None
    if block.lock_until:
        try:
            lock_until = datetime.fromisoformat(block.lock_until)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid lock_until datetime format")

    db_block = Block(
        name=block.name,
        block_mode=block.block_mode,
        block_days_of_week=block.block_days_of_week,
        block_start_time=block.block_start_time,
        block_end_time=block.block_end_time,
        lock_mode=block.lock_mode,
        lock_days_of_week=block.lock_days_of_week,
        lock_start_time=block.lock_start_time,
        lock_end_time=block.lock_end_time,
        lock_until=lock_until,
        websites_blocked=block.websites_blocked,
        websites_allowed=block.websites_allowed,
        apps_blocked=block.apps_blocked,
        apps_allowed=block.apps_allowed,
        enabled=block.enabled
    )
    session.add(db_block)
    await session.commit()
    await session.refresh(db_block)

    return BlockResponse(**db_block.to_dict())


@router.put("/blocks/{block_id}", response_model=BlockResponse)
async def update_block(
    block_id: int,
    block: BlockUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a block."""
    await check_block_lock(block_id)

    result = await session.execute(select(Block).where(Block.id == block_id))
    db_block = result.scalar_one_or_none()

    if db_block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    if block.name is not None:
        db_block.name = block.name

    if block.block_mode is not None:
        if block.block_mode not in ('always', 'time_range', 'disabled'):
            raise HTTPException(status_code=400, detail="Invalid block_mode")
        db_block.block_mode = block.block_mode

    if block.block_days_of_week is not None:
        db_block.block_days_of_week = block.block_days_of_week

    if block.block_start_time is not None:
        db_block.block_start_time = block.block_start_time

    if block.block_end_time is not None:
        db_block.block_end_time = block.block_end_time

    # Handle lock_mode and lock_until together for consistency
    if block.lock_mode is not None:
        if block.lock_mode not in ('none', 'time_range', 'locked_until'):
            raise HTTPException(status_code=400, detail="Invalid lock_mode")
        db_block.lock_mode = block.lock_mode

        # Clear lock_until if changing away from locked_until mode
        if block.lock_mode != 'locked_until':
            db_block.lock_until = None

    if block.lock_days_of_week is not None:
        db_block.lock_days_of_week = block.lock_days_of_week

    if block.lock_start_time is not None:
        db_block.lock_start_time = block.lock_start_time

    if block.lock_end_time is not None:
        db_block.lock_end_time = block.lock_end_time

    # Handle lock_until with validation
    if block.lock_until is not None:
        # Skip empty strings
        if block.lock_until.strip() == '':
            # If explicitly setting to empty, clear it
            db_block.lock_until = None
        else:
            try:
                db_block.lock_until = datetime.fromisoformat(block.lock_until)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid lock_until datetime format. Expected ISO format like '2024-12-25T14:30'")

    # Validate that locked_until mode has a lock_until value
    if db_block.lock_mode == 'locked_until' and db_block.lock_until is None:
        raise HTTPException(status_code=400, detail="lock_until datetime is required when lock_mode is 'locked_until'")

    if block.enabled is not None:
        db_block.enabled = block.enabled

    if block.websites_blocked is not None:
        db_block.websites_blocked = block.websites_blocked

    if block.websites_allowed is not None:
        db_block.websites_allowed = block.websites_allowed

    if block.apps_blocked is not None:
        db_block.apps_blocked = block.apps_blocked

    if block.apps_allowed is not None:
        db_block.apps_allowed = block.apps_allowed

    await session.commit()
    await session.refresh(db_block)

    return BlockResponse(**db_block.to_dict())


@router.delete("/blocks/{block_id}")
async def delete_block(block_id: int, session: AsyncSession = Depends(get_session)):
    """Delete a block."""
    await check_block_lock(block_id)

    result = await session.execute(select(Block).where(Block.id == block_id))
    db_block = result.scalar_one_or_none()

    if db_block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    await session.delete(db_block)
    await session.commit()

    return {"status": "deleted"}


@router.get("/blocks/{block_id}/lock-status")
async def get_block_lock_status(block_id: int):
    """Get lock status for a specific block."""
    lock_manager = get_lock_manager()
    if lock_manager:
        is_locked = await lock_manager.is_block_locked(block_id)
        return {"locked": is_locked}
    return {"locked": False}
