# Website & Application Blocker

A robust website and application blocking system for Arch Linux + Hyprland that prevents access to distracting sites and apps during scheduled focus periods.

**Status:** ✅ **Functional** - Core system working, see [STATUS.md](STATUS.md) for details

## Features

- 🚫 **Website Blocking** - Block distracting websites with pattern matching
- 📱 **App Blocking** - Close blocked applications via Hyprland
- ⏰ **Smart Scheduling** - Time-based blocking (weekdays 9-5, etc.)
- 🔒 **Lock Mode** - Configuration becomes read-only during blocking periods
- ✅ **Allow Lists** - Block sites with exceptions (e.g., block reddit except r/programming)
- 🎯 **Path-Specific** - Block specific pages (e.g., youtube.com/shorts only)
- 🌐 **Browser Extension** - Enforces blocks in Firefox and Chrome
- 💪 **Bypass-Resistant** - NTP verification, daemon refuses to stop during lock
- 📊 **Statistics** - Track blocks and usage patterns
- 🖥️ **Desktop GUI** - Easy configuration with native GTK app

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
                            ┌──────────▼────────────┐                │
                            │  Browser Extension    │ Heartbeat      │
                            │  - Blocks websites    │────────────────┘
                            │  - Sends pulse        │  (every 30s)
                            └───────────────────────┘
```

## Components

1. **Daemon** (Python/FastAPI) - Background service running as systemd unit
2. **Desktop App** (Python/pywebview) - GUI for configuration and monitoring
3. **Browser Extension** (JavaScript) - Blocks sites and maintains heartbeat

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
- Copy daemon files to `~/.config/website-blocker/`
- Copy extension to `~/.local/share/website-blocker/extension/`
- Create systemd service file

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

#### Firefox:
1. Go to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `~/.local/share/website-blocker/extension/manifest.json`
4. Go to `about:addons`, find Website Blocker, enable "Run in Private Windows"

#### Chrome/Chromium:
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `~/.local/share/website-blocker/extension/`
5. Click extension details, enable "Allow in incognito"

**Important:** Extension must be enabled in incognito/private mode!

### 5. Launch Desktop App

```bash
uv run python desktop-app/main.py
```

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

- **Allowed Applications** (exceptions):
  ```
  discord-work
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
- ✅ Firefox - Extension active
- ❌ Chrome - Extension not detected
- ⏱️ Grace Period - 30 second window to install extensions

**Grace Period:**
Click "Add Extension" to start a 30-second grace period where browser enforcement is paused, giving you time to install the extension.

## Configuration Files

- **Config**: `~/.config/website-blocker/config.json`
- **Database**: `~/.config/website-blocker/blocker.db`
- **Extension**: `~/.local/share/website-blocker/extension/`
- **Logs**: `journalctl --user -u website-blocker`

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
- **Daemon Protection**: Refuses SIGTERM during lock, auto-restarts via systemd
- **Extension Heartbeat**: Browser closes if extension stops (60s timeout)
- **Time Verification**: NTP check prevents clock manipulation
- **Lock Mode**: Configuration frozen during blocking periods
- **Fail-Safe**: Network/DB errors result in blocking (not allowing)

### Limitations
**This is designed for self-control, not parental controls.**

Determined users with root access can bypass:
- `sudo systemctl stop website-blocker` (when not locked)
- `sudo killall python` (crude but effective)
- Changing system time (detected via NTP when network available)
- Editing database directly (when not locked)
- Disabling extension (browser gets killed)

For a more secure solution, consider:
1. Rust rewrite (harder to bypass than Python)
2. Kernel module (but complex to maintain)
3. Network-level blocking (router/firewall)

## Project Structure

```
Blocker/
├── daemon/              # Python daemon
│   ├── main.py          # Entry point
│   ├── api.py           # REST API
│   ├── blocker.py       # Blocking logic
│   ├── scheduler.py     # Schedule checking
│   ├── database.py      # SQLAlchemy models
│   ├── migrations.py    # Database migrations
│   └── ...
├── desktop-app/         # Python + pywebview GUI
│   ├── main.py          # Entry point
│   ├── api_client.py    # Daemon API client
│   └── web/             # HTML/CSS/JS frontend
├── extension/           # Browser extension
│   ├── manifest.json
│   ├── background.js
│   └── ...
├── config/              # Configuration templates
├── install.sh           # Installation script
├── README.md            # This file
├── STATUS.md            # Current project status
└── PROJECT_SPEC.md      # Original specification
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

# Load extension in browser
# Firefox: about:debugging
# Chrome: chrome://extensions
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
- Installation Guide: See "Quick Start" above

---

**Remember:** This tool is meant to help you, not to punish you. Use it wisely and adjust your blocks as needed. The goal is productivity, not suffering! 🚀
