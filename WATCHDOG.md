# Watchdog System Documentation

The watchdog system makes the daemon harder to disable by spawning independent processes that monitor and restart the daemon if it's killed.

## Overview

When enabled, the daemon spawns multiple watchdog processes that:
- Monitor the daemon's health via HTTP checks
- Monitor each other to ensure resilience
- Restart the daemon if it dies
- Respawn dead sibling watchdogs
- Use obfuscated process names to avoid detection

## How It Works

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Watchdog 1 │◄───►│  Watchdog 2 │◄───►│  Watchdog 3 │
│ "kworker/7" │     │ "gsd-color" │     │ "update-mgr"│
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Daemon    │
                    │  (FastAPI)  │
                    │  Port 8765  │
                    └─────────────┘
```

### Monitoring Loop

Each watchdog runs independently and performs these checks:

**Every 5 seconds:**
- HTTP GET to `http://127.0.0.1:8765/api/status`
- If 3 consecutive failures → restart daemon via `systemctl --user restart website-blocker`

**Every 10 seconds:**
- Check sibling watchdog PIDs with `kill -0 <pid>`
- If sibling is dead → fork a new replacement watchdog

**Every 30 seconds:**
- Update own heartbeat in `watchdog_state.json`
- Clean up stale entries (no heartbeat > 60s)
- Check settings lock status via NTP-verified time

### Process Obfuscation

Watchdogs use obfuscated process names to blend in with system processes:

**System-like names:**
- `kworker/7`, `ksoftirqd/2`, `migration/1`
- `systemd-helper`, `dbus-daemon`, `gdbus`

**Common app names:**
- `update-notifier`, `gsd-color`, `gsd-power`
- `at-spi-bus`, `ibus-daemon`, `pipewire`

**Random strings:**
- 8-character lowercase alphanumeric strings

The process name is set using Linux `prctl(PR_SET_NAME)`, making it visible in `ps`, `top`, and `htop`.

## Configuration

### Enabling Watchdogs

**Via Desktop UI:**
1. Go to Settings page
2. Enable "Watchdog Protection" checkbox
3. Select number of watchdogs (2-5, default 3)

**Via API:**
```bash
# Enable with 3 watchdogs
curl -X PUT http://127.0.0.1:8765/api/settings/watchdog \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "count": 3}'

# Check status
curl http://127.0.0.1:8765/api/settings/watchdog | python3 -m json.tool
```

**Via Config File:**
Edit `~/.config/website-blocker/config.json`:
```json
{
  "security": {
    "watchdog_enabled": true,
    "watchdog_count": 3
  }
}
```
Then restart daemon: `systemctl --user restart website-blocker`

### Settings Lock Integration

When settings are locked:
- Watchdogs ignore shutdown signals
- Watchdogs continue restarting daemon even if user tries to stop it
- Lock status verified via NTP to prevent clock manipulation

To lock settings for 4 hours:
```bash
# Calculate lock_until (4 hours from now)
LOCK_UNTIL=$(date -u -d "+4 hours" --iso-8601=seconds)

# Lock settings
curl -X POST http://127.0.0.1:8765/api/settings/lock \
  -H "Content-Type: application/json" \
  -d "{\"lock_until\": \"$LOCK_UNTIL\"}"
```

## State Files

### Watchdog State File

Location: `~/.config/website-blocker/watchdog_state.json`

```json
{
  "enabled": true,
  "watchdog_count": 3,
  "watchdogs": [
    {
      "pid": 12345,
      "name": "kworker/7",
      "started": "2025-12-28T10:30:00.000000+00:00",
      "last_heartbeat": "2025-12-28T10:35:23.000000+00:00"
    },
    {
      "pid": 12346,
      "name": "gsd-color",
      "started": "2025-12-28T10:30:00.000000+00:00",
      "last_heartbeat": "2025-12-28T10:35:24.000000+00:00"
    },
    {
      "pid": 12347,
      "name": "update-notifier",
      "started": "2025-12-28T10:30:00.000000+00:00",
      "last_heartbeat": "2025-12-28T10:35:22.000000+00:00"
    }
  ],
  "daemon_pid": 12340,
  "shutdown_requested": false
}
```

This file is used for:
- Coordination between watchdog processes
- Tracking active watchdogs
- Signaling shutdown when watchdogs should exit

### Logs

**Daemon logs:** `~/.config/website-blocker/daemon.log`
```
2025-12-28 10:30:00 - INFO - Spawned 3 watchdog processes: [12345, 12346, 12347]
2025-12-28 10:30:00 - INFO - Watchdog 1/3: PID 12345, name 'kworker/7'
```

**Watchdog logs:** `~/.config/website-blocker/watchdog.log`
```
2025-12-28 10:30:01 - INFO - Watchdog started: name=kworker/7, pid=12345
2025-12-28 10:35:00 - ERROR - Daemon unresponsive, restarting...
2025-12-28 10:35:01 - INFO - Daemon restarted successfully
2025-12-28 10:40:15 - WARNING - Sibling 12346 is dead
2025-12-28 10:40:15 - INFO - Respawned sibling: PID 12350, name 'gsd-power'
```

## Monitoring Watchdogs

### Check Active Watchdogs

**Via Desktop UI:**
- Go to Settings page
- Watchdog Protection card shows active watchdogs with PIDs and uptime

**Via API:**
```bash
curl http://127.0.0.1:8765/api/settings/watchdog | python3 -m json.tool
```

Output:
```json
{
  "enabled": true,
  "count": 3,
  "active_watchdogs": [
    {
      "pid": 12345,
      "name": "kworker/7",
      "uptime_seconds": 315
    },
    {
      "pid": 12346,
      "name": "gsd-color",
      "uptime_seconds": 315
    },
    {
      "pid": 12347,
      "name": "update-notifier",
      "uptime_seconds": 315
    }
  ]
}
```

**Via Process List:**
```bash
# Look for obfuscated names
ps aux | grep -E "kworker|gsd-|update-notifier|at-spi|ibus"

# More targeted search
ps -eo pid,comm,cmd | grep python | grep watchdog_runner
```

### Tail Logs
```bash
# Watch watchdog activity
tail -f ~/.config/website-blocker/watchdog.log

# Watch daemon logs (includes watchdog spawning)
tail -f ~/.config/website-blocker/daemon.log
```

## Disabling Watchdogs

### Clean Shutdown (Settings Not Locked)

**Via Desktop UI:**
1. Go to Settings page
2. Uncheck "Enable watchdog processes"
3. Watchdogs will exit gracefully

**Via API:**
```bash
curl -X PUT http://127.0.0.1:8765/api/settings/watchdog \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Via Config File:**
```json
{
  "security": {
    "watchdog_enabled": false
  }
}
```
Then restart daemon.

### Force Kill (Settings Locked)

If settings are locked and watchdogs are protecting the daemon:

```bash
# Find watchdog PIDs
ps aux | grep watchdog_runner

# Kill each watchdog (they'll respawn)
kill <pid1> <pid2> <pid3>

# Kill all Python processes (crude but effective)
pkill -9 python

# Wait for settings lock to expire, then disable normally
```

**Note:** If settings are locked, watchdogs will continue restarting themselves and the daemon until the lock expires.

## Troubleshooting

### Watchdogs Not Spawning

**Check logs:**
```bash
tail -n 50 ~/.config/website-blocker/daemon.log | grep -i watchdog
```

**Common issues:**
- Watchdog setting not enabled in config
- Python not in PATH
- Permissions issues with state file
- watchdog_runner.py missing

### Daemon Keeps Restarting

This is **expected behavior** when:
- Watchdogs are enabled
- You try to stop the daemon
- Settings are locked

**To actually stop it:**
1. Wait for settings lock to expire (check Settings page)
2. Disable watchdogs via UI
3. Stop daemon: `systemctl --user stop website-blocker`

### Watchdog Not Restarting Daemon

**Check watchdog logs:**
```bash
tail -n 50 ~/.config/website-blocker/watchdog.log
```

**Possible causes:**
- systemctl not in PATH
- User systemd not running
- Daemon service file missing
- Network issue preventing HTTP checks

### Too Many Watchdogs

If you see more watchdogs than configured:
```bash
# Count watchdog processes
ps aux | grep watchdog_runner | wc -l

# Kill extras
pkill -f watchdog_runner

# Restart daemon cleanly
systemctl --user restart website-blocker
```

## Security Considerations

### Resilience Level

The watchdog system provides **strong resilience** for self-control:
- Survives `systemctl stop` when settings locked
- Survives individual watchdog kills (siblings respawn)
- Obfuscated names make watchdogs harder to identify
- Settings lock prevents disabling via UI/API

### Bypass Methods

Users with system access can still bypass:

**Kill all Python processes:**
```bash
pkill -9 python  # Kills daemon + watchdogs + desktop app
```

**Disable systemd service:**
```bash
systemctl --user disable website-blocker
systemctl --user stop website-blocker
pkill -9 python
```

**Edit config directly:**
```bash
# When settings not locked
nano ~/.config/website-blocker/config.json
# Set watchdog_enabled: false
systemctl --user restart website-blocker
```

**Boot into recovery mode:**
- Remove systemd service file
- Reboot normally

### Design Philosophy

This system is designed for **self-control**, not parental controls:
- Makes impulsive bypasses harder
- Provides time to reconsider
- Respects user's ultimate authority over their system
- Helps build discipline through friction, not absolute prevention

For stronger security, consider:
- Network-level blocking (router/firewall)
- Separate user account with restricted permissions
- Trusted friend managing the configuration
- Physical time-lock boxes for keyboard

## API Reference

### GET /api/settings/watchdog

Get current watchdog status.

**Response:**
```json
{
  "enabled": true,
  "count": 3,
  "active_watchdogs": [
    {"pid": 12345, "name": "kworker/7", "uptime_seconds": 315}
  ]
}
```

### PUT /api/settings/watchdog

Update watchdog settings.

**Request:**
```json
{
  "enabled": true,
  "count": 3
}
```

**Response:**
```json
{
  "success": true,
  "enabled": true,
  "count": 3
}
```

**Errors:**
- `403` - Settings are locked
- `400` - Invalid count (must be 2-5)

### GET /api/settings/lock

Get settings lock status.

**Response:**
```json
{
  "locked": true,
  "lock_until": "2025-12-28T14:30:00+00:00",
  "remaining_seconds": 3600
}
```

### POST /api/settings/lock

Lock settings until a specific datetime.

**Request:**
```json
{
  "lock_until": "2025-12-28T14:30:00+00:00"
}
```

**Response:**
```json
{
  "success": true,
  "lock_until": "2025-12-28T14:30:00+00:00"
}
```

**Errors:**
- `403` - System time manipulation detected
- `400` - Invalid datetime or time in past

### DELETE /api/settings/lock

Unlock settings (only works if lock has expired).

**Response:**
```json
{
  "success": true
}
```

**Errors:**
- `403` - Settings still locked (hasn't expired yet)

## Best Practices

### Recommended Configuration

For moderate self-control:
```json
{
  "security": {
    "watchdog_enabled": true,
    "watchdog_count": 3
  }
}
```

For maximum resilience:
```json
{
  "security": {
    "watchdog_enabled": true,
    "watchdog_count": 5,
    "settings_lock_until": "2025-12-28T18:00:00+00:00"
  }
}
```

### Usage Tips

1. **Start with lock periods you can handle** - Don't lock yourself out for days at first
2. **Test watchdogs before relying on them** - Make sure they restart the daemon correctly
3. **Keep logs accessible** - Helps debug issues during lock periods
4. **Have an escape plan** - Remember you can always boot into recovery mode if needed
5. **Combine with other techniques** - Watchdogs work best alongside other productivity strategies

### Common Workflows

**Deep work session (4 hours):**
1. Enable watchdogs
2. Lock settings for 4 hours
3. Watchdogs ensure daemon stays running
4. Automatic unlock after 4 hours

**Daily focus time (weekdays 9-5):**
1. Create block with time range
2. Enable watchdogs
3. Lock settings daily during work hours
4. Settings unlock evenings/weekends

**Exam week (1 week):**
1. Enable maximum watchdogs (5)
2. Lock settings for 1 week
3. Add break periods as allowed times
4. Removes temptation to disable

## Implementation Details

### Files

**Core Logic:**
- `daemon/watchdog.py` - `WatchdogManager` and `Watchdog` classes
- `daemon/watchdog_runner.py` - Standalone watchdog process entry point

**Integration:**
- `daemon/main.py` - Spawns watchdogs on daemon startup
- `daemon/api.py` - Watchdog and settings lock API endpoints
- `daemon/config.py` - Configuration storage

### Key Functions

**WatchdogManager.spawn_watchdogs():**
- Forks N child processes
- Sets obfuscated process names
- Detaches from parent
- Executes watchdog_runner.py

**Watchdog.run():**
- Main monitoring loop
- Performs health checks
- Handles restarts
- Updates heartbeat

**is_settings_locked_ntp():**
- Reads `settings_lock_until` from config
- Queries NTP servers for accurate time
- Compares current time to lock expiry
- Returns lock status

### Process Lifecycle

```
Daemon Startup
    ↓
WatchdogManager.spawn_watchdogs()
    ↓
fork() × N processes
    ↓
Child: os.setsid() - Detach from parent
    ↓
Child: os.execv(watchdog_runner.py)
    ↓
Watchdog.run() - Monitoring loop
    ↓
Exit on shutdown_requested (if not locked)
```

---

**Remember:** Watchdogs are a tool for self-improvement, not punishment. Use them to build better habits, not to torture yourself! 🐕🚀
