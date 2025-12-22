# Website & Application Blocker

A robust website and application blocking system for Arch Linux + Hyprland that prevents access to distracting sites and apps during scheduled focus periods.

## Components

1. **Daemon** (Python/FastAPI) - Background service that enforces blocks
2. **Desktop App** (Python/pywebview) - GUI for configuration
3. **Browser Extension** (JavaScript) - Blocks sites and maintains heartbeat

## Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies
cd /path/to/Blocker
uv sync
```

### 2. Run the Install Script

```bash
./install.sh
```

### 3. Start the Daemon

```bash
# Enable and start the service
systemctl --user enable website-blocker
systemctl --user start website-blocker

# Check status
systemctl --user status website-blocker
```

### 4. Install Browser Extension

**Firefox:**
1. Go to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `~/.local/share/website-blocker/extension/manifest.json`
4. Go to `about:addons`, find Website Blocker, enable "Run in Private Windows"

**Chrome/Chromium:**
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `~/.local/share/website-blocker/extension/`
5. Click extension details, enable "Allow in incognito"

### 5. Launch Desktop App

```bash
uv run python desktop-app/main.py
```

## Usage

### Creating Block Rules

1. Open the desktop app
2. Go to "Block Rules"
3. Click "Add Rule"
4. Choose type (Website or Application)
5. Enter the target:
   - Websites: `reddit.com`, `*.youtube.com`, `twitter.com`
   - Applications: `steam`, `discord`, `slack`

### Creating Schedules

1. Go to "Schedules"
2. Click "Add Schedule"
3. Choose type:
   - **Time Range**: Recurring schedule (e.g., weekdays 9am-5pm)
   - **Lock Until**: One-time lock until a specific date/time
4. Select which rules to enforce
5. Enable the schedule

### Lock Mode

When a schedule is active:
- Configuration becomes read-only
- The daemon refuses to stop
- All associated rules are enforced

## API Endpoints

The daemon exposes a REST API at `http://127.0.0.1:8765`:

- `GET /api/status` - Daemon status and lock state
- `GET /api/rules` - List all rules
- `POST /api/rules` - Create a rule
- `PUT /api/rules/{id}` - Update a rule
- `DELETE /api/rules/{id}` - Delete a rule
- `GET /api/schedules` - List all schedules
- `POST /api/schedules` - Create a schedule
- `PUT /api/schedules/{id}` - Update a schedule
- `DELETE /api/schedules/{id}` - Delete a schedule
- `GET /api/stats` - Blocking statistics
- `GET /api/browsers` - Browser extension status
- `POST /api/heartbeat` - Extension heartbeat

## Files & Locations

- Config: `~/.config/website-blocker/config.json`
- Database: `~/.config/website-blocker/blocker.db`
- Logs: `~/.config/website-blocker/daemon.log`
- Extension: `~/.local/share/website-blocker/extension/`

## Debugging

```bash
# View daemon logs
journalctl --user -u website-blocker -f

# Test API
curl http://127.0.0.1:8765/api/status

# Check Hyprland windows
hyprctl clients -j | jq '.[] | select(.class | contains("firefox"))'
```

## Security Notes

- The daemon refuses SIGTERM during lock periods
- NTP time verification prevents clock manipulation
- Extension heartbeat ensures browsers have the extension active
- Fail-safe: Network/DB errors result in blocking, not allowing

Note: Determined users with root access can always bypass. This is designed for self-control, not parental controls.
