# Multi-Profile Browser Window Counting

## Overview

This document describes the multi-profile window counting system that prevents users from bypassing the blocker by opening guest profiles or multiple browser profiles without the extension installed.

## The Problem

### Guest Profile Bypass Vulnerability

Chromium-based browsers allow users to open "Guest" profiles without signing in. These guest profiles:
- Share the same process ID (PID) as the main browser
- Run as separate profiles with isolated extensions
- Do **not** have the blocker extension installed (extensions don't auto-install in guest mode)

**Before the fix:**
```
Main Profile (PID: 12345)
├─ 1 window with extension → sends heartbeat
└─ Guest Profile
   └─ 1 window WITHOUT extension → no heartbeat

Daemon sees:
- PID 12345 sending heartbeats ✓
- Thinks entire browser is monitored
- Guest profile bypasses blocking ✗
```

### Multiple Profile Issue

Similarly, users could open multiple profiles:
- Profile A with extension (1 window)
- Profile B with extension (1 window)
- Both share PID 12345

**Before the fix:**
- Each extension sends `window_count: 1`
- Heartbeats overwrite each other (last one wins)
- Daemon thinks extension sees 1 window
- Hyprland sees 2 windows
- **False positive**: Browser gets killed even though both profiles have extensions

## The Solution

### Extension Instance Tracking

Each browser profile runs its own instance of the extension with a unique `chrome.runtime.id`. By tracking window counts per extension instance and summing them, we can detect unmonitored windows.

**Architecture:**

```
Browser Process (PID: 12345)
│
├─ Profile A (extension_id: "abc123...")
│  ├─ Window 1
│  └─ Window 2
│  └─ Extension → heartbeat {extension_id: "abc123", window_count: 2}
│
├─ Profile B (extension_id: "def456...")
│  └─ Window 1
│  └─ Extension → heartbeat {extension_id: "def456", window_count: 1}
│
└─ Guest Profile (no extension_id)
   └─ Window 1
   └─ NO heartbeat

Daemon tracking:
- extension_instances[12345] = {
    "abc123...": {window_count: 2, last_seen: ...},
    "def456...": {window_count: 1, last_seen: ...}
  }
- Total extension count: 2 + 1 = 3
- Hyprland count: 4 (includes guest window)
- Mismatch detected → Kill browser
```

## Implementation

### 1. Extension Changes (`extension/background.js`)

**Added to heartbeat payload:**
```javascript
{
    pid: browserPID,
    browser: getBrowserName(),
    incognito: isIncognito,
    incognito_enabled: incognitoAllowed,
    extension_id: chrome.runtime.id,  // NEW: Unique per profile
    window_count: windowCount,
    timestamp: Date.now()
}
```

**`chrome.runtime.id` properties:**
- Unique per extension installation
- Persists across browser restarts
- Different for each browser profile
- Does not exist in guest profiles (no extensions)

### 2. API Changes (`daemon/api.py`)

**Updated HeartbeatRequest model:**
```python
class HeartbeatRequest(BaseModel):
    pid: int
    browser: str
    incognito: bool = False
    incognito_enabled: bool = True
    extension_id: str  # Required - Unique per profile
    window_count: int  # Required - Windows visible to this extension
    timestamp: Optional[int] = None
```

### 3. Heartbeat Tracker Changes (`daemon/heartbeat_tracker.py`)

**New data structures:**
```python
@dataclass
class ExtensionInstance:
    """Tracks a single extension instance (one per browser profile)."""
    extension_id: str
    window_count: int
    last_seen: datetime

class HeartbeatTracker:
    def __init__(self):
        self.active_browsers: Dict[int, BrowserHeartbeat] = {}
        # NEW: Track extension instances per PID
        # {pid: {extension_id: ExtensionInstance}}
        self.extension_instances: Dict[int, Dict[str, ExtensionInstance]] = {}
```

**Key method - Sum window counts:**
```python
def get_total_extension_window_count(self, pid: int) -> Optional[int]:
    """Sum window counts from all extension instances for this PID."""
    if pid not in self.extension_instances:
        return None

    now = datetime.now()
    timeout = timedelta(seconds=self.heartbeat_timeout)
    total = 0

    for instance in self.extension_instances[pid].values():
        if now - instance.last_seen <= timeout:
            total += instance.window_count

    return total if total > 0 else None
```

### 4. Monitor Changes (`daemon/hyprland_monitor.py`)

**Updated detection:**
```python
def get_browsers_with_unmonitored_windows(...) -> Set[int]:
    for pid in browser_windows.keys():
        # Get TOTAL count from ALL extension instances
        extension_count = tracker.get_total_extension_window_count(pid)
        hyprland_count = self.count_browser_windows_by_pid(windows, pid)

        if hyprland_count > extension_count:
            # Unmonitored windows detected (guest profile, etc.)
            mismatch_count = tracker.increment_window_mismatch(pid)
            if mismatch_count >= 2:
                unmonitored.add(pid)
```

## Scenarios

### Scenario 1: Single Profile, Multiple Windows ✓
```
Profile A with extension
├─ Window 1
└─ Window 2

Extension reports: window_count: 2
Hyprland sees: 2 windows
Match → Browser OK
```

### Scenario 2: Two Profiles with Extensions ✓
```
Profile A with extension
└─ Window 1 → heartbeat {extension_id: "aaa", window_count: 1}

Profile B with extension
└─ Window 1 → heartbeat {extension_id: "bbb", window_count: 1}

Daemon sums: 1 + 1 = 2
Hyprland sees: 2 windows
Match → Browser OK
```

### Scenario 3: One Profile + Guest Profile ✗
```
Profile A with extension
└─ Window 1 → heartbeat {extension_id: "aaa", window_count: 1}

Guest Profile (no extension)
└─ Window 1 → NO heartbeat

Daemon sums: 1 (only from Profile A)
Hyprland sees: 2 windows
Mismatch → Browser KILLED after 2 consecutive checks (~10s)
```

### Scenario 4: Two Profiles, One Without Extension ✗
```
Profile A with extension
└─ Window 1 → heartbeat {extension_id: "aaa", window_count: 1}

Profile B WITHOUT extension
└─ Window 1 → NO heartbeat

Daemon sums: 1 (only from Profile A)
Hyprland sees: 2 windows
Mismatch → Browser KILLED
```

## Edge Cases

### Timing Windows
**Issue**: User opens a new window between heartbeats (30s interval)
- Extension heartbeat: `window_count: 1` (sent before new window opened)
- Hyprland: sees 2 windows (right after new window opened)
- Brief mismatch

**Solution**: Require 2+ consecutive mismatches (mismatch counter)
- First mismatch: counter = 1, wait
- Second mismatch: counter = 2, kill browser
- If counts match again: counter reset to 0

This gives a ~10 second grace period for timing discrepancies.

### Stale Extension Instances
**Issue**: User closes a profile, but extension instance data remains

**Solution**: Extension instances are automatically cleaned up:
```python
def cleanup_old_heartbeats(self):
    for pid in self.extension_instances.keys():
        stale_extensions = [
            ext_id for ext_id, instance in self.extension_instances[pid].items()
            if now - instance.last_seen > timeout
        ]
        for ext_id in stale_extensions:
            del self.extension_instances[pid][ext_id]
```

Only extension instances with recent heartbeats (within 60s) are counted.

### DevTools Windows
**Issue**: Chrome DevTools create separate windows that might be counted differently

**Solution**: Extension filters by window type:
```javascript
const windows = await chrome.windows.getAll({
    windowTypes: ['normal', 'popup']
});
```

This excludes `'devtools'` type windows from the count.

## Security Properties

### Bypass Resistance
- **Cannot spoof extension_id**: Each profile's extension has a unique Chrome-assigned ID
- **Cannot fake window counts**: Extension reports truthfully from its limited scope
- **Cannot hide windows**: Hyprland sees all windows via IPC, regardless of profile

### Fail-Safe Behavior
- If extension crashes/stops: No heartbeat → browser killed
- If extension can't count windows: Returns `None` → no enforcement (graceful degradation)
- If Hyprland unavailable: Can't count windows → monitoring paused

### Attack Surface
The only way to bypass this system:
1. Modify the daemon code (requires root/user permissions)
2. Disable Hyprland/use different window manager
3. Run browser in a VM/container that daemon can't see

All of these require significantly more technical sophistication than simply opening a guest profile.

## Performance Impact

### Memory
- Per extension instance: ~100 bytes (`ExtensionInstance` dataclass)
- Typical usage: 1-2 profiles = 100-200 bytes
- Negligible impact

### CPU
- Window counting: O(n) where n = number of browser windows
- Typically n < 10, so < 1ms per check
- Runs every 5 seconds in monitor loop
- Negligible impact

### Network
- Additional 36 bytes per heartbeat (extension_id field)
- Heartbeats sent every 30 seconds
- ~1.2 bytes/second additional bandwidth
- Negligible impact

## Monitoring & Debugging

### View Extension Instances
Check the daemon logs for extension instance tracking:
```bash
journalctl --user -u website-blocker | grep "extension instance"
```

Example output:
```
Updated extension instance: abc12345... (PID: 12345, windows: 2)
Updated extension instance: def67890... (PID: 12345, windows: 1)
```

### View Window Count Mismatches
```bash
journalctl --user -u website-blocker | grep "unmonitored windows"
```

Example output:
```
Browser PID 12345 has unmonitored windows! Extension sees 2, Hyprland sees 3 (mismatch count: 2)
```

### Manual Verification
1. Open browser windows in different profiles
2. Check API: `curl http://127.0.0.1:8765/api/browsers`
3. Compare `hyprctl clients -j | jq '.[] | select(.class == "chromium")'`

## Future Enhancements

### Per-Extension Window Details
Could track which specific windows belong to which extension instance, but currently unnecessary for blocking logic.

### Profile Name Detection
Could attempt to extract profile names from window titles, but not needed since extension_id already provides unique identification.

### Window Type Filtering
Could add more sophisticated window type detection (e.g., ignore PiP windows), but current filter is sufficient.
