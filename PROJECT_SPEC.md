# Website & Application Blocker - Project Specification

## Project Overview

Build a robust website and application blocking system for Arch Linux + Hyprland that prevents access to distracting sites and apps during scheduled focus periods. The system consists of three main components:

1. **Daemon** (Python) - Background service that enforces blocks
2. **Desktop App** (Python + pywebview[gtk]) - GUI for configuration
3. **Browser Extension** (JavaScript) - Blocks sites and maintains heartbeat

## Core Philosophy

- **Strict by default**: No warnings, no pauses, no bypasses during lock periods
- **Fail-safe**: When in doubt, block (network down, database corrupted, etc.)
- **Bypass-resistant**: Multiple layers of protection against circumvention
- **Lock mode**: During scheduled blocks, configuration is read-only and daemon cannot be stopped

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  USER SPACE                                                  │
│                                                              │
│  ┌──────────────────┐         ┌─────────────────────────┐  │
│  │  Desktop App     │  HTTP   │   Daemon (systemd)      │  │
│  │  (pywebview+GTK) │◄───────►│   - FastAPI server      │  │
│  │                  │         │   - Schedule checker     │  │
│  │  - Config UI     │         │   - Hyprland monitor    │  │
│  │  - View stats    │         │   - Heartbeat tracker   │  │
│  │  - Manage rules  │         │   - Lock mode enforcer  │  │
│  └──────────────────┘         │   - NTP time verifier   │  │
│                                └───────┬─────────────────┘  │
│                                        │                     │
│  ┌──────────────────┐                 │                     │
│  │ Browser          │    Heartbeat    │                     │
│  │  + Extension     │─────────────────┘                     │
│  │                  │  (every 30s)                          │
│  │  - Blocks sites  │                                        │
│  │  - Sends pulse   │  {browser, pid, incognito, timestamp} │
│  │  - Works in      │                                        │
│  │    incognito     │                                        │
│  └──────────────────┘                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
         │                      │
         │                      │
         ▼                      ▼
┌─────────────────┐    ┌──────────────────┐
│  Hyprland IPC   │    │  Storage         │
│  - List windows │    │  - SQLite DB     │
│  - Close windows│    │  - JSON config   │
└─────────────────┘    └──────────────────┘
```

## Component 1: Daemon (Python)

### Technology Stack
- **Python 3.11+**
- **FastAPI** - REST API server
- **APScheduler** - Schedule management
- **SQLAlchemy** - Database ORM
- **asyncio** - Async operations
- **subprocess** - Hyprland IPC interaction

### File Structure
```
daemon/
├── main.py                 # Entry point, systemd service
├── api.py                  # FastAPI routes
├── blocker.py              # Core blocking logic
├── scheduler.py            # Schedule checking and enforcement
├── hyprland_monitor.py     # Hyprland window monitoring
├── heartbeat_tracker.py    # Browser extension heartbeat tracking
├── lock_manager.py         # Lock mode enforcement
├── time_verifier.py        # NTP time verification
├── database.py             # SQLAlchemy models and DB setup
├── config.py               # Configuration management
└── utils.py                # Helper functions
```

### Key Responsibilities

#### 1. REST API Server (api.py)
Endpoints:
- `POST /api/heartbeat` - Receive extension heartbeat
- `GET /api/rules` - Get all blocking rules
- `POST /api/rules` - Add new rule (checks lock mode)
- `PUT /api/rules/{id}` - Update rule (checks lock mode)
- `DELETE /api/rules/{id}` - Delete rule (checks lock mode)
- `GET /api/schedules` - Get all schedules
- `POST /api/schedules` - Add schedule (checks lock mode)
- `PUT /api/schedules/{id}` - Update schedule (checks lock mode)
- `DELETE /api/schedules/{id}` - Delete schedule (checks lock mode)
- `GET /api/status` - Get daemon status, lock state, active rules
- `GET /api/stats` - Get blocking statistics
- `GET /api/browsers` - Get detected browsers and extension status

All modification endpoints must check `lock_manager.is_locked()` first.

#### 2. Schedule Checking (scheduler.py)
- Run check every 10 seconds
- Evaluate all schedules against current time
- Activate/deactivate rules based on schedules
- Trigger lock mode when entering scheduled block period
- Release lock mode when exiting scheduled block period
- Verify system time against NTP at lock transitions

Schedule types:
```python
class ScheduleType(Enum):
    TIME_RANGE = "time_range"  # e.g., "9am-5pm on weekdays"
    LOCKED_UNTIL = "locked_until"  # e.g., "locked until Dec 25, 2025 5pm"

class Schedule:
    id: int
    schedule_type: ScheduleType
    
    # For TIME_RANGE
    days_of_week: List[int]  # 0=Monday, 6=Sunday
    start_time: time  # e.g., 09:00
    end_time: time    # e.g., 17:00
    
    # For LOCKED_UNTIL
    locked_until: datetime  # Absolute timestamp
    
    # Associated rules
    block_rules: List[BlockRule]
    enabled: bool
```

#### 3. Hyprland Monitoring (hyprland_monitor.py)
- Run check every 5 seconds
- Get all windows: `hyprctl clients -j`
- Identify browser windows by class name
- Close blocked applications: `hyprctl dispatch closewindow address:{address}`
- Close browsers without active extension (no heartbeat in 60s)
- Close browsers missing incognito heartbeat (if incognito window detected)

Supported browser classes (hardcoded):
```python
BROWSER_CLASSES = [
    'firefox',
    'firefox-esr',
    'chromium',
    'google-chrome',
    'brave-browser',
    'microsoft-edge',
    'opera',
    'vivaldi-stable'
]
```

#### 4. Heartbeat Tracking (heartbeat_tracker.py)
Track active browser instances:
```python
class HeartbeatTracker:
    # {pid: {last_seen: datetime, incognito_last_seen: datetime, browser: str}}
    active_browsers: Dict[int, BrowserHeartbeat]
    
    HEARTBEAT_TIMEOUT = 60  # seconds
    
    def register_heartbeat(self, pid: int, browser: str, incognito: bool):
        """Register a heartbeat from browser extension"""
        
    def get_compliant_browsers(self) -> Set[int]:
        """Get PIDs of browsers with recent heartbeats"""
        
    def get_non_compliant_browsers(self, all_browser_pids: Set[int]) -> Set[int]:
        """Find browsers without recent heartbeats"""
        
    def cleanup_old_heartbeats(self):
        """Remove heartbeats older than timeout"""
```

#### 5. Lock Mode Management (lock_manager.py)
```python
class LockManager:
    def is_locked(self) -> bool:
        """Check if currently in a locked period"""
        now = self.get_verified_time()
        for schedule in self.get_active_schedules():
            if schedule.is_active(now):
                return True
        return False
    
    def get_verified_time(self) -> datetime:
        """Get current time, verified against NTP if needed"""
        # Check cache first
        # If near lock transition, verify with NTP
        
    def verify_time_with_ntp(self) -> bool:
        """Check system time against NTP servers"""
        # Query multiple NTP servers
        # If difference > 5 minutes, something is wrong
        # Return False if can't reach NTP (network down)
    
    def handle_lock_transition(self, entering_lock: bool):
        """Called when entering/exiting lock period"""
        if entering_lock:
            # Verify time with NTP
            # Show notification
            # Enforce all active rules immediately
        else:
            # Verify time with NTP (prevent early exit)
            # Show notification
```

#### 6. Time Verification (time_verifier.py)
```python
class TimeVerifier:
    NTP_SERVERS = [
        'pool.ntp.org',
        'time.google.com',
        'time.cloudflare.com'
    ]
    
    MAX_TIME_DIFF = 300  # 5 minutes
    
    def get_ntp_time(self) -> Optional[datetime]:
        """Query NTP servers for accurate time"""
        # Try each server until one responds
        # Return None if all fail (network down)
    
    def is_system_time_valid(self) -> bool:
        """Check if system time is reasonable"""
        ntp_time = self.get_ntp_time()
        if ntp_time is None:
            # Network down - fail safe (assume valid but log)
            return True
        
        system_time = datetime.now()
        diff = abs((ntp_time - system_time).total_seconds())
        
        if diff > self.MAX_TIME_DIFF:
            # Time manipulation detected
            return False
        return True
    
    def verify_at_lock_transitions(self, transition_time: datetime) -> bool:
        """Verify time specifically at lock start/end"""
        # This is called when entering or exiting lock
        # MUST verify with NTP to prevent time manipulation
        # If network down, use cached verification or fail-safe block
```

#### 7. Database Schema (database.py)
```python
class BlockRule(Base):
    __tablename__ = 'block_rules'
    
    id: int
    rule_type: str  # 'website' or 'application'
    target: str  # URL pattern or app class name
    enabled: bool
    created_at: datetime

class Schedule(Base):
    __tablename__ = 'schedules'
    
    id: int
    name: str
    schedule_type: str  # 'time_range' or 'locked_until'
    
    # TIME_RANGE fields
    days_of_week: str  # JSON: [0,1,2,3,4]
    start_time: str  # "09:00"
    end_time: str  # "17:00"
    
    # LOCKED_UNTIL fields
    locked_until: datetime  # Absolute timestamp
    
    enabled: bool
    created_at: datetime

class ScheduleRule(Base):
    __tablename__ = 'schedule_rules'
    
    id: int
    schedule_id: int  # FK to schedules
    rule_id: int  # FK to block_rules

class BlockEvent(Base):
    __tablename__ = 'block_events'
    
    id: int
    rule_id: int
    blocked_target: str  # What was blocked
    timestamp: datetime
    event_type: str  # 'website_blocked', 'app_closed', 'browser_killed'

class HeartbeatLog(Base):
    __tablename__ = 'heartbeat_logs'
    
    id: int
    browser_pid: int
    browser_name: str
    incognito: bool
    timestamp: datetime
```

#### 8. Configuration (config.py)
Location: `~/.config/website-blocker/config.json`

```json
{
    "daemon": {
        "host": "127.0.0.1",
        "port": 8765,
        "log_level": "INFO"
    },
    "monitoring": {
        "check_interval_seconds": 5,
        "heartbeat_timeout_seconds": 60,
        "schedule_check_interval_seconds": 10
    },
    "security": {
        "ntp_servers": [
            "pool.ntp.org",
            "time.google.com",
            "time.cloudflare.com"
        ],
        "max_time_diff_seconds": 300,
        "verify_time_on_transitions": true
    },
    "browsers": [
        "firefox",
        "firefox-esr",
        "chromium",
        "google-chrome",
        "brave-browser",
        "microsoft-edge",
        "opera",
        "vivaldi-stable"
    ]
}
```

During lock mode, daemon ignores changes to this file.

#### 9. Signal Handling (main.py)
```python
def handle_sigterm(signum, frame):
    """Handle termination signals"""
    if lock_manager.is_locked():
        logger.warning("Ignoring stop signal during lock period")
        show_notification(
            "Website Blocker",
            "Cannot stop daemon during locked period"
        )
        return  # Refuse to stop
    else:
        logger.info("Shutting down daemon")
        shutdown()
        sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)
```

#### 10. Systemd Service
File: `/etc/systemd/system/website-blocker.service`

```ini
[Unit]
Description=Website Blocker Daemon
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=%USER%
Environment="PYTHONUNBUFFERED=1"
WorkingDirectory=/home/%USER%/.config/website-blocker
ExecStart=/usr/bin/python3 /path/to/daemon/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Make it harder to kill
KillMode=process
KillSignal=SIGTERM
SendSIGKILL=no

[Install]
WantedBy=default.target
```

### Error Handling Rules

| Situation | Behavior |
|-----------|----------|
| Network down (can't verify NTP) | Trust system time, log warning |
| Network down at lock transition | Block by default (fail-safe) |
| Hyprland IPC fails | Log error, continue daemon (can't enforce) |
| Database corrupted | Block everything, show critical error |
| Extension crashes (no heartbeat) | Close browser after timeout |
| Config file corrupted | Use default config (block everything) |
| Can't bind to port 8765 | Exit with error (critical) |

## Component 2: Desktop App (Python + pywebview)

### Technology Stack
- **Python 3.11+**
- **pywebview[gtk]** - Native window with web content
- **HTML/CSS/JavaScript** - Frontend UI
- **Tailwind CSS** - Styling
- **Requests** - HTTP client to talk to daemon

### File Structure
```
desktop-app/
├── main.py                # Entry point, creates pywebview window
├── api_client.py          # Wrapper for daemon API calls
├── web/
│   ├── index.html         # Main UI
│   ├── styles.css         # Custom styles (Tailwind)
│   ├── app.js             # Frontend logic
│   └── assets/
│       └── icons/         # UI icons
└── utils.py               # Helper functions
```

### UI Pages/Views

#### 1. Dashboard (Home)
- Current status: "Blocking Active" / "Idle"
- Active schedules (if any)
- Quick stats: Sites blocked today, apps closed today
- Browser status: Show which browsers have extension installed
  - ✅ Firefox - Extension active
  - ❌ Chrome - Extension not detected
  - ✅ Brave - Extension active (incognito: ✅)

#### 2. Block Rules
List of all rules with:
- Type (website/app)
- Target (URL pattern or app name)
- Status (enabled/disabled)
- Actions: Edit, Delete (disabled during lock)

Add New Rule form:
- Type: Website / Application
- Target: 
  - For websites: URL pattern (e.g., `reddit.com`, `*.youtube.com`)
  - For apps: Class name (e.g., `steam`, `discord`)
- Preview: Show example matches

#### 3. Schedules
List of schedules with:
- Name
- Type (Time Range / Locked Until)
- Details (e.g., "Weekdays 9am-5pm")
- Associated rules count
- Status (enabled/disabled)
- Actions: Edit, Delete (disabled during lock)

Add New Schedule form:

**Time Range:**
- Days: Checkboxes for Mon-Sun
- Start time: Time picker
- End time: Time picker
- Rules: Multi-select from existing rules

**Locked Until:**
- Date: Date picker
- Time: Time picker
- Rules: Multi-select from existing rules

#### 4. Statistics
- Chart: Blocks over time (daily)
- Table: Most blocked sites/apps
- Total blocks this week/month
- Time saved estimate

#### 5. Settings
- Daemon status: Running / Stopped
- Port: 8765
- Log level: Debug / Info / Warning / Error
- NTP servers: List of servers
- Browser list: Editable list of browser class names
- About: Version info, GitHub link

#### 6. Extension Setup Guide
- Step-by-step instructions for each browser
- Links to extension stores (or manual install)
- Test page: Check if extension is working
- Shows current status of each browser

### Lock Mode UI Behavior

When daemon reports `is_locked: true`:
- Show lock icon in top bar
- All edit/delete buttons disabled
- Add/Create buttons disabled
- Show message: "Configuration locked during blocking period"
- Show countdown: "Unlocks in 3h 42m"

When user tries to edit:
- Show modal: "Cannot modify rules during lock period. Lock will end at 5:00 PM."

### API Integration (api_client.py)

```python
class DaemonClient:
    BASE_URL = "http://127.0.0.1:8765/api"
    
    def get_status(self) -> Dict:
        """Get daemon status and lock state"""
        
    def get_rules(self) -> List[BlockRule]:
        """Get all blocking rules"""
        
    def add_rule(self, rule: BlockRule) -> BlockRule:
        """Add new rule (may fail if locked)"""
        
    def update_rule(self, rule_id: int, rule: BlockRule) -> BlockRule:
        """Update rule (may fail if locked)"""
        
    def delete_rule(self, rule_id: int) -> bool:
        """Delete rule (may fail if locked)"""
        
    # ... similar methods for schedules, stats, browsers
    
    def is_daemon_running(self) -> bool:
        """Check if daemon is reachable"""
```

### First-Time Setup Flow

On first launch:
1. Check if daemon is running
2. If not, show setup wizard:
   - "Welcome to Website Blocker"
   - "Installing daemon as system service..."
   - Run: `sudo systemctl enable website-blocker`
   - Run: `sudo systemctl start website-blocker`
3. Show extension installation page
4. Wait for extension heartbeats
5. Guide user to create first schedule
6. Done

## Component 3: Browser Extension

### Technology Stack
- **WebExtensions API** (compatible with Firefox & Chrome)
- **Native Messaging** (to get browser PID)
- **Vanilla JavaScript** (no frameworks)

### File Structure
```
extension/
├── manifest.json          # Extension manifest (v3)
├── background.js          # Service worker (main logic)
├── content.js             # Content script (optional)
├── popup/
│   ├── popup.html         # Extension popup UI
│   ├── popup.js           # Popup logic
│   └── popup.css          # Popup styles
├── blocked.html           # Page shown when site is blocked
├── blocked.js             # Blocked page logic
├── native-host/
│   ├── host.py            # Native messaging host (gets PID)
│   └── manifest.json      # Native messaging manifest
└── icons/
    └── icon*.png          # Extension icons
```

### Manifest (manifest.json)
```json
{
  "manifest_version": 3,
  "name": "Website Blocker",
  "version": "1.0.0",
  "description": "Blocks websites during focus periods",
  "permissions": [
    "webRequest",
    "webRequestBlocking",
    "storage",
    "nativeMessaging",
    "tabs",
    "notifications"
  ],
  "host_permissions": [
    "<all_urls>"
  ],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": "icons/icon48.png"
  },
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  },
  "web_accessible_resources": [{
    "resources": ["blocked.html"],
    "matches": ["<all_urls>"]
  }]
}
```

### Background Script (background.js)

```javascript
const DAEMON_URL = 'http://127.0.0.1:8765';
const HEARTBEAT_INTERVAL = 30000; // 30 seconds
let browserPID = null;
let blockedSites = [];

// Initialize
chrome.runtime.onInstalled.addListener(async () => {
    console.log('Extension installed');
    await getBrowserPID();
    startHeartbeat();
    await fetchBlockedSites();
});

chrome.runtime.onStartup.addListener(async () => {
    console.log('Browser started');
    await getBrowserPID();
    startHeartbeat();
    await fetchBlockedSites();
});

// Get browser PID via native messaging
async function getBrowserPID() {
    try {
        const port = chrome.runtime.connectNative('com.websiteblocker.host');
        
        port.onMessage.addListener((message) => {
            if (message.pid) {
                browserPID = message.pid;
                console.log('Browser PID:', browserPID);
            }
        });
        
        port.postMessage({ action: 'get_pid' });
    } catch (error) {
        console.error('Failed to get PID:', error);
    }
}

// Send heartbeat to daemon
async function sendHeartbeat() {
    try {
        const isIncognito = await isIncognitoWindow();
        
        const response = await fetch(`${DAEMON_URL}/api/heartbeat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pid: browserPID,
                browser: getBrowserName(),
                incognito: isIncognito,
                timestamp: Date.now()
            })
        });
        
        if (response.ok) {
            console.log('Heartbeat sent successfully');
        }
    } catch (error) {
        console.error('Failed to send heartbeat:', error);
    }
}

// Check if current window is incognito
async function isIncognitoWindow() {
    const windows = await chrome.windows.getAll();
    for (const window of windows) {
        if (window.focused && window.incognito) {
            return true;
        }
    }
    return false;
}

// Start heartbeat loop
function startHeartbeat() {
    sendHeartbeat(); // Send immediately
    setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
}

// Fetch blocked sites from daemon
async function fetchBlockedSites() {
    try {
        const response = await fetch(`${DAEMON_URL}/api/rules`);
        const rules = await response.json();
        
        blockedSites = rules
            .filter(r => r.rule_type === 'website' && r.enabled)
            .map(r => r.target);
        
        console.log('Blocked sites updated:', blockedSites);
    } catch (error) {
        console.error('Failed to fetch blocked sites:', error);
    }
}

// Refresh blocked sites every minute
setInterval(fetchBlockedSites, 60000);

// Block requests to blocked sites
chrome.webRequest.onBeforeRequest.addListener(
    (details) => {
        const url = new URL(details.url);
        const hostname = url.hostname;
        
        // Check if this site is blocked
        for (const pattern of blockedSites) {
            if (matchesPattern(hostname, pattern)) {
                console.log('Blocking:', hostname);
                
                // Redirect to blocked page
                return {
                    redirectUrl: chrome.runtime.getURL('blocked.html') +
                                '?url=' + encodeURIComponent(details.url) +
                                '&site=' + encodeURIComponent(hostname)
                };
            }
        }
    },
    { urls: ['<all_urls>'], types: ['main_frame'] },
    ['blocking']
);

// Pattern matching helper
function matchesPattern(hostname, pattern) {
    // Exact match
    if (hostname === pattern) return true;
    
    // Wildcard subdomain (*.example.com)
    if (pattern.startsWith('*.')) {
        const domain = pattern.slice(2);
        return hostname === domain || hostname.endsWith('.' + domain);
    }
    
    // Subdomain match (example.com matches www.example.com)
    if (hostname.endsWith('.' + pattern)) return true;
    
    return false;
}

// Detect browser
function getBrowserName() {
    const userAgent = navigator.userAgent.toLowerCase();
    if (userAgent.includes('firefox')) return 'firefox';
    if (userAgent.includes('chrome')) return 'chrome';
    if (userAgent.includes('brave')) return 'brave';
    if (userAgent.includes('edge')) return 'edge';
    return 'unknown';
}
```

### Native Messaging Host (native-host/host.py)

```python
#!/usr/bin/env python3
import sys
import json
import struct
import os

def send_message(message):
    """Send message to extension"""
    encoded = json.dumps(message).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('I', len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()

def read_message():
    """Read message from extension"""
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None
    length = struct.unpack('I', raw_length)[0]
    message = sys.stdin.buffer.read(length).decode('utf-8')
    return json.loads(message)

def main():
    while True:
        message = read_message()
        if message is None:
            break
        
        if message.get('action') == 'get_pid':
            # Return parent process PID (the browser)
            pid = os.getppid()
            send_message({'pid': pid})

if __name__ == '__main__':
    main()
```

### Native Messaging Manifest (native-host/manifest.json)

For Firefox (`~/.mozilla/native-messaging-hosts/com.websiteblocker.host.json`):
```json
{
  "name": "com.websiteblocker.host",
  "description": "Website Blocker Native Host",
  "path": "/path/to/native-host/host.py",
  "type": "stdio",
  "allowed_extensions": ["website-blocker@example.com"]
}
```

For Chrome (`~/.config/google-chrome/NativeMessagingHosts/com.websiteblocker.host.json`):
```json
{
  "name": "com.websiteblocker.host",
  "description": "Website Blocker Native Host",
  "path": "/path/to/native-host/host.py",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://YOUR_EXTENSION_ID/"
  ]
}
```

### Blocked Page (blocked.html)

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Site Blocked</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            text-align: center;
            max-width: 600px;
            padding: 40px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            backdrop-filter: blur(10px);
        }
        h1 {
            font-size: 3em;
            margin: 0 0 20px 0;
        }
        .icon {
            font-size: 4em;
            margin-bottom: 20px;
        }
        .site {
            font-size: 1.2em;
            margin: 20px 0;
            padding: 10px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
        }
        .message {
            font-size: 1.1em;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🚫</div>
        <h1>Site Blocked</h1>
        <div class="site" id="blocked-site"></div>
        <div class="message">
            This site is blocked during your focus period.
            <br><br>
            Stay focused on what matters!
        </div>
    </div>
    <script src="blocked.js"></script>
</body>
</html>
```

### Blocked Page Script (blocked.js)

```javascript
// Get URL parameters
const params = new URLSearchParams(window.location.search);
const blockedUrl = params.get('url');
const blockedSite = params.get('site');

// Display blocked site
document.getElementById('blocked-site').textContent = blockedSite || blockedUrl;

// Prevent navigation
window.history.pushState(null, null, window.location.href);
window.addEventListener('popstate', () => {
    window.history.pushState(null, null, window.location.href);
});
```

### Extension Popup (popup/popup.html)

Simple status display:
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="popup.css">
</head>
<body>
    <div class="popup">
        <h2>Website Blocker</h2>
        <div class="status">
            <span class="indicator" id="status-indicator">●</span>
            <span id="status-text">Checking...</span>
        </div>
        <div class="info">
            <p><strong>Blocked sites:</strong> <span id="blocked-count">0</span></p>
            <p><strong>Status:</strong> <span id="daemon-status">Unknown</span></p>
        </div>
        <button id="open-app">Open Settings</button>
    </div>
    <script src="popup.js"></script>
</body>
</html>
```

## Installation & Setup

### 1. Install Dependencies

```bash
# System packages
sudo pacman -S python python-pip webkit2gtk

# Python packages
pip install --user fastapi uvicorn sqlalchemy aiosqlite apscheduler pywebview[gtk]
```

### 2. Install Daemon as Service

```bash
# Copy daemon files
mkdir -p ~/.config/website-blocker
cp -r daemon/* ~/.config/website-blocker/

# Create systemd service
sudo cp config/website-blocker.service /etc/systemd/system/
sudo sed -i "s/%USER%/$USER/g" /etc/systemd/system/website-blocker.service

# Enable and start
sudo systemctl enable website-blocker
sudo systemctl start website-blocker
```

### 3. Install Browser Extension

**Firefox:**
1. Go to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `extension/manifest.json`
4. Install native host: `cp native-host/manifest.json ~/.mozilla/native-messaging-hosts/`

**Chrome:**
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `extension/` directory
5. Install native host: `cp native-host/manifest.json ~/.config/google-chrome/NativeMessagingHosts/`

**Important:** Must enable extension in incognito/private mode in browser settings!

### 4. Launch Desktop App

```bash
cd desktop-app
python main.py
```

## Testing Checklist

### Daemon Tests
- [ ] Daemon starts successfully
- [ ] API endpoints respond correctly
- [ ] Schedules activate/deactivate at correct times
- [ ] Lock mode prevents configuration changes
- [ ] NTP time verification works
- [ ] Daemon refuses to stop during lock
- [ ] Hyprland window detection works
- [ ] Heartbeat tracking works
- [ ] Non-compliant browsers are closed
- [ ] Database operations work
- [ ] Systemd service auto-restarts

### Extension Tests
- [ ] Extension loads in Firefox
- [ ] Extension loads in Chrome
- [ ] Heartbeat sends successfully
- [ ] Native messaging gets PID
- [ ] Blocked sites redirect to blocked page
- [ ] Pattern matching works (*.example.com)
- [ ] Works in incognito/private mode
- [ ] Incognito heartbeat sends correctly

### Desktop App Tests
- [ ] App window opens
- [ ] Can view rules
- [ ] Can add/edit/delete rules (when unlocked)
- [ ] Can view schedules
- [ ] Can add/edit/delete schedules (when unlocked)
- [ ] Lock mode disables UI correctly
- [ ] Browser status shows correctly
- [ ] Statistics display correctly

### Integration Tests
- [ ] End-to-end: Add rule → Schedule → Block triggers → Site blocked
- [ ] Lock mode: Schedule activates → UI locks → Daemon refuses stop
- [ ] Extension crash: Heartbeat stops → Browser closes
- [ ] Time manipulation: Change system time → Detected → Falls back to safe
- [ ] Network down: NTP fails → Blocks anyway (fail-safe)

## Future Enhancements (Post-Prototype)

1. **Rust rewrite** - Prevent `killall python3` bypass
2. **Break intervals** - Allow 5 minutes every hour
3. **Usage limits** - Block after 30 minutes total usage
4. **Categories** - Pre-defined site categories (Social, News, Gaming)
5. **Allowlist mode** - Block everything except specified sites
6. **Focus sessions** - Pomodoro-style timed sessions
7. **Multi-device sync** - Sync rules across machines
8. **Mobile companion** - Android/iOS app
9. **Accountability partner** - Share stats with friend
10. **Analytics** - Detailed usage insights

## Development Notes

### Hyprland IPC Examples

```bash
# List all windows
hyprctl clients -j

# Example output:
[
  {
    "address": "0x5b4e8f4a0",
    "mapped": true,
    "hidden": false,
    "at": [100, 100],
    "size": [1920, 1080],
    "workspace": {
      "id": 1,
      "name": "1"
    },
    "floating": false,
    "monitor": 0,
    "class": "firefox",
    "title": "Reddit - Dive into anything",
    "pid": 12345,
    "xwayland": false
  }
]

# Close window by address
hyprctl dispatch closewindow address:0x5b4e8f4a0

# Close window by PID
hyprctl dispatch closewindow pid:12345
```

### NTP Query Example

```bash
# Query NTP server
ntpdate -q pool.ntp.org

# Example output:
server 162.159.200.123, stratum 3, offset -0.002015, delay 0.02817
22 Dec 15:32:45 ntpdate[1234]: adjust time server 162.159.200.123 offset -0.002015 sec
```

### Database Location
- Database: `~/.config/website-blocker/blocker.db`
- Config: `~/.config/website-blocker/config.json`
- Logs: `~/.config/website-blocker/daemon.log`

### Debugging

```bash
# Check daemon status
systemctl status website-blocker

# View daemon logs
journalctl -u website-blocker -f

# Test API
curl http://127.0.0.1:8765/api/status

# Check Hyprland windows
hyprctl clients -j | jq '.[] | select(.class | contains("firefox"))'
```

## Security Considerations

1. **Daemon protection**: Refuses SIGTERM during lock, restarts automatically
2. **Extension heartbeat**: Browser closed if extension stops
3. **Time verification**: NTP check prevents time manipulation
4. **Lock mode**: Configuration frozen during blocks
5. **Fail-safe**: Network/DB errors result in blocking (not allowing)
6. **File permissions**: Config files owned by user, not writable by others

Note: Determined users with root access can always bypass. This is designed for self-control, not parental controls.

## API Reference

### Daemon API Endpoints

**GET /api/status**
```json
{
  "running": true,
  "locked": false,
  "active_rules": 5,
  "active_schedules": 1,
  "browsers_detected": 2,
  "browsers_compliant": 2
}
```

**GET /api/rules**
```json
[
  {
    "id": 1,
    "rule_type": "website",
    "target": "reddit.com",
    "enabled": true,
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

**POST /api/rules**
```json
{
  "rule_type": "website",
  "target": "twitter.com",
  "enabled": true
}
```

**POST /api/heartbeat**
```json
{
  "pid": 12345,
  "browser": "firefox",
  "incognito": false,
  "timestamp": 1705320000000
}
```

Response:
```json
{
  "status": "ok"
}
```

**GET /api/browsers**
```json
[
  {
    "pid": 12345,
    "browser": "firefox",
    "compliant": true,
    "last_heartbeat": "2025-01-15T10:30:00Z",
    "incognito_active": true
  }
]
```

## Conclusion

This specification provides a complete blueprint for building a robust website and application blocker for Arch Linux + Hyprland. The system is designed to be bypass-resistant while remaining user-friendly for legitimate configuration.

The three-component architecture (daemon, desktop app, extension) provides multiple layers of enforcement, and the lock mode ensures that once a blocking period starts, it cannot be easily circumvented.

Start with the daemon as the core component, then build the extension, and finally the desktop app for configuration. Test thoroughly at each stage before moving on.

Good luck with the implementation!
