# Website & Application Blocker

A robust website and application blocking system for Arch Linux + Hyprland that prevents access to distracting sites and apps during scheduled focus periods.

**Status:** ✅ **Functional** - Core system working, see [STATUS.md](STATUS.md) for details

## Features

- **Website Blocking** - Block distracting websites with pattern matching
- **App Blocking** - Close blocked applications via Hyprland
- **Smart Scheduling** - Time-based blocking (weekdays 9-5, etc.)
- **Lock Mode** - Configuration becomes read-only during blocking periods
- **Watchdog System** - Independent processes restart daemon if killed
- **Settings Lock** - Prevent all changes for a duration (with NTP verification)
- **Safe Search Enforcement** - Force strict safe search on Google, Bing, and DuckDuckGo
- **Allow Lists** - Block sites with exceptions (e.g., block reddit except r/programming)
- **Path-Specific** - Block specific pages (e.g., youtube.com/shorts only)
- **Browser Extension** - Enforces blocks in Firefox and Chrome
- **Bypass-Resistant** - NTP verification, daemon refuses to stop during lock
- **Statistics** - Track blocks and usage patterns
- **Desktop GUI** - Easy configuration with native GTK app
- **System Tray** - Quick access menu with daemon status

## Architecture

```
┌─────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│  Desktop App    │  HTTP   │   Daemon (systemd)   │ Hyprland│   Applications  │
│  (pywebview)    │◄───────►│   - FastAPI server   │  IPC    │   & Browsers    │
│                 │         │   - Block checker    │────────►│                 │
│  - Config UI    │         │   - Lock enforcer    │         │                 │
│  - View stats   │         │   - Time verifier    │         │                 │
└─────────────────┘         └──────────┬───────────┘         └────────▲────────┘
                                       │                              │
┌─────────────────┐         ┌──────────▼────────────┐                │
│   Tray App      │         │  Browser Extension    │ Heartbeat      │
│   (pystray)     │         │  - Blocks websites    │────────────────┘
│                 │         │  - Sends pulse        │  (every 30s)
│  - Quick access │         │  - Safe search        │
│  - Status icon  │         └───────────────────────┘
└─────────────────┘
```

## Components

1. **Daemon** (Python/FastAPI) - Background service running as systemd unit
2. **Desktop App** (Python/pywebview) - GUI for configuration and monitoring
3. **Tray App** (Python/pystray) - System tray icon with quick access menu
4. **Browser Extension** (JavaScript) - Blocks sites and maintains heartbeat

## Quick Start

### 1. Install Dependencies

```bash
# Install Python with uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install system dependencies
sudo pacman -S webkit2gtk python-gobject

# Install Python dependencies
cd /path/to/Blocker
uv sync
```

### 2. Run the Install Script

```bash
./install.sh
```

This will:

- Build desktop and tray app executables to `~/.local/bin/`
- Copy daemon files to `~/.config/website-blocker/`
- Copy extension to `~/.local/share/website-blocker/extension/`
- Create systemd service file
- Set up tray app autostart (runs on login)

### 3. Start the Daemon

```bash
# Enable and start the service
systemctl --user enable website-blocker
systemctl --user start website-blocker

# Check status
systemctl --user status website-blocker

# View logs
journalctl --user -u website-blocker -f
```

### 4. Install Browser Extension

**Chrome/Chromium:**

1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `~/.local/share/website-blocker/extension/`
5. Click extension details, enable "Allow in incognito"

**Important:** Extension must be enabled in incognito/private mode!

### 5. Launch Desktop App

After installation, the tray app will start automatically on login. To launch the desktop app:

```bash
# If installed with ./install.sh --build
website-blocker

# Or run from source
uv run python desktop-app/main.py
```

The desktop app will automatically start the tray app if it's not already running.

## Usage

### Creating Blocks

Blocks group rules together and define when they're active and when configuration is locked.

1. Open the desktop app
2. Go to "Blocks" page
3. Click "Add Block"
4. Configure the block:

**Basic Settings:**

- **Name**: e.g., "Work Focus", "Study Time"
- **Enabled**: Toggle to activate/deactivate

**Block Schedule** (when content is blocked):

- **Always Block** - Block 24/7
- **Time Range** - Block during specific days/times (e.g., weekdays 9am-5pm)
- **Disabled** - Don't block (rules inactive)

**Lock Schedule** (when configuration is read-only):

- **No Lock** - Config can be changed anytime
- **Time Range** - Config locked during specific days/times
- **Locked Until** - Config locked until a specific date/time

**Blocked Content** (one entry per line):

- **Blocked Websites**:

  ```
  reddit.com
  youtube.com/shorts
  twitter.com
  ```

- **Allowed Websites** (exceptions to blocked):

  ```
  reddit.com/r/programming
  reddit.com/r/linux
  youtube.com/educational
  ```

- **Blocked Applications**:

  ```
  steam
  discord
  slack
  ```

### Pattern Matching

**Websites:**

- `reddit.com` - Blocks reddit.com and all subdomains/paths
- `youtube.com/shorts` - Blocks only YouTube Shorts (path-specific)
- `*.reddit.com` - Blocks all Reddit subdomains but not reddit.com itself
- `old.reddit.com` - Blocks only old.reddit.com

**Applications:**

- `steam` - Exact match or partial (matches "steam", "steam.exe", etc.)
- `*discord*` - Wildcard matching

### Allow List Precedence

Allow lists always take priority over block lists:

**Example:** Block all of Reddit except programming subreddits

```
Blocked Websites:
  reddit.com

Allowed Websites:
  reddit.com/r/programming
  reddit.com/r/archlinux
```

### Lock Mode

When a block's lock schedule is active:

- Configuration becomes read-only
- Cannot edit or delete the locked block
- Can still create new blocks (they have their own locks)
- Daemon refuses to stop (systemd service won't terminate)
- Lock banner shows time until unlock

### Browser Status

The "Browsers" page shows:

- ✅ Chrome - Extension active
- ❌ Firefox - Extension not detected
- ⏱️ Grace Period - 30 second window to install extensions

**Grace Period:**
Click "Add Extension" to start a 30-second grace period where browser enforcement is paused, giving you time to install the extension.

### Tray App

The tray app provides quick access to the blocker from the system tray:

- **System tray icon**: Shows blocker status at a glance
- **Quick menu**:
  - Open Desktop App - Launch the full configuration UI
  - Daemon Status - Check if daemon is running
  - Quit - Exit the tray app (daemon continues running)
- **Autostart**: Automatically starts on login via `~/.config/autostart/`

The tray app is lightweight and uses the pystray library with AppIndicator backend for Wayland/Hyprland compatibility.

### Safe Search Enforcement

The "Settings" page includes an option to enforce safe search on major search engines:

- **Google**: Automatically adds `safe=active` parameter
- **Bing**: Automatically adds `adlt=strict` parameter
- **DuckDuckGo**: Automatically adds `kp=1` parameter

When enabled:

- Search URLs are automatically modified before loading
- Works seamlessly with website blocking
- Respects settings lock (cannot be disabled when locked)
- Default: **Disabled** (opt-in feature)

This feature helps prevent unwanted content in search results without blocking the search engines entirely.

## Configuration Files

- **Config**: `~/.config/website-blocker/config.json`
- **Database**: `~/.config/website-blocker/blocker.db`
- **Watchdog State**: `~/.config/website-blocker/watchdog_state.json`
- **Extension**: `~/.local/share/website-blocker/extension/`
- **Executables**:
  - Desktop app: `~/.local/bin/website-blocker`
  - Tray app: `~/.local/bin/website-blocker-tray`
- **Autostart**: `~/.config/autostart/website-blocker-tray.desktop`
- **Icons**: `~/.local/share/website-blocker/icons/`
- **Logs**:
  - Daemon: `~/.config/website-blocker/daemon.log`
  - Watchdog: `~/.config/website-blocker/watchdog.log`
  - Systemd: `journalctl --user -u website-blocker`

## API Endpoints

The daemon exposes a REST API at `http://127.0.0.1:8765`:

### Status & Info

- `GET /api/status` - Daemon status and lock state
- `GET /api/stats` - Blocking statistics
- `GET /api/browsers` - Browser extension status

### Blocks

- `GET /api/blocks` - List all blocks
- `POST /api/blocks` - Create a block
- `PUT /api/blocks/{id}` - Update a block
- `DELETE /api/blocks/{id}` - Delete a block
- `GET /api/blocks/{id}/lock-status` - Check if block is locked

### Extension

- `POST /api/heartbeat` - Extension heartbeat
- `GET /api/grace-period` - Grace period status
- `POST /api/grace-period` - Start grace period

### Settings

- `GET /api/settings/browser-enforcement` - Browser enforcement status
- `PUT /api/settings/browser-enforcement` - Toggle browser enforcement
- `GET /api/settings/safe-search` - Safe search enforcement status
- `PUT /api/settings/safe-search` - Toggle safe search enforcement
- `GET /api/settings/watchdog` - Watchdog status
- `PUT /api/settings/watchdog` - Enable/disable watchdog
- `GET /api/settings/lock` - Settings lock status
- `POST /api/settings/lock` - Lock settings until datetime
- `DELETE /api/settings/lock` - Unlock settings

## Debugging

### Check Daemon Status

```bash
# Service status
systemctl --user status website-blocker

# View logs
journalctl --user -u website-blocker -f

# Test API
curl http://127.0.0.1:8765/api/status | python3 -m json.tool
```

### Check Blocks

```bash
# List all blocks
curl http://127.0.0.1:8765/api/blocks | python3 -m json.tool

# Check browser status
curl http://127.0.0.1:8765/api/browsers | python3 -m json.tool
```

### Check Hyprland Windows

```bash
# List all windows
hyprctl clients -j | jq '.[] | {class, pid, title}'

# Find browser windows
hyprctl clients -j | jq '.[] | select(.class | contains("firefox"))'
```

### Common Issues

**Daemon won't start:**

```bash
# Check logs for errors
journalctl --user -u website-blocker -n 50 --no-pager

# Verify port is available
ss -tulpn | grep 8765

# Test database
sqlite3 ~/.config/website-blocker/blocker.db ".tables"
```

**Extension not working:**

```bash
# Check if extension is loaded
# Firefox: about:debugging
# Chrome: chrome://extensions/

# Verify extension can reach daemon
# Open browser console (F12) and look for errors

# Check heartbeat is being received
curl http://127.0.0.1:8765/api/browsers
```

**Sites not blocked:**

```bash
# Check if block is active
curl http://127.0.0.1:8765/api/blocks | jq '.[] | select(.enabled == true)'

# Verify block schedule
# Check block_mode and time ranges

# Test pattern matching
# Make sure URL pattern matches correctly
```

## Security Notes

### Bypass Resistance

- **Watchdog System**: Independent processes restart daemon if killed (see [WATCHDOG.md](WATCHDOG.md))
- **Settings Lock**: Prevents all configuration changes until expiry (NTP-verified)
- **Daemon Protection**: Refuses SIGTERM during lock, auto-restarts via systemd
- **Extension Heartbeat**: Browser closes if extension stops (60s timeout)
- **Safe Search Enforcement**: Automatically adds safe search parameters to Google, Bing, and DuckDuckGo
- **Time Verification**: NTP check prevents clock manipulation
- **Lock Mode**: Configuration frozen during blocking periods
- **Fail-Safe**: Network/DB errors result in blocking (not allowing)

**Watchdog Features:**

- 2-5 configurable watchdog processes (default 3)
- Obfuscated process names (blend in with system processes)
- Self-perpetuating (watchdogs monitor and respawn each other)
- Automatically restart daemon via systemctl
- Respect settings lock (continue protecting even during shutdown attempts)

See [WATCHDOG.md](WATCHDOG.md) for detailed documentation.

### Limitations

**This is designed for self-control, not parental controls.**

Determined users with system access can bypass:

- `pkill -9 python` - Kills daemon, watchdogs, and desktop app
- `sudo systemctl disable website-blocker` - Prevents auto-start
- Changing system time (detected via NTP when network available)
- Editing database directly (when not locked)
- Disabling extension (browser gets killed)
- Boot into recovery mode

**However, the watchdog system makes impulsive bypasses harder:**

- Requires finding and killing multiple obfuscated processes
- Settings lock prevents easy disabling via UI/API
- Provides time to reconsider before succeeding

For a more secure solution, consider:

1. Network-level blocking (router/firewall)
2. Separate user account with restricted permissions
3. Rust rewrite (harder to bypass than Python)
4. Kernel module (but complex to maintain)

## Project Structure

```
Blocker/
├── daemon/              # Python daemon
│   ├── main.py          # Entry point
│   ├── api/             # REST API package
│   │   ├── __init__.py  # App creation and router wiring
│   │   ├── app.py       # FastAPI app setup
│   │   ├── deps.py      # Shared dependencies
│   │   ├── schemas.py   # Pydantic models
│   │   └── routes/      # API route handlers
│   │       ├── blocks.py
│   │       ├── heartbeat.py
│   │       ├── settings.py
│   │       └── status.py
│   ├── blocker.py       # Blocking logic
│   ├── scheduler.py     # Schedule checking
│   ├── watchdog.py      # Watchdog manager
│   ├── watchdog_runner.py  # Watchdog process entry point
│   ├── database.py      # SQLAlchemy models
│   ├── migrations.py    # Database migrations
│   ├── hyprland_monitor.py  # Window monitoring
│   ├── heartbeat_tracker.py  # Browser compliance
│   ├── lock_manager.py  # Lock enforcement
│   ├── time_verifier.py # NTP verification
│   └── config.py        # Configuration management
├── desktop-app/         # Python + pywebview GUI
│   ├── main.py          # Entry point
│   ├── api_client.py    # Daemon API client
│   ├── frontend/        # React + TypeScript (Vite)
│   └── desktop-app.spec # PyInstaller spec
├── tray/                # System tray app
│   ├── main.py          # Entry point
│   └── tray-app.spec    # PyInstaller spec
├── extension/           # Browser extension
│   ├── manifest.json
│   ├── background.js
│   ├── blocked.html
│   ├── popup/           # Extension popup UI
│   └── native-host/     # Native messaging host
│       └── host.py
├── icons/               # App icons
│   ├── icon-desktop-*.png
│   └── icon-tray-*.png
├── config/              # Configuration templates
├── install.sh           # Installation script
├── reinstall.sh         # Development reinstall script
├── CLAUDE.md            # Technical reference for Claude
├── README.md            # This file
└── documentation/       # Additional documentation
```

## Development

### Running from Source

```bash
# Start daemon in foreground (for debugging)
cd daemon
uv run python main.py

# Start desktop app
cd desktop-app
uv run python main.py

# Start tray app
cd tray
uv run python main.py

# Load extension in browser
# Firefox: about:debugging
# Chrome: chrome://extensions
```

### Building Executables

```bash
# Build both desktop and tray apps
./install.sh --build

# Executables will be created in:
# - ~/.local/bin/website-blocker (desktop app)
# - ~/.local/bin/website-blocker-tray (tray app)
```

### Database Migrations

Migrations run automatically on daemon startup. To manually inspect:

```bash
# Open database
sqlite3 ~/.config/website-blocker/blocker.db

# List tables
.tables

# View blocks
SELECT * FROM blocks;

# View schema
.schema blocks
```

## Future Enhancements

See [STATUS.md](STATUS.md) for current priorities.

**Planned:**

- Break intervals (5 minutes every hour)
- Usage limits (block after X minutes total)
- Site categories (Social, News, Gaming)
- Import/export configurations
- Better statistics dashboard
- Mobile companion app

**Maybe:**

- Rust rewrite for better security
- Multi-device sync
- Accountability partner features
- Browser history analysis

## Contributing

This is a personal project, but bug reports and feature requests are welcome:

1. Check [STATUS.md](STATUS.md) for known issues
2. Search existing issues
3. Create detailed bug report with logs
4. Pull requests welcome for bug fixes

## License

MIT License - See LICENSE file for details

## Acknowledgments

Built for personal use on Arch Linux + Hyprland. Inspired by various website blockers but designed specifically for tiling window managers and strict enforcement.

## Links

- Project Status: [STATUS.md](STATUS.md)
- Full Specification: [PROJECT_SPEC.md](PROJECT_SPEC.md)
- Watchdog Documentation: [WATCHDOG.md](WATCHDOG.md)
- Installation Guide: See "Quick Start" above

---

**Remember:** This tool is meant to help you, not to punish you. Use it wisely and adjust your blocks as needed. The goal is productivity, not suffering! 🚀
