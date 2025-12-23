# Website Blocker - Project Status

**Last Updated:** December 22, 2025

## Overview

The Website Blocker project is a functional website and application blocking system for Arch Linux + Hyprland. The system consists of a Python daemon, desktop GUI app, and browser extension working together to enforce focus periods with strict lock mode.

## Current Status: **FUNCTIONAL** ✅

The core system is working and can be used for basic blocking functionality.

---

## Recent Major Changes (December 2025)

### Data Model Refactoring

We recently completed a **major refactoring** of the data model and UI:

#### What Changed:
1. **Removed Standalone Rules** - Rules no longer exist as separate entities
2. **Rules Now Belong to Blocks** - Each block contains its own rules stored as newline-separated text
3. **Added Allow Lists** - Support for blocking with exceptions (e.g., block `twitch.tv` but allow `twitch.tv/specific-channel`)
4. **Path-Specific Blocking** - Can now block specific paths like `youtube.com/shorts` instead of entire domains
5. **Per-Block Locking** - UI now reflects per-block lock status instead of global lock

#### Migration:
- Existing data was automatically migrated from the old `block_rules` table to text fields
- `BlockEvent` table updated to remove foreign key constraint
- All API endpoints updated to work with new structure

---

## Components Status

### 1. Daemon ✅ WORKING

**Status:** Fully functional with recent fixes

**What's Working:**
- ✅ FastAPI server running on port 8765
- ✅ Block schedule checking (every 10 seconds)
- ✅ Hyprland window monitoring (every 5 seconds)
- ✅ Browser extension heartbeat tracking
- ✅ Lock mode enforcement (per-block and global)
- ✅ NTP time verification
- ✅ Signal handling (refuses SIGTERM during lock)
- ✅ SQLite database with automatic migrations
- ✅ systemd service integration
- ✅ Application blocking via Hyprland IPC
- ✅ Browser killing when extension missing
- ✅ Text-based rule storage with allow lists
- ✅ Path-specific website blocking

**Recent Fixes:**
- Fixed `Block.block_rules` relationship removal
- Updated `hyprland_monitor.py` to use `AppBlocker` instead of deleted methods
- Removed `BlockEvent` foreign key to deleted `block_rules` table
- Fixed API status endpoint to remove `BlockRule` references

**Files:**
- `daemon/main.py` - Entry point
- `daemon/api.py` - REST API endpoints
- `daemon/blocker.py` - URL/app pattern matching with allow lists
- `daemon/scheduler.py` - Block schedule management
- `daemon/hyprland_monitor.py` - Window monitoring
- `daemon/heartbeat_tracker.py` - Extension heartbeat tracking
- `daemon/lock_manager.py` - Lock enforcement
- `daemon/time_verifier.py` - NTP verification
- `daemon/database.py` - SQLAlchemy models
- `daemon/migrations.py` - Database migrations

**Configuration:**
- Location: `~/.config/website-blocker/config.json`
- Database: `~/.config/website-blocker/blocker.db`
- Service: `systemctl --user status website-blocker`

---

### 2. Desktop App ✅ WORKING (Needs Testing)

**Status:** Code updated, UI refactored, needs testing

**What's Working:**
- ✅ pywebview + GTK window
- ✅ Dashboard with status display
- ✅ Blocks page with add/edit/delete
- ✅ Statistics page
- ✅ Browser status page with grace period
- ✅ Settings page
- ✅ Lock banner (global lock indicator)
- ✅ Text area input for rules (4 fields per block)
- ✅ Per-block lock checking

**Recent Changes:**
- ✅ Removed all standalone rule UI (quick add card, rules page, add rule modal)
- ✅ Updated block modal with text areas for inline rule entry
- ✅ Removed global lock state management
- ✅ Updated JavaScript to check per-block lock status
- ✅ Fixed rule counting to parse from text fields
- ✅ Removed all rule-related API calls from backend

**What Needs Testing:**
- ⚠️ Creating blocks with text-based rules
- ⚠️ Editing existing blocks
- ⚠️ Path-specific blocking (e.g., `youtube.com/shorts`)
- ⚠️ Allow list functionality
- ⚠️ Per-block lock UI behavior
- ⚠️ Grace period for extension installation

**Files:**
- `desktop-app/main.py` - Entry point
- `desktop-app/api_client.py` - Daemon API wrapper
- `desktop-app/web/index.html` - UI structure
- `desktop-app/web/app.js` - Frontend logic
- `desktop-app/web/styles.css` - Styling

---

### 3. Browser Extension ⚠️ NEEDS UPDATES

**Status:** Functional but needs updates for new data model

**What's Working:**
- ✅ Heartbeat sending (every 30 seconds)
- ✅ PID detection via native messaging
- ✅ Incognito detection
- ✅ Website blocking via webRequest API
- ✅ Blocked page display
- ✅ Works in Firefox and Chromium

**What Needs Updates:**
- ⚠️ Extension fetches `/api/rules` which no longer exists
- ⚠️ Need to create new endpoint or update extension to use blocks
- ⚠️ Path-specific blocking may need pattern matching updates
- ⚠️ Allow list logic needs implementation

**Files:**
- `extension/manifest.json` - Extension manifest
- `extension/background.js` - Main extension logic (NEEDS UPDATE)
- `extension/blocked.html` - Blocked page
- `extension/popup/` - Extension popup UI

**Installation Locations:**
- Extension: `~/.local/share/website-blocker/extension/`
- Native host: `~/.mozilla/native-messaging-hosts/` (Firefox)
- Native host: `~/.config/google-chrome/NativeMessagingHosts/` (Chrome)

---

## API Endpoints

### Current (Updated)

**Status & Info:**
- `GET /api/status` - Daemon status and lock state ✅
- `GET /api/stats` - Blocking statistics ✅
- `GET /api/browsers` - Browser extension status ✅

**Blocks (Formerly Schedules):**
- `GET /api/blocks` - List all blocks ✅
- `POST /api/blocks` - Create a block ✅
- `PUT /api/blocks/{id}` - Update a block ✅
- `DELETE /api/blocks/{id}` - Delete a block ✅
- `GET /api/blocks/{id}/lock-status` - Get lock status for a block ✅

**Extension:**
- `POST /api/heartbeat` - Extension heartbeat ✅
- `GET /api/grace-period` - Grace period status ✅
- `POST /api/grace-period` - Start grace period ✅

### Removed (No Longer Exist)
- ❌ `GET /api/rules` - Rules are now part of blocks
- ❌ `POST /api/rules` - Create rules via block text areas
- ❌ `PUT /api/rules/{id}` - Edit via blocks
- ❌ `DELETE /api/rules/{id}` - Delete via blocks

---

## Database Schema

### Current Tables

**blocks** - Block configurations with inline rules
- `id` - Primary key
- `name` - Block name (e.g., "Work Focus")
- `block_mode` - When to block: 'always', 'time_range', 'disabled'
- `block_days_of_week` - JSON array for time_range mode
- `block_start_time` - Start time for time_range mode
- `block_end_time` - End time for time_range mode
- `lock_mode` - When config is locked: 'none', 'time_range', 'locked_until'
- `lock_days_of_week` - JSON array for lock time_range
- `lock_start_time` - Lock start time
- `lock_end_time` - Lock end time
- `lock_until` - Absolute datetime for locked_until mode
- **`websites_blocked`** - Newline-separated website patterns ⭐ NEW
- **`websites_allowed`** - Newline-separated allow list ⭐ NEW
- **`apps_blocked`** - Newline-separated app patterns ⭐ NEW
- **`apps_allowed`** - Newline-separated app allow list ⭐ NEW
- `enabled` - Whether block is active
- `created_at` - Creation timestamp

**block_events** - Blocking event log
- `id` - Primary key
- `rule_id` - Legacy field (nullable, no FK)
- `blocked_target` - What was blocked
- `timestamp` - When it was blocked
- `event_type` - Type: 'website_blocked', 'app_closed', 'browser_killed'

**heartbeat_logs** - Browser extension heartbeats
- `id` - Primary key
- `browser_pid` - Browser process ID
- `browser_name` - Browser type
- `incognito` - Whether incognito mode
- `timestamp` - Heartbeat time

### Removed Tables
- ❌ `block_rules` - Replaced by text fields in blocks
- ❌ `block_rule_associations` - No longer needed
- ❌ `schedules` - Renamed to blocks (migrated)
- ❌ `schedule_rules` - Replaced by text fields

---

## Testing Status

### Tested ✅
- ✅ Daemon starts and runs
- ✅ API endpoints respond correctly
- ✅ Database migrations run successfully
- ✅ Block schedule checking works
- ✅ Lock mode prevents configuration changes
- ✅ Hyprland window detection
- ✅ Browser heartbeat tracking
- ✅ systemd service integration

### Needs Testing ⚠️
- ⚠️ Desktop app with new UI
- ⚠️ Creating blocks with text-based rules
- ⚠️ Path-specific blocking (youtube.com/shorts)
- ⚠️ Allow lists (block twitch.tv, allow twitch.tv/channel)
- ⚠️ Per-block lock UI behavior
- ⚠️ Extension with updated API
- ⚠️ End-to-end: Create block → Schedule activates → Site blocked

### Not Yet Tested ❌
- ❌ NTP time verification in production
- ❌ Time manipulation detection
- ❌ Network failure scenarios
- ❌ Extension crash handling
- ❌ Database corruption recovery
- ❌ Multiple blocks with overlapping rules
- ❌ Incognito mode enforcement
- ❌ Long-running stability (24+ hours)

---

## Known Issues

### Critical 🔴
None currently

### High Priority 🟡
1. **Extension needs API update** - Extension fetches `/api/rules` endpoint which no longer exists
   - Need to create `/api/blocked-sites` endpoint or similar
   - Update extension to parse from blocks

2. **Desktop app untested** - UI refactoring complete but not yet tested
   - Need to verify block creation with text areas
   - Test per-block lock checking
   - Verify allow list and path-specific features work

### Medium Priority 🟢
1. **Migration only runs once** - If migration fails, database may be in inconsistent state
   - Consider adding rollback capability
   - Add migration health check

2. **No edit block UI** - Currently can't edit existing blocks in desktop app
   - Add edit button to blocks table
   - Populate modal with existing block data

3. **Rule counting** - Desktop app counts rules by splitting text, could be more robust
   - Handle empty lines
   - Handle whitespace

### Low Priority 🔵
1. **Legacy fields** - `active_rules` in status response set to 0
   - Could remove from API entirely
   - Update frontend to not display

2. **Block event logging** - rule_id is always null
   - Could track block_id instead
   - Add more context to events

---

## Installation & Setup

### Quick Start (Current System)

```bash
# 1. Install dependencies
cd /path/to/Blocker
uv sync

# 2. Run install script
./install.sh

# 3. Start daemon
systemctl --user enable website-blocker
systemctl --user start website-blocker
systemctl --user status website-blocker

# 4. Install browser extension
# Firefox: about:debugging > Load Temporary Add-on
# Chrome: chrome://extensions > Developer mode > Load unpacked
# Location: ~/.local/share/website-blocker/extension/

# 5. Launch desktop app
uv run python desktop-app/main.py
```

### Debugging

```bash
# View daemon logs
journalctl --user -u website-blocker -f

# Test API
curl http://127.0.0.1:8765/api/status | python3 -m json.tool

# Check blocks
curl http://127.0.0.1:8765/api/blocks | python3 -m json.tool

# Check Hyprland windows
hyprctl clients -j | jq '.[] | {class, pid, title}'
```

---

## Next Steps

### Immediate (To Make System Fully Functional)
1. **Update Extension** ⭐ HIGH PRIORITY
   - Create `/api/blocked-sites` endpoint that returns current blocked patterns
   - Update extension to use new endpoint
   - Test path-specific blocking
   - Implement allow list checking

2. **Test Desktop App** ⭐ HIGH PRIORITY
   - Launch app and verify UI works
   - Create test block with text rules
   - Test allow lists
   - Verify per-block locking

3. **Add Edit Block Feature**
   - Add edit button to blocks table
   - Create edit modal or reuse add modal
   - Populate with existing data
   - Handle lock checking

### Short Term
1. **Integration Testing**
   - End-to-end test: Create block → Active → Site blocked
   - Test lock mode transitions
   - Test grace period for extensions
   - Test multiple blocks

2. **Documentation**
   - Update user guide
   - Create setup videos
   - Document new features (allow lists, path blocking)

3. **Polish**
   - Better error messages
   - Loading states
   - Confirmation dialogs
   - Toast notifications

### Medium Term (Enhancements)
1. **Break Intervals** - Allow 5 minutes every hour
2. **Usage Limits** - Block after X minutes total usage
3. **Categories** - Pre-defined site categories
4. **Import/Export** - Backup and share configurations
5. **Stats Dashboard** - Better visualization

### Long Term (Nice to Have)
1. **Rust Rewrite** - Prevent `killall python` bypass
2. **Mobile Companion** - Android/iOS app
3. **Multi-device Sync** - Sync across machines
4. **Accountability Partner** - Share stats

---

## Development Notes

### Project Structure
```
Blocker/
├── daemon/           # Python daemon (systemd service)
├── desktop-app/      # Python + pywebview GUI
├── extension/        # Browser extension
├── config/           # Configuration files
├── install.sh        # Installation script
├── README.md         # User documentation
├── PROJECT_SPEC.md   # Original specification
└── STATUS.md         # This file
```

### Key Design Decisions

1. **Text-Based Rules** - Simpler than separate table, easier to bulk edit
2. **Allow Lists** - More flexible than just blocking
3. **Path-Specific** - Block youtube.com/shorts but not all of YouTube
4. **Per-Block Locking** - Each block has its own lock schedule
5. **Fail-Safe** - When in doubt, block (network down, errors, etc.)

### Architecture Philosophy

- **Daemon is the source of truth** - Everything enforced server-side
- **Extension is untrusted** - Browser can be killed if not compliant
- **Desktop app is convenience** - Just a pretty UI for the API
- **Lock mode is strict** - No bypasses, no warnings, no mercy

---

## Contributing

This is a personal project, but if you find bugs or have suggestions:

1. Check existing issues
2. Create detailed bug report
3. Include logs and steps to reproduce
4. PRs welcome for bug fixes

---

## License

MIT License - See LICENSE file for details

---

## Changelog

### 2025-12-22 - Major Refactoring
- **BREAKING:** Removed standalone rules table
- **BREAKING:** Removed `/api/rules` endpoints
- **Added:** Text-based rule storage in blocks
- **Added:** Allow lists for websites and apps
- **Added:** Path-specific website blocking
- **Added:** Per-block lock status endpoint
- **Fixed:** Database migration for BlockEvent table
- **Fixed:** Daemon errors after refactoring
- **Updated:** Desktop app UI for new data model
- **Updated:** API client with new endpoints

### 2025-12-21 - Environment Separation
- **Added:** Per-block locking support
- **Updated:** Lock manager to check individual blocks
- **Fixed:** Schedule vs Block terminology

### Earlier Changes
- See git log for full history
