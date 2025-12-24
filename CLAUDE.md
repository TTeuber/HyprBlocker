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

- `main.py` - Entry point, systemd integration, signal handling
- `api.py` - 26 REST API endpoints
- `blocker.py` - Pattern matching for websites/apps
- `scheduler.py` - Block schedule checking and activation
- `hyprland_monitor.py` - Window monitoring and app closing via Hyprland IPC
- `heartbeat_tracker.py` - Browser compliance tracking
- `lock_manager.py` - Lock mode enforcement
- `time_verifier.py` - NTP time verification
- `database.py` - SQLAlchemy ORM models
- `config.py` - Configuration management
- `migrations.py` - Database migration logic

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

| Endpoint                       | Method     | Purpose                                  |
| ------------------------------ | ---------- | ---------------------------------------- |
| `/api/status`                  | GET        | Daemon status, active blocks, lock state |
| `/api/blocks`                  | GET/POST   | List/create blocks                       |
| `/api/blocks/{id}`             | PUT/DELETE | Update/delete block                      |
| `/api/blocks/{id}/lock-status` | GET        | Check if block is locked                 |
| `/api/stats`                   | GET        | Blocking statistics                      |
| `/api/browsers`                | GET        | Browser extension status                 |
| `/api/heartbeat`               | POST       | Browser extension heartbeat              |
| `/api/grace-period`            | GET/POST   | Grace period for extension setup         |
| `/api/blocked-sites`           | GET        | Current blocked patterns (for extension) |
| `/api/settings/dev-mode`       | GET/PUT    | Dev mode toggle                          |

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

- **Lock mode**: Prevents configuration changes when active
- **Signal handling**: Daemon refuses SIGTERM during lock
- **NTP verification**: Prevents clock manipulation
- **Fail-safe design**: Errors result in blocking (not allowing)
- **Browser enforcement**: Force-close browsers if extension stops responding
- **Incognito detection**: Extension reports incognito status

## Data Flow

1. **Configuration**: Desktop App → POST /api/blocks → SQLite
2. **Schedule checking**: Daemon polls every 10s, activates blocks
3. **Browser monitoring**: Extension → POST /api/heartbeat every 30s
4. **Blocking enforcement**:
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
- Systemd: `~/.config/systemd/user/website-blocker.service`
- Native messaging: `~/.config/chromium/NativeMessagingHosts/com.websiteblocker.host.json`

## Design Principles

- **Daemon is source of truth**: All enforcement server-side
- **Extension is untrusted**: Browsers killed if extension stops
- **Fail-safe**: When in doubt, block (not allow)
- **Self-control focused**: Not designed as parental controls

## Notes from Developer

- This app is in early development, don't worry about backwards compatibility
- If there are any changes to the structure of this app like adding/removing files or changing the database model, please update CLAUDE.md with those changes
