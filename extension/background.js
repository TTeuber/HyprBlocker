/**
 * Website Blocker - Background Service Worker
 * Handles heartbeat, site blocking, and communication with the daemon.
 */

const DAEMON_URL = 'http://127.0.0.1:8765';
const HEARTBEAT_INTERVAL = 30000; // 30 seconds
const RULES_REFRESH_INTERVAL = 5000; // 5 seconds

let browserPID = null;
let blocksData = [];  // Array of {id, name, blocked[], allowed[]}
let heartbeatIntervalId = null;
let rulesRefreshIntervalId = null;

// Deduplication to prevent multiple redirects for same navigation
const BLOCK_CACHE_DURATION = 2000; // 2 seconds
const recentBlocks = new Map(); // Map<tabId, {url: string, timestamp: number}>

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

    const incognitoAllowed = await isAllowedIncognitoAccess();
    console.log('Extension incognito access:', incognitoAllowed ? 'ENABLED' : 'DISABLED');
    if (!incognitoAllowed) {
        console.warn('WARNING: Extension does not have incognito permission - browser will be NON-COMPLIANT');
    }

    startHeartbeat();
    startRulesRefresh();
}

/**
 * Get browser PID via native messaging
 */
async function getBrowserPID() {
    // Set fallback PID immediately so heartbeats work
    browserPID = hashCode(chrome.runtime.id + Date.now());
    console.log('Initial fallback PID:', browserPID);

    // Try to get real PID from native messaging (will override fallback if successful)
    try {
        const port = chrome.runtime.connectNative('com.websiteblocker.host');

        port.onMessage.addListener((message) => {
            if (message.pid) {
                browserPID = message.pid;
                console.log('✅ Using real browser PID from native host:', browserPID);
                console.log('Extension ID:', chrome.runtime.id);
            }
            if (message.error) {
                console.error('❌ Native host error:', message.error);
                console.warn('⚠️ Using fallback PID:', browserPID);
            }
        });

        port.onDisconnect.addListener(() => {
            if (chrome.runtime.lastError) {
                console.error('❌ Native messaging disconnected:', chrome.runtime.lastError.message);
                console.warn('⚠️ Using fallback PID:', browserPID, '- Browser may be killed!');
                console.info('ℹ️ Extension ID:', chrome.runtime.id);
                console.info('ℹ️ Check native messaging manifest for ID mismatch');
            }
        });

        port.postMessage({ action: 'get_pid' });
    } catch (error) {
        console.error('❌ Native messaging error:', error);
        console.warn('⚠️ Using fallback PID:', browserPID, '- Browser may be killed!');
        console.info('ℹ️ Extension ID:', chrome.runtime.id);
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
 * Count visible browser windows that the extension can see
 * Used to detect unmonitored profiles (guest profiles, etc.)
 */
async function getVisibleWindowCount() {
    try {
        // Only count 'normal' and large 'popup' windows
        // Excludes: devtools, panel, and tiny extension popups
        const windows = await chrome.windows.getAll({ windowTypes: ['normal', 'popup'] });
        let count = 0;
        for (const window of windows) {
            // Normal windows always count
            // Popup windows only count if they're large enough to be a real browser window
            if (window.type === 'normal' || (window.type === 'popup' && window.width > 400)) {
                count++;
            }
        }
        return count;
    } catch (error) {
        console.error('Failed to count windows:', error);
        return null; // Return null to indicate failure (not 0)
    }
}

/**
 * Check if any window is in incognito mode
 */
async function isIncognitoWindow() {
    try {
        const windows = await chrome.windows.getAll();

        // Check if ANY window is in incognito mode (not just focused)
        for (const window of windows) {
            if (window.incognito) {
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
 * Check if extension is allowed to run in incognito mode
 */
async function isAllowedIncognitoAccess() {
    return new Promise((resolve) => {
        try {
            chrome.extension.isAllowedIncognitoAccess((isAllowed) => {
                if (chrome.runtime.lastError) {
                    console.error('Failed to check incognito access:', chrome.runtime.lastError);
                    resolve(false);
                } else {
                    resolve(isAllowed);
                }
            });
        } catch (error) {
            console.error('Exception checking incognito access:', error);
            resolve(false);
        }
    });
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
    try {
        const isIncognito = await isIncognitoWindow();
        const incognitoAllowed = await isAllowedIncognitoAccess();
        const windowCount = await getVisibleWindowCount();

        const response = await fetch(`${DAEMON_URL}/api/heartbeat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pid: browserPID,
                browser: getBrowserName(),
                incognito: isIncognito,
                incognito_enabled: incognitoAllowed,
                extension_id: chrome.runtime.id,
                window_count: windowCount,
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

        blocksData = data.blocks || [];

        console.log('Blocks data updated:', blocksData.length, 'blocks');

        // Store in local storage for popup access
        chrome.storage.local.set({
            blocksData: blocksData
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
 * Check if URL (with path) matches a pattern
 * Supports:
 * - Domain matching: reddit.com matches www.reddit.com and reddit.com/anything
 * - Path-specific: youtube.com/shorts only matches that specific path
 * - Wildcard subdomains: *.reddit.com matches all subdomains
 */
function matchesPatternWithPath(urlPath, pattern) {
    urlPath = urlPath.toLowerCase();
    pattern = pattern.toLowerCase();

    // Remove protocol if present
    if (pattern.startsWith('http://')) {
        pattern = pattern.substring(7);
    } else if (pattern.startsWith('https://')) {
        pattern = pattern.substring(8);
    }

    // Remove trailing slash from pattern
    if (pattern.endsWith('/')) {
        pattern = pattern.slice(0, -1);
    }

    // Remove trailing slash from urlPath
    if (urlPath.endsWith('/')) {
        urlPath = urlPath.slice(0, -1);
    }

    // Handle wildcard subdomains (*.example.com)
    if (pattern.startsWith('*.')) {
        const domain = pattern.substring(2);
        const hostname = urlPath.split('/')[0];
        return hostname === domain || hostname.endsWith('.' + domain);
    }

    // Check if pattern includes path
    if (pattern.includes('/')) {
        // Path-specific matching with subdomain support
        // Split pattern into domain and path parts
        const patternParts = pattern.split('/');
        const patternDomain = patternParts[0];
        const patternPath = '/' + patternParts.slice(1).join('/');

        // Split URL into domain and path parts
        const urlParts = urlPath.split('/');
        const urlDomain = urlParts[0];
        const urlPathPart = '/' + urlParts.slice(1).join('/');

        // Check if domains match (with subdomain support like "www.twitch.tv" matches "twitch.tv")
        const domainsMatch = urlDomain === patternDomain ||
                            urlDomain.endsWith('.' + patternDomain);

        // Check if paths match (exact match or subpath)
        const pathsMatch = urlPathPart === patternPath ||
                          urlPathPart.startsWith(patternPath + '/') ||
                          urlPathPart.startsWith(patternPath + '?');

        return domainsMatch && pathsMatch;
    } else {
        // Domain-only pattern - match domain and all paths
        const hostname = urlPath.split('/')[0];
        const patternParts = pattern.split('/');
        const patternHostname = patternParts[0];

        // Exact hostname match or subdomain match
        return hostname === patternHostname ||
               hostname.endsWith('.' + patternHostname) ||
               urlPath.startsWith(patternHostname + '/');
    }
}

/**
 * Check if a URL should be blocked
 * Implements intersection-based allow logic: URL is allowed only if it appears
 * in the allow list of EVERY block that would otherwise block it.
 */
function shouldBlockUrl(url) {
    try {
        const urlObj = new URL(url);
        const hostname = urlObj.hostname;
        const fullPath = hostname + urlObj.pathname;

        // Find all blocks that would block this URL (ignoring allow lists)
        const blockingBlocks = [];

        for (const block of blocksData) {
            // Check if this block's blocked patterns match the URL
            for (const pattern of block.blocked) {
                if (matchesPatternWithPath(fullPath, pattern)) {
                    blockingBlocks.push(block);
                    break;  // This block would block it, move to next block
                }
            }
        }

        // If no blocks would block this URL, it's allowed
        if (blockingBlocks.length === 0) {
            return { blocked: false };
        }

        // Check if URL is in the allow list of EVERY blocking block
        for (const block of blockingBlocks) {
            let urlAllowedByThisBlock = false;

            for (const pattern of block.allowed) {
                if (matchesPatternWithPath(fullPath, pattern)) {
                    urlAllowedByThisBlock = true;
                    break;
                }
            }

            // If this blocking block doesn't allow the URL, it's blocked
            if (!urlAllowedByThisBlock) {
                console.log('🚫 URL blocked by block:', block.name, '→', url);
                return {
                    blocked: true,
                    blockName: block.name,
                    hostname: hostname
                };
            }
        }

        // URL is in the allow list of ALL blocking blocks
        console.log('✅ URL allowed by all blocking blocks →', url);
        return { blocked: false, allowed: true };

    } catch (error) {
        console.error('Invalid URL:', url);
        return { blocked: false };
    }
}

/**
 * Check if we should attempt to block a navigation
 * Returns false if we recently blocked this URL in this tab
 */
function shouldAttemptBlock(tabId, url) {
    const now = Date.now();
    const cached = recentBlocks.get(tabId);

    if (cached && cached.url === url) {
        const timeSinceBlock = now - cached.timestamp;
        if (timeSinceBlock < BLOCK_CACHE_DURATION) {
            console.log('⏭️ Skipping duplicate block (already blocked', timeSinceBlock, 'ms ago)');
            return false;
        }
    }

    return true;
}

/**
 * Record that we blocked a URL in a tab
 */
function recordBlock(tabId, url) {
    recentBlocks.set(tabId, {
        url: url,
        timestamp: Date.now()
    });

    // Clean up old entries to prevent memory leak
    if (recentBlocks.size > 100) {
        const cutoff = Date.now() - BLOCK_CACHE_DURATION;
        for (const [tid, block] of recentBlocks.entries()) {
            if (block.timestamp < cutoff) {
                recentBlocks.delete(tid);
            }
        }
    }
}

/**
 * Handle navigation blocking for any webNavigation event
 */
async function handleNavigationBlock(details, eventName) {
    // Only handle main frame navigation
    if (details.frameId !== 0) {
        return;
    }

    // Check deduplication cache
    if (!shouldAttemptBlock(details.tabId, details.url)) {
        return;
    }

    const result = shouldBlockUrl(details.url);

    if (result.blocked) {
        console.log(`🚫 [${eventName}] Blocking:`, result.hostname, 'matched pattern:', result.pattern);

        // Record this block to prevent duplicates
        recordBlock(details.tabId, details.url);

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
}

/**
 * PRIMARY: Catch navigation before it starts (URL bar, new tabs)
 */
chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
    await handleNavigationBlock(details, 'onBeforeNavigate');
});

/**
 * SECONDARY: Catch same-origin navigations that onBeforeNavigate misses
 */
chrome.webNavigation.onCommitted.addListener(async (details) => {
    await handleNavigationBlock(details, 'onCommitted');
});

/**
 * SAFETY NET: Catch anything that got committed but not blocked
 */
chrome.webNavigation.onDOMContentLoaded.addListener(async (details) => {
    await handleNavigationBlock(details, 'onDOMContentLoaded');
});

/**
 * CRITICAL: Catch SPA navigation (YouTube, Twitch, Reddit, etc.)
 * Fires when sites use history.pushState/replaceState for client-side routing
 */
chrome.webNavigation.onHistoryStateUpdated.addListener(async (details) => {
    await handleNavigationBlock(details, 'onHistoryStateUpdated');
});

/**
 * Clean up block cache when tabs are closed
 */
chrome.tabs.onRemoved.addListener((tabId) => {
    recentBlocks.delete(tabId);
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
