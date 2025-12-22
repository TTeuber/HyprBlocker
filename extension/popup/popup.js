/**
 * Website Blocker - Popup Script
 */

const DAEMON_URL = 'http://127.0.0.1:8765';

// DOM elements
const daemonIndicator = document.getElementById('daemon-indicator');
const daemonStatus = document.getElementById('daemon-status');
const extensionIndicator = document.getElementById('extension-indicator');
const extensionStatus = document.getElementById('extension-status');
const blockedCount = document.getElementById('blocked-count');
const browserPid = document.getElementById('browser-pid');
const lockStatus = document.getElementById('lock-status');
const refreshBtn = document.getElementById('refresh-btn');
const settingsBtn = document.getElementById('settings-btn');
const lastUpdate = document.getElementById('last-update');

/**
 * Update the daemon status display
 */
async function updateDaemonStatus() {
    try {
        const response = await fetch(`${DAEMON_URL}/api/status`);

        if (response.ok) {
            const status = await response.json();

            daemonIndicator.classList.remove('disconnected', 'warning');
            daemonIndicator.classList.add('connected');
            daemonStatus.textContent = 'Connected';

            // Update lock status
            if (status.locked) {
                lockStatus.textContent = 'Locked';
                lockStatus.classList.add('locked');
                lockStatus.classList.remove('unlocked');

                if (status.lock_end_time) {
                    const endTime = new Date(status.lock_end_time);
                    const now = new Date();
                    const diffMs = endTime - now;

                    if (diffMs > 0) {
                        const hours = Math.floor(diffMs / (1000 * 60 * 60));
                        const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                        lockStatus.textContent = `Locked (${hours}h ${minutes}m)`;
                    }
                }
            } else {
                lockStatus.textContent = 'Unlocked';
                lockStatus.classList.add('unlocked');
                lockStatus.classList.remove('locked');
            }
        } else {
            setDaemonDisconnected();
        }
    } catch (error) {
        console.error('Failed to fetch daemon status:', error);
        setDaemonDisconnected();
    }
}

/**
 * Set daemon status to disconnected
 */
function setDaemonDisconnected() {
    daemonIndicator.classList.remove('connected', 'warning');
    daemonIndicator.classList.add('disconnected');
    daemonStatus.textContent = 'Disconnected';
    lockStatus.textContent = '-';
    lockStatus.classList.remove('locked', 'unlocked');
}

/**
 * Update extension status from background script
 */
async function updateExtensionStatus() {
    try {
        const response = await chrome.runtime.sendMessage({ action: 'getStatus' });

        if (response) {
            extensionIndicator.classList.remove('disconnected', 'warning');
            extensionIndicator.classList.add('connected');
            extensionStatus.textContent = 'Active';

            blockedCount.textContent = response.blockedSitesCount || 0;
            browserPid.textContent = response.pid || '-';
        }
    } catch (error) {
        console.error('Failed to get extension status:', error);
        extensionIndicator.classList.remove('connected', 'warning');
        extensionIndicator.classList.add('disconnected');
        extensionStatus.textContent = 'Error';
    }
}

/**
 * Refresh rules from daemon
 */
async function refreshRules() {
    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Refreshing...';

    try {
        const response = await chrome.runtime.sendMessage({ action: 'refreshRules' });

        if (response && response.success) {
            blockedCount.textContent = response.count;
            lastUpdate.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
        }
    } catch (error) {
        console.error('Failed to refresh rules:', error);
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.textContent = 'Refresh Rules';
    }
}

/**
 * Open settings (desktop app or daemon URL)
 */
function openSettings() {
    // Try to open the desktop app, or fall back to daemon URL
    chrome.tabs.create({ url: `${DAEMON_URL}/docs` });
}

// Event listeners
refreshBtn.addEventListener('click', refreshRules);
settingsBtn.addEventListener('click', openSettings);

// Initial update
updateDaemonStatus();
updateExtensionStatus();

// Update every 5 seconds while popup is open
setInterval(() => {
    updateDaemonStatus();
    updateExtensionStatus();
}, 5000);
