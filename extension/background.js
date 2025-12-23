/**
 * Website Blocker - Background Service Worker
 * Handles heartbeat, site blocking, and communication with the daemon.
 */

const DAEMON_URL = 'http://127.0.0.1:8765';
const HEARTBEAT_INTERVAL = 30000; // 30 seconds
const RULES_REFRESH_INTERVAL = 60000; // 1 minute

let browserPID = null;
let blockedSites = [];
let allowedSites = [];
let heartbeatIntervalId = null;
let rulesRefreshIntervalId = null;

// Initialize on install
chrome.runtime.onInstalled.addListener(async () => {
    console.log('Website Blocker extension installed');
    await initialize();
});

// Initialize on browser startup
chrome.runtime.onStartup.addListener(async () => {
    console.log('Browser started - initializing Website Blocker');
    await initialize();
});

/**
 * Initialize the extension
 */
async function initialize() {
    await getBrowserPID();
    await fetchBlockedSites();
    startHeartbeat();
    startRulesRefresh();
}

/**
 * Get browser PID via native messaging
 */
async function getBrowserPID() {
    try {
        const port = chrome.runtime.connectNative('com.websiteblocker.host');

        port.onMessage.addListener((message) => {
            if (message.pid) {
                browserPID = message.pid;
                console.log('Browser PID:', browserPID);
            }
            if (message.error) {
                console.error('Native host error:', message.error);
            }
        });

        port.onDisconnect.addListener(() => {
            if (chrome.runtime.lastError) {
                console.warn('Native messaging disconnected:', chrome.runtime.lastError.message);
            }
        });

        port.postMessage({ action: 'get_pid' });
    } catch (error) {
        console.error('Failed to connect to native host:', error);
        // Use a fallback - generate a random ID based on extension ID
        browserPID = hashCode(chrome.runtime.id + Date.now());
        console.log('Using fallback PID:', browserPID);
    }
}

/**
 * Simple hash function for fallback PID generation
 */
function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return Math.abs(hash);
}

/**
 * Check if any window is in incognito mode
 */
async function isIncognitoWindow() {
    try {
        const windows = await chrome.windows.getAll();
        for (const window of windows) {
            if (window.focused && window.incognito) {
                return true;
            }
        }
        return false;
    } catch (error) {
        console.error('Failed to check incognito status:', error);
        return false;
    }
}

/**
 * Detect browser name from user agent
 */
function getBrowserName() {
    const userAgent = navigator.userAgent.toLowerCase();
    if (userAgent.includes('firefox')) return 'firefox';
    if (userAgent.includes('edg/')) return 'edge';
    if (userAgent.includes('brave')) return 'brave';
    if (userAgent.includes('chrome')) return 'chrome';
    if (userAgent.includes('chromium')) return 'chromium';
    if (userAgent.includes('opera') || userAgent.includes('opr/')) return 'opera';
    if (userAgent.includes('vivaldi')) return 'vivaldi';
    return 'unknown';
}

/**
 * Send heartbeat to daemon
 */
async function sendHeartbeat() {
    if (!browserPID) {
        console.warn('No browser PID available for heartbeat');
        return;
    }

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
            // Update badge to show connected
            chrome.action.setBadgeText({ text: '' });
            chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
        } else {
            console.error('Heartbeat failed:', response.status);
            chrome.action.setBadgeText({ text: '!' });
            chrome.action.setBadgeBackgroundColor({ color: '#F44336' });
        }
    } catch (error) {
        console.error('Failed to send heartbeat:', error);
        chrome.action.setBadgeText({ text: '!' });
        chrome.action.setBadgeBackgroundColor({ color: '#F44336' });
    }
}

/**
 * Start the heartbeat loop
 */
function startHeartbeat() {
    // Clear any existing interval
    if (heartbeatIntervalId) {
        clearInterval(heartbeatIntervalId);
    }

    // Send immediately
    sendHeartbeat();

    // Then send every 30 seconds
    heartbeatIntervalId = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
}

/**
 * Fetch blocked sites from daemon
 */
async function fetchBlockedSites() {
    try {
        const response = await fetch(`${DAEMON_URL}/api/blocked-sites`);

        if (!response.ok) {
            console.error('Failed to fetch blocked sites:', response.status);
            return;
        }

        const data = await response.json();

        blockedSites = data.blocked || [];
        allowedSites = data.allowed || [];

        console.log('Blocked sites updated:', blockedSites.length, 'patterns');
        console.log('Allowed sites:', allowedSites.length, 'patterns');

        // Store in local storage for popup access
        chrome.storage.local.set({
            blockedSites: blockedSites,
            allowedSites: allowedSites
        });

    } catch (error) {
        console.error('Failed to fetch blocked sites:', error);
    }
}

/**
 * Start the rules refresh loop
 */
function startRulesRefresh() {
    // Clear any existing interval
    if (rulesRefreshIntervalId) {
        clearInterval(rulesRefreshIntervalId);
    }

    // Refresh every minute
    rulesRefreshIntervalId = setInterval(fetchBlockedSites, RULES_REFRESH_INTERVAL);
}

/**
 * Check if hostname matches a blocking pattern
 */
function matchesPattern(hostname, pattern) {
    hostname = hostname.toLowerCase();
    pattern = pattern.toLowerCase();

    // Remove protocol if present
    if (pattern.startsWith('http://')) {
        pattern = pattern.substring(7);
    } else if (pattern.startsWith('https://')) {
        pattern = pattern.substring(8);
    }

    // Remove trailing slash and path
    pattern = pattern.split('/')[0];

    // Exact match
    if (hostname === pattern) {
        return true;
    }

    // Wildcard subdomain (*.example.com)
    if (pattern.startsWith('*.')) {
        const domain = pattern.substring(2);
        return hostname === domain || hostname.endsWith('.' + domain);
    }

    // Subdomain match (example.com matches www.example.com)
    if (hostname.endsWith('.' + pattern)) {
        return true;
    }

    return false;
}

/**
 * Check if a URL should be blocked
 */
function shouldBlockUrl(url) {
    try {
        const urlObj = new URL(url);
        const hostname = urlObj.hostname;

        for (const pattern of blockedSites) {
            if (matchesPattern(hostname, pattern)) {
                return { blocked: true, pattern: pattern, hostname: hostname };
            }
        }

        return { blocked: false };
    } catch (error) {
        console.error('Invalid URL:', url);
        return { blocked: false };
    }
}

/**
 * Handle navigation events - block if necessary
 */
chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
    // Only handle main frame navigation
    if (details.frameId !== 0) {
        return;
    }

    const result = shouldBlockUrl(details.url);

    if (result.blocked) {
        console.log('Blocking:', result.hostname, 'matched pattern:', result.pattern);

        // Redirect to blocked page
        const blockedUrl = chrome.runtime.getURL('blocked.html') +
            '?url=' + encodeURIComponent(details.url) +
            '&site=' + encodeURIComponent(result.hostname);

        try {
            await chrome.tabs.update(details.tabId, { url: blockedUrl });
        } catch (error) {
            console.error('Failed to redirect to blocked page:', error);
        }
    }
});

/**
 * Handle messages from popup or content scripts
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'getStatus') {
        sendResponse({
            pid: browserPID,
            browser: getBrowserName(),
            blockedSitesCount: blockedSites.length,
            daemonUrl: DAEMON_URL
        });
    } else if (message.action === 'refreshRules') {
        fetchBlockedSites().then(() => {
            sendResponse({ success: true, count: blockedSites.length });
        });
        return true; // Keep channel open for async response
    } else if (message.action === 'checkUrl') {
        const result = shouldBlockUrl(message.url);
        sendResponse(result);
    }
});

/**
 * Handle alarms for periodic tasks (more reliable than setInterval in service workers)
 */
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'heartbeat') {
        sendHeartbeat();
    } else if (alarm.name === 'refreshRules') {
        fetchBlockedSites();
    }
});

// Create alarms for periodic tasks
chrome.alarms.create('heartbeat', { periodInMinutes: 0.5 }); // 30 seconds
chrome.alarms.create('refreshRules', { periodInMinutes: 1 }); // 1 minute

// Initial setup when service worker starts
initialize();
