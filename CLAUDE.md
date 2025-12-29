# Website Blocker - Technical Reference for Claude

## Architecture Overview

Three main components:

1. **Daemon** (daemon/) - FastAPI server, port 8765, systemd service
2. **Desktop App** (desktop-app/) - PyWebView GUI with React frontend
3. **Browser Extension** (extension/) - WebExtensions API (Manifest v3)

```
Desktop App + Browser Extension
       ↓ HTTP API (localhost:8765)
    Daemon (FastAPI)
       ↓ SQLite + Hyprland IPC
   Database + Window Manager
```

## Key Files & Modules

### Daemon (daemon/)

- `main.py` - Entry point, systemd integration, signal handling, watchdog spawning
- `api/` - REST API package
  - `__init__.py` - App creation and router wiring
  - `app.py` - FastAPI app setup with CORS
  - `deps.py` - Shared dependencies (session factory, lock checks)
  - `schemas.py` - Pydantic request/response models
  - `routes/` - API route handlers
    - `heartbeat.py` - `/api/heartbeat`, `/api/grace-period`
    - `blocks.py` - `/api/blocks` CRUD
    - `status.py` - `/api/status`, `/api/stats`, `/api/browsers`, `/api/blocked-sites`
    - `settings.py` - `/api/settings/*` endpoints
- `blocker.py` - Pattern matching for websites/apps
- `scheduler.py` - Block schedule checking and activation
- `hyprland_monitor.py` - Window monitoring and app closing via Hyprland IPC
- `heartbeat_tracker.py` - Browser compliance tracking
- `lock_manager.py` - Per-block lock mode enforcement
- `time_verifier.py` - NTP time verification
- `database.py` - SQLAlchemy ORM models
- `config.py` - Configuration management
- `migrations.py` - Database migration logic
- `watchdog.py` - Watchdog manager and process logic
- `watchdog_runner.py` - Standalone watchdog process entry point

### Desktop App (desktop-app/)

- `main.py` - PyWebView window + JS bridge
- `api_client.py` - HTTP client for daemon API
- `frontend/` - React + TypeScript (Vite build)

### Browser Extension (extension/)

- `background.js` - Service worker (heartbeat, blocking)
- `blocked.html` - Blocked page display
- `popup/` - Extension popup UI
- `native-host/host.py` - Native messaging for PID detection

## Database Schema

Location: `~/.config/website-blocker/blocker.db`

### blocks table

```sql
id INTEGER PRIMARY KEY
name TEXT NOT NULL
enabled BOOLEAN DEFAULT true

-- Block schedule
block_mode TEXT CHECK(block_mode IN ('always', 'time_range', 'disabled'))
block_days_of_week TEXT  -- JSON array [0-6], Monday=0
block_start_time TIME
block_end_time TIME

-- Lock schedule (per-block)
lock_mode TEXT CHECK(lock_mode IN ('none', 'time_range', 'locked_until'))
lock_days_of_week TEXT
lock_start_time TIME
lock_end_time TIME
lock_until DATETIME

-- Rules (newline-separated text)
websites_blocked TEXT
websites_allowed TEXT
apps_blocked TEXT
apps_allowed TEXT
```

### block_events table

```sql
id INTEGER PRIMARY KEY
blocked_target TEXT
timestamp DATETIME
event_type TEXT
```

### heartbeat_logs table

```sql
id INTEGER PRIMARY KEY
browser_pid INTEGER
browser_name TEXT
incognito BOOLEAN
incognito_enabled BOOLEAN
timestamp DATETIME
```

## Key API Endpoints

| Endpoint                       | Method         | Purpose                                  |
| ------------------------------ | -------------- | ---------------------------------------- |
| `/api/status`                  | GET            | Daemon status, active blocks             |
| `/api/blocks`                  | GET/POST       | List/create blocks                       |
| `/api/blocks/{id}`             | PUT/DELETE     | Update/delete block                      |
| `/api/blocks/{id}/lock-status` | GET            | Check if block is locked                 |
| `/api/stats`                   | GET            | Blocking statistics                      |
| `/api/browsers`                | GET            | Browser extension status                 |
| `/api/heartbeat`               | POST           | Browser extension heartbeat              |
| `/api/grace-period`            | GET/POST       | Grace period for extension setup         |
| `/api/blocked-sites`           | GET            | Current blocked patterns (for extension) |
| `/api/settings/browser-enforcement` | GET/PUT   | Browser enforcement toggle               |
| `/api/settings/safe-search`    | GET/PUT        | Safe search enforcement toggle           |
| `/api/settings/shutdown-prevention` | GET/PUT   | Shutdown prevention toggle               |
| `/api/settings/watchdog`       | GET/PUT        | Watchdog enable/disable, count           |
| `/api/settings/lock`           | GET/POST/DELETE| Settings lock (lock-until with NTP)      |

## Data Model

### Rules Storage

- **Text-based**: Newline-separated strings in blocks table
- **Four rule types**: websites_blocked, websites_allowed, apps_blocked, apps_allowed
- **Allow list precedence**: Allow lists override block lists

### Website Patterns

- Domain: `youtube.com`
- Subdomain: `www.youtube.com` (matches when blocking `youtube.com`)
- Wildcard: `*.reddit.com`
- Path-specific: `youtube.com/shorts`

### App Patterns

- Window class matching via Hyprland IPC
- Partial matching: `steam` matches `steam_app_123456`

## Monitoring Intervals

- Schedule checking: Every 10 seconds
- Window monitoring: Every 5 seconds
- Browser heartbeat timeout: 60 seconds
- Extension heartbeat send: Every 30 seconds
- Grace period: 30 seconds (for extension installation)

## Security Features

- **Per-block lock mode**: Prevents modifications to a specific block when active
- **Settings lock**: Prevents all settings changes until expiry (with NTP verification)
- **Shutdown prevention**: Daemon refuses SIGTERM signals when enabled
- **NTP verification**: Prevents clock manipulation
- **Fail-safe design**: Errors result in blocking (not allowing)
- **Browser enforcement**: Force-close browsers if extension stops responding
- **Safe search enforcement**: Forces strict safe search on Google, Bing, and DuckDuckGo
- **Incognito detection**: Extension reports incognito status
- **Watchdog system**: Independent processes restart daemon if killed (requires shutdown prevention)

## Safe Search Enforcement

The safe search enforcement feature automatically modifies search engine URLs to enable strict safe search mode.

### How it works

1. Daemon stores `safe_search_enabled` boolean in config (`config.py`)
2. `/api/blocked-sites` endpoint includes `safe_search_enabled` in response
3. Extension stores setting and applies it before blocking check
4. When user navigates to a search engine, extension checks and modifies URL if needed

### Search Engine Parameters

| Engine | Detection | Parameter | Value |
|--------|-----------|-----------|-------|
| Google | `google.*` + `/search` path | `safe` | `active` |
| Bing | `bing.com` + `/search` path | `adlt` | `strict` |
| DuckDuckGo | `duckduckgo.com` (any path) | `kp` | `1` |

### Implementation (extension/background.js)

```javascript
function enforceSafeSearch(url) {
    const urlObj = new URL(url);

    // Check if parameter already set
    if (urlObj.searchParams.get('safe') === 'active') return { redirect: false };

    // Add parameter and redirect
    urlObj.searchParams.set('safe', 'active');
    return { redirect: true, newUrl: urlObj.toString() };
}
```

### Integration with blocking

Safe search enforcement runs **before** blocking logic in `handleNavigationBlock()`:
1. Check if safe search is enabled
2. If enabled, enforce safe search parameters
3. If redirect needed, stop processing (don't check for blocks)
4. Otherwise, continue with normal blocking logic

This ensures search engines are accessible but with safe search enforced.

## Watchdog System

The watchdog system provides daemon resilience by spawning independent processes that monitor the daemon and each other.

### How it works

1. Watchdog requires **both** shutdown prevention AND watchdog to be enabled
2. When enabled, daemon spawns N watchdog processes (configurable 2-5, default 3)
3. Each watchdog monitors:
   - Daemon health (HTTP check every 5 seconds)
   - Sibling watchdog processes (PID check every 10 seconds)
4. If daemon dies → watchdog restarts via `systemctl --user restart website-blocker`
5. If sibling dies → remaining watchdogs respawn it
6. Watchdogs use obfuscated process names for resilience

### State File

Location: `~/.config/website-blocker/watchdog_state.json`

```json
{
  "enabled": true,
  "watchdog_count": 3,
  "watchdogs": [
    {"pid": 12345, "name": "kworker-7", "started": "...", "last_heartbeat": "..."}
  ],
  "daemon_pid": 12340,
  "shutdown_requested": false
}
```

### Shutdown Prevention Integration

- Watchdog toggle is disabled in UI if shutdown prevention is off
- Disabling shutdown prevention automatically disables watchdog
- When settings are locked, both toggles cannot be changed
- This pairing ensures watchdogs only run when daemon shutdown protection is needed

## Data Flow

1. **Configuration**: Desktop App → POST /api/blocks → SQLite
2. **Schedule checking**: Daemon polls every 10s, activates blocks
3. **Browser monitoring**: Extension → POST /api/heartbeat every 30s
4. **Blocking enforcement**:
   - Extension enforces safe search (if enabled) via URL parameter injection
   - Extension blocks in-browser via webNavigation API
   - Daemon closes non-compliant browsers via Hyprland IPC
5. **App blocking**: Daemon → Hyprland IPC → Close windows

## Native Messaging

- **Purpose**: Get real browser PID (not extension process PID)
- **Protocol**: Stdin/stdout JSON messages
- **Host location**: `~/.config/chromium/NativeMessagingHosts/com.websiteblocker.host.json`
- **Host script**: `extension/native-host/host.py`
- **Permissions**: nativeMessaging in manifest.json

## Configuration Files

- Config: `~/.config/website-blocker/config.json`
- Database: `~/.config/website-blocker/blocker.db`
- Watchdog state: `~/.config/website-blocker/watchdog_state.json`
- Daemon log: `~/.config/website-blocker/daemon.log`
- Watchdog log: `~/.config/website-blocker/watchdog.log`
- Systemd: `~/.config/systemd/user/website-blocker.service`
- Native messaging: `~/.config/chromium/NativeMessagingHosts/com.websiteblocker.host.json`

### Config Fields (config.json security section)

```json
{
  "security": {
    "browser_enforcement_enabled": true,
    "safe_search_enabled": false,
    "shutdown_prevention_enabled": false,
    "watchdog_enabled": false,
    "watchdog_count": 3,
    "settings_lock_until": null
  }
}
```

## Design Principles

- **Daemon is source of truth**: All enforcement server-side
- **Extension is untrusted**: Browsers killed if extension stops
- **Fail-safe**: When in doubt, block (not allow)
- **Self-control focused**: Not designed as parental controls

## Notes from Developer

- This app is in early development, don't worry about backwards compatibility
- If there are any changes to the structure of this app like adding/removing files or changing the database model, please update CLAUDE.md with those changes
