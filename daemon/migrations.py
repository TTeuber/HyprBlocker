"""Database migrations for schema changes."""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def migrate_schedules_to_blocks(session: AsyncSession) -> None:
    """Migrate Schedule table to Block table with new schema.

    This migration:
    1. Renames 'schedules' to 'blocks' with new block_mode/lock_mode fields
    2. Renames 'schedule_rules' to 'block_rule_associations'
    3. Maps old schedule_type to new block_mode and lock_mode
    """
    # Check if old schedules table exists
    result = await session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'"
    ))
    if not result.fetchone():
        logger.info("No schedules table to migrate")
        return

    # Check if new blocks table already exists
    result = await session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='blocks'"
    ))
    if result.fetchone():
        logger.info("Blocks table already exists, skipping migration")
        return

    logger.info("Starting migration from schedules to blocks")

    # Create new blocks table with separated block_mode and lock_mode
    await session.execute(text("""
        CREATE TABLE blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            block_mode VARCHAR(20) NOT NULL DEFAULT 'always',
            block_days_of_week TEXT,
            block_start_time VARCHAR(10),
            block_end_time VARCHAR(10),
            lock_mode VARCHAR(20) NOT NULL DEFAULT 'none',
            lock_days_of_week TEXT,
            lock_start_time VARCHAR(10),
            lock_end_time VARCHAR(10),
            lock_until DATETIME,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL
        )
    """))

    # Migrate data from schedules to blocks
    # Map old schedule_type to new block_mode and lock_mode:
    # - time_range -> block_mode='time_range', lock_mode='none'
    # - locked_until -> block_mode='always', lock_mode='locked_until'
    await session.execute(text("""
        INSERT INTO blocks (
            id, name,
            block_mode, block_days_of_week, block_start_time, block_end_time,
            lock_mode, lock_until,
            enabled, created_at
        )
        SELECT
            id, name,
            CASE
                WHEN schedule_type = 'time_range' THEN 'time_range'
                WHEN schedule_type = 'locked_until' THEN 'always'
                ELSE 'always'
            END,
            CASE WHEN schedule_type = 'time_range' THEN days_of_week ELSE NULL END,
            CASE WHEN schedule_type = 'time_range' THEN start_time ELSE NULL END,
            CASE WHEN schedule_type = 'time_range' THEN end_time ELSE NULL END,
            CASE
                WHEN schedule_type = 'locked_until' THEN 'locked_until'
                ELSE 'none'
            END,
            locked_until,
            enabled, created_at
        FROM schedules
    """))

    # Create new block_rule_associations table
    await session.execute(text("""
        CREATE TABLE block_rule_associations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id INTEGER NOT NULL,
            rule_id INTEGER NOT NULL,
            FOREIGN KEY (block_id) REFERENCES blocks(id),
            FOREIGN KEY (rule_id) REFERENCES block_rules(id)
        )
    """))

    # Migrate schedule_rules to block_rule_associations
    await session.execute(text("""
        INSERT INTO block_rule_associations (id, block_id, rule_id)
        SELECT id, schedule_id, rule_id FROM schedule_rules
    """))

    # Rename old tables to backup (SQLite doesn't support DROP in all cases)
    await session.execute(text("""
        ALTER TABLE schedule_rules RENAME TO schedule_rules_backup
    """))

    await session.execute(text("""
        ALTER TABLE schedules RENAME TO schedules_backup
    """))

    await session.commit()
    logger.info("Migration completed successfully - schedules -> blocks")


async def migrate_rules_to_text_fields(session: AsyncSession) -> None:
    """Migrate BlockRule data to text fields in Block table.

    This migration:
    1. Adds new text columns to blocks table
    2. Migrates existing rule data to text format
    3. Drops block_rules and block_rule_associations tables
    """
    # Check if migration needed (look for block_rules table)
    result = await session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='block_rules'"
    ))
    if not result.fetchone():
        logger.info("No block_rules table to migrate")
        return  # Already migrated

    logger.info("Migrating rules to text fields...")

    # 1. Add new columns to blocks table if they don't exist
    for column in ['websites_blocked', 'websites_allowed', 'apps_blocked', 'apps_allowed']:
        try:
            await session.execute(text(f"ALTER TABLE blocks ADD COLUMN {column} TEXT"))
        except Exception:
            pass  # Column already exists

    # 2. Migrate data from block_rules to blocks
    result = await session.execute(text("""
        SELECT b.id, br.rule_type, br.target
        FROM blocks b
        JOIN block_rule_associations bra ON b.id = bra.block_id
        JOIN block_rules br ON bra.rule_id = br.id
        WHERE br.enabled = 1
        ORDER BY b.id, br.rule_type, br.target
    """))

    blocks_data = {}
    for row in result:
        block_id, rule_type, target = row
        if block_id not in blocks_data:
            blocks_data[block_id] = {'websites': [], 'apps': []}

        if rule_type == 'website':
            blocks_data[block_id]['websites'].append(target)
        elif rule_type == 'application':
            blocks_data[block_id]['apps'].append(target)

    # 3. Update blocks with migrated data
    for block_id, data in blocks_data.items():
        websites = '\n'.join(data['websites']) if data['websites'] else None
        apps = '\n'.join(data['apps']) if data['apps'] else None

        await session.execute(text("""
            UPDATE blocks
            SET websites_blocked = :websites, apps_blocked = :apps
            WHERE id = :id
        """), {'websites': websites, 'apps': apps, 'id': block_id})

    # 4. Fix BlockEvent table - remove foreign key constraint to block_rules
    # SQLite doesn't support dropping foreign keys, so we recreate the table
    try:
        # Create new table without foreign key
        await session.execute(text("""
            CREATE TABLE block_events_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                blocked_target VARCHAR(500) NOT NULL,
                timestamp DATETIME NOT NULL,
                event_type VARCHAR(50) NOT NULL
            )
        """))

        # Copy existing data
        await session.execute(text("""
            INSERT INTO block_events_new (id, rule_id, blocked_target, timestamp, event_type)
            SELECT id, rule_id, blocked_target, timestamp, event_type
            FROM block_events
        """))

        # Drop old table and rename new one
        await session.execute(text("DROP TABLE block_events"))
        await session.execute(text("ALTER TABLE block_events_new RENAME TO block_events"))

        logger.info("Fixed BlockEvent table foreign key constraint")
    except Exception as e:
        logger.warning(f"BlockEvent table may already be fixed: {e}")

    # 5. Drop old tables
    await session.execute(text("DROP TABLE IF EXISTS block_rule_associations"))
    await session.execute(text("DROP TABLE IF EXISTS block_rules"))

    await session.commit()
    logger.info(f"Migrated {len(blocks_data)} blocks from old rule format")
