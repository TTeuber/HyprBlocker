/**
 * Website Blocker Desktop App - Main JavaScript
 */

// State
let currentBlocks = [];
let gracePeriodInterval = null;
let modalEditingBlockId = null; // null = add mode, number = edit mode

// DOM Elements
const pages = document.querySelectorAll('.page');
const navItems = document.querySelectorAll('.nav-item');
const lockBanner = document.getElementById('lock-banner');
const lockTimer = document.getElementById('lock-timer');
const daemonStatus = document.getElementById('daemon-status');
const toastContainer = document.getElementById('toast-container');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    setupNavigation();
    setupModals();
    setupForms();
    await refreshAll();

    // Refresh data every 5 seconds
    setInterval(refreshAll, 5000);
});

/**
 * Setup navigation
 */
function setupNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            showPage(page);
        });
    });
}

/**
 * Show a specific page
 */
function showPage(pageName) {
    pages.forEach(p => p.classList.remove('active'));
    navItems.forEach(n => n.classList.remove('active'));

    const page = document.getElementById(`page-${pageName}`);
    const navItem = document.querySelector(`[data-page="${pageName}"]`);

    if (page) page.classList.add('active');
    if (navItem) navItem.classList.add('active');

    // Refresh data when switching pages
    if (pageName === 'blocks') refreshBlocks();
    if (pageName === 'stats') refreshStats();
    if (pageName === 'browsers') refreshBrowsers();
}

/**
 * Setup modal handlers
 */
function setupModals() {
    // Close buttons
    document.querySelectorAll('[data-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.dataset.modal;
            closeModal(modalId);
        });
    });

    // Add block button
    document.getElementById('add-block-btn').addEventListener('click', () => {
        // Reset to add mode
        modalEditingBlockId = null;
        document.querySelector('#add-block-modal h3').textContent = 'Add Block';
        document.querySelector('#add-block-form button[type="submit"]').textContent = 'Add Block';
        document.getElementById('add-block-form').reset();

        openModal('add-block-modal');
    });

    // Block mode toggle
    document.getElementById('block-mode').addEventListener('change', (e) => {
        const blockTimeFields = document.getElementById('block-time-fields');
        if (e.target.value === 'time_range') {
            blockTimeFields.classList.remove('hidden');
        } else {
            blockTimeFields.classList.add('hidden');
        }
    });

    // Lock mode toggle
    document.getElementById('lock-mode').addEventListener('change', (e) => {
        const lockTimeFields = document.getElementById('lock-time-fields');
        const lockUntilFields = document.getElementById('lock-until-fields');

        lockTimeFields.classList.add('hidden');
        lockUntilFields.classList.add('hidden');

        if (e.target.value === 'time_range') {
            lockTimeFields.classList.remove('hidden');
        } else if (e.target.value === 'locked_until') {
            lockUntilFields.classList.remove('hidden');
        }
    });

    // Refresh browsers button
    document.getElementById('refresh-browsers-btn').addEventListener('click', refreshBrowsers);

    // Add extension button
    const addExtensionBtn = document.getElementById('add-extension-btn');
    if (addExtensionBtn) {
        addExtensionBtn.addEventListener('click', startExtensionGracePeriod);
    }
}

/**
 * Setup form handlers
 */
function setupForms() {
    // Add block form
    document.getElementById('add-block-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        if (modalEditingBlockId !== null) {
            // Edit mode
            await updateBlock(modalEditingBlockId);
        } else {
            // Add mode
            await addBlock();
        }

        closeModal('add-block-modal');
        document.getElementById('add-block-form').reset();
        modalEditingBlockId = null; // Reset to add mode
    });
}

/**
 * Open a modal
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('hidden');
}

/**
 * Close a modal
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('hidden');

    // Reset modal to add mode
    if (modalId === 'add-block-modal') {
        modalEditingBlockId = null;
        document.querySelector('#add-block-modal h3').textContent = 'Add Block';
        document.querySelector('#add-block-form button[type="submit"]').textContent = 'Add Block';
        document.getElementById('add-block-form').reset();

        // Hide conditional fields
        document.getElementById('block-time-fields').classList.add('hidden');
        document.getElementById('lock-time-fields').classList.add('hidden');
        document.getElementById('lock-until-fields').classList.add('hidden');
    }
}

/**
 * Refresh all data
 */
async function refreshAll() {
    await Promise.all([
        refreshStatus(),
        refreshStats()
    ]);
}

/**
 * Refresh daemon status
 */
async function refreshStatus() {
    try {
        const status = await pywebview.api.get_status();

        if (status.running) {
            updateDaemonStatus(true);
            updateLockState(status.locked, status.lock_end_time);

            document.getElementById('status-text').textContent = status.locked ? 'Locked' : 'Active';
            document.getElementById('status-details').textContent =
                `${status.active_blocks} blocks | ${status.browsers_compliant}/${status.browsers_detected} browsers`;

            document.getElementById('settings-daemon-status').textContent = 'Running';
        } else {
            updateDaemonStatus(false);
            document.getElementById('status-text').textContent = 'Daemon Not Running';
            document.getElementById('settings-daemon-status').textContent = 'Not Running';
        }
    } catch (error) {
        console.error('Failed to refresh status:', error);
        updateDaemonStatus(false);
    }
}

/**
 * Update daemon status indicator
 */
function updateDaemonStatus(connected) {
    const indicator = daemonStatus.querySelector('.status-indicator');
    const text = daemonStatus.querySelector('.status-text');

    if (connected) {
        indicator.classList.add('connected');
        indicator.classList.remove('disconnected');
        text.textContent = 'Connected';
    } else {
        indicator.classList.remove('connected');
        indicator.classList.add('disconnected');
        text.textContent = 'Disconnected';
    }
}

/**
 * Update lock state UI
 */
async function updateLockState(locked, lockEndTime) {
    if (locked) {
        lockBanner.classList.remove('hidden');
        if (lockEndTime) {
            const endTime = new Date(lockEndTime);
            const now = new Date();
            const diffMs = endTime - now;

            if (diffMs > 0) {
                const hours = Math.floor(diffMs / (1000 * 60 * 60));
                const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                lockTimer.textContent = `Unlocks in ${hours}h ${minutes}m`;
            }
        }
    } else {
        lockBanner.classList.add('hidden');
    }

    // Refresh blocks to update per-block lock status
    await refreshBlocks();
}

/**
 * Refresh blocks list
 */
async function refreshBlocks() {
    try {
        currentBlocks = await pywebview.api.get_blocks();
        renderBlocks();
    } catch (error) {
        console.error('Failed to refresh blocks:', error);
    }
}

/**
 * Render blocks table
 */
function renderBlocks() {
    const tbody = document.getElementById('blocks-tbody');
    const empty = document.getElementById('blocks-empty');
    const table = document.getElementById('blocks-table');

    if (currentBlocks.length === 0) {
        table.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
    }

    try {
        table.classList.remove('hidden');
        empty.classList.add('hidden');

        tbody.innerHTML = currentBlocks.map(block => {
            try {
                let blockDetails = formatBlockMode(block);
                let lockDetails = formatLockMode(block);

                // Count rules from text fields
                const websitesCount = block.websites_blocked ? block.websites_blocked.split('\n').filter(s => s.trim()).length : 0;
                const appsCount = block.apps_blocked ? block.apps_blocked.split('\n').filter(s => s.trim()).length : 0;
                const totalRules = websitesCount + appsCount;

                return `
                    <tr>
                        <td>${escapeHtml(block.name)}</td>
                        <td>${blockDetails}</td>
                        <td>${lockDetails}</td>
                        <td>${totalRules} rules</td>
                        <td><span class="status-badge ${block.enabled ? 'enabled' : 'disabled'}">${block.enabled ? 'Enabled' : 'Disabled'}</span></td>
                        <td class="actions">
                            <button class="btn btn-small btn-secondary" onclick="editBlock(${block.id})">Edit</button>
                            <button class="btn btn-small btn-secondary" onclick="toggleBlock(${block.id}, ${!block.enabled})">
                                ${block.enabled ? 'Disable' : 'Enable'}
                            </button>
                            <button class="btn btn-small btn-danger" onclick="deleteBlock(${block.id})">Delete</button>
                        </td>
                    </tr>
                `;
            } catch (rowError) {
                console.error('Error rendering block row:', block.id, rowError);
                return `<tr><td colspan="6">Error rendering block: ${escapeHtml(block.name)}</td></tr>`;
            }
        }).join('');
    } catch (error) {
        console.error('Error rendering blocks table:', error);
        showToast('Error displaying blocks. Check console for details.', 'error');
        table.classList.add('hidden');
        empty.classList.remove('hidden');
    }
}

/**
 * Safely parse JSON with fallback
 */
function safeParseJSON(value, defaultValue = null) {
    if (!value) return defaultValue;

    // If already parsed (is an object/array), return it
    if (typeof value === 'object') return value;

    // Try to parse string
    try {
        return JSON.parse(value);
    } catch (e) {
        console.warn('Failed to parse JSON:', value, e);
        return defaultValue;
    }
}

/**
 * Format block mode for display
 */
function formatBlockMode(block) {
    if (block.block_mode === 'always') {
        return '<span class="type-badge">Always</span>';
    } else if (block.block_mode === 'time_range') {
        const daysArray = safeParseJSON(block.block_days_of_week, []);
        const days = daysArray.length > 0 ? formatDays(daysArray) : 'All days';
        return `<span class="type-badge">Time Range</span><br><small>${days} ${block.block_start_time || ''} - ${block.block_end_time || ''}</small>`;
    } else {
        return '<span class="type-badge disabled">Disabled</span>';
    }
}

/**
 * Format lock mode for display
 */
function formatLockMode(block) {
    if (block.lock_mode === 'none') {
        return '<span class="type-badge">No Lock</span>';
    } else if (block.lock_mode === 'time_range') {
        const daysArray = safeParseJSON(block.lock_days_of_week, []);
        const days = daysArray.length > 0 ? formatDays(daysArray) : 'All days';
        return `<span class="type-badge">Time Lock</span><br><small>${days} ${block.lock_start_time || ''} - ${block.lock_end_time || ''}</small>`;
    } else if (block.lock_mode === 'locked_until') {
        return `<span class="type-badge">Lock Until</span><br><small>${formatDate(block.lock_until)}</small>`;
    }
    return '-';
}

/**
 * Add a new block
 */
async function addBlock() {
    const name = document.getElementById('block-name').value;
    const blockMode = document.getElementById('block-mode').value;
    const lockMode = document.getElementById('lock-mode').value;
    const enabled = document.getElementById('block-enabled').checked;

    // Get rules from text areas
    const websitesBlocked = document.getElementById('websites-blocked').value.trim() || null;
    const websitesAllowed = document.getElementById('websites-allowed').value.trim() || null;
    const appsBlocked = document.getElementById('apps-blocked').value.trim() || null;
    const appsAllowed = document.getElementById('apps-allowed').value.trim() || null;

    const data = {
        name: name,
        block_mode: blockMode,
        lock_mode: lockMode,
        enabled: enabled,
        websites_blocked: websitesBlocked,
        websites_allowed: websitesAllowed,
        apps_blocked: appsBlocked,
        apps_allowed: appsAllowed
    };

    // Block time range
    if (blockMode === 'time_range') {
        const dayCheckboxes = document.querySelectorAll('input[name="block-days"]:checked');
        const days = Array.from(dayCheckboxes).map(cb => parseInt(cb.value));
        data.block_days_of_week = JSON.stringify(days);
        data.block_start_time = document.getElementById('block-start').value;
        data.block_end_time = document.getElementById('block-end').value;
    }

    // Lock time range
    if (lockMode === 'time_range') {
        const dayCheckboxes = document.querySelectorAll('input[name="lock-days"]:checked');
        const days = Array.from(dayCheckboxes).map(cb => parseInt(cb.value));
        data.lock_days_of_week = JSON.stringify(days);
        data.lock_start_time = document.getElementById('lock-start').value;
        data.lock_end_time = document.getElementById('lock-end').value;
    } else if (lockMode === 'locked_until') {
        const date = document.getElementById('lock-date').value;
        const time = document.getElementById('lock-time').value;
        if (date && time) {
            data.lock_until = `${date}T${time}:00`;
        }
    }

    try {
        const result = await pywebview.api.add_block(data);
        if (result.success) {
            showToast('Block added successfully', 'success');
            await refreshBlocks();
        } else {
            showToast(result.error || 'Failed to add block', 'error');
        }
    } catch (error) {
        showToast('Failed to add block', 'error');
    }
}

/**
 * Update an existing block
 */
async function updateBlock(blockId) {
    const name = document.getElementById('block-name').value;
    const blockMode = document.getElementById('block-mode').value;
    const lockMode = document.getElementById('lock-mode').value;
    const enabled = document.getElementById('block-enabled').checked;

    // Get rules from text areas
    const websitesBlocked = document.getElementById('websites-blocked').value.trim() || null;
    const websitesAllowed = document.getElementById('websites-allowed').value.trim() || null;
    const appsBlocked = document.getElementById('apps-blocked').value.trim() || null;
    const appsAllowed = document.getElementById('apps-allowed').value.trim() || null;

    const data = {
        name: name,
        block_mode: blockMode,
        lock_mode: lockMode,
        enabled: enabled,
        websites_blocked: websitesBlocked,
        websites_allowed: websitesAllowed,
        apps_blocked: appsBlocked,
        apps_allowed: appsAllowed
    };

    // Block time range
    if (blockMode === 'time_range') {
        const dayCheckboxes = document.querySelectorAll('input[name="block-days"]:checked');
        const days = Array.from(dayCheckboxes).map(cb => parseInt(cb.value));
        data.block_days_of_week = JSON.stringify(days);
        data.block_start_time = document.getElementById('block-start').value;
        data.block_end_time = document.getElementById('block-end').value;
    }

    // Lock time range
    if (lockMode === 'time_range') {
        const dayCheckboxes = document.querySelectorAll('input[name="lock-days"]:checked');
        const days = Array.from(dayCheckboxes).map(cb => parseInt(cb.value));
        data.lock_days_of_week = JSON.stringify(days);
        data.lock_start_time = document.getElementById('lock-start').value;
        data.lock_end_time = document.getElementById('lock-end').value;
    } else if (lockMode === 'locked_until') {
        const date = document.getElementById('lock-date').value;
        const time = document.getElementById('lock-time').value;
        if (date && time) {
            data.lock_until = `${date}T${time}:00`;
        }
    }

    try {
        const result = await pywebview.api.update_block(blockId, data);
        if (result.success) {
            showToast('Block updated successfully', 'success');
            await refreshBlocks();
        } else {
            showToast(result.error || 'Failed to update block', 'error');
        }
    } catch (error) {
        console.error('Update block error:', error);
        showToast('Failed to update block', 'error');
    }
}

/**
 * Toggle a block's enabled state
 */
async function toggleBlock(blockId, enabled) {
    try {
        // Check if block is locked
        const lockStatus = await pywebview.api.get_block_lock_status(blockId);
        if (lockStatus.locked) {
            showToast('This block is currently locked', 'warning');
            return;
        }

        const result = await pywebview.api.update_block(blockId, { enabled: enabled });
        if (result.success) {
            await refreshBlocks();
        } else {
            showToast(result.error || 'Failed to update block', 'error');
        }
    } catch (error) {
        showToast('Failed to update block', 'error');
    }
}

/**
 * Delete a block
 */
async function deleteBlock(blockId) {
    try {
        // Check if block is locked
        const lockStatus = await pywebview.api.get_block_lock_status(blockId);
        if (lockStatus.locked) {
            showToast('This block is currently locked', 'warning');
            return;
        }

        if (!confirm('Are you sure you want to delete this block?')) {
            return;
        }

        const result = await pywebview.api.delete_block(blockId);
        if (result.success) {
            showToast('Block deleted', 'success');
            await refreshBlocks();
        } else {
            showToast(result.error || 'Failed to delete block', 'error');
        }
    } catch (error) {
        showToast('Failed to delete block', 'error');
    }
}

/**
 * Edit a block
 */
async function editBlock(blockId) {
    try {
        // Check if block is locked
        const lockStatus = await pywebview.api.get_block_lock_status(blockId);
        if (lockStatus.locked) {
            showToast('This block is currently locked', 'warning');
            return;
        }

        // Find block in currentBlocks array
        const block = currentBlocks.find(b => b.id === blockId);
        if (!block) {
            showToast('Block not found', 'error');
            return;
        }

        // Set modal to edit mode
        modalEditingBlockId = blockId;

        // Update modal UI
        document.querySelector('#add-block-modal h3').textContent = 'Edit Block';
        document.querySelector('#add-block-form button[type="submit"]').textContent = 'Save Changes';

        // Populate basic fields
        document.getElementById('block-name').value = block.name;
        document.getElementById('block-mode').value = block.block_mode;
        document.getElementById('lock-mode').value = block.lock_mode;
        document.getElementById('block-enabled').checked = block.enabled;

        // Populate block time range fields
        if (block.block_mode === 'time_range') {
            document.getElementById('block-time-fields').classList.remove('hidden');

            // Parse and check block days
            const blockDays = safeParseJSON(block.block_days_of_week, []);
            document.querySelectorAll('input[name="block-days"]').forEach(checkbox => {
                checkbox.checked = blockDays.includes(parseInt(checkbox.value));
            });

            document.getElementById('block-start').value = block.block_start_time || '09:00';
            document.getElementById('block-end').value = block.block_end_time || '17:00';
        } else {
            document.getElementById('block-time-fields').classList.add('hidden');
        }

        // Populate lock time range fields
        if (block.lock_mode === 'time_range') {
            document.getElementById('lock-time-fields').classList.remove('hidden');
            document.getElementById('lock-until-fields').classList.add('hidden');

            const lockDays = safeParseJSON(block.lock_days_of_week, []);
            document.querySelectorAll('input[name="lock-days"]').forEach(checkbox => {
                checkbox.checked = lockDays.includes(parseInt(checkbox.value));
            });

            document.getElementById('lock-start').value = block.lock_start_time || '09:00';
            document.getElementById('lock-end').value = block.lock_end_time || '17:00';
        } else if (block.lock_mode === 'locked_until') {
            document.getElementById('lock-time-fields').classList.add('hidden');
            document.getElementById('lock-until-fields').classList.remove('hidden');

            // Parse lock_until datetime (format: "2024-01-15T17:00:00")
            if (block.lock_until) {
                const lockDate = new Date(block.lock_until);
                const dateStr = lockDate.toISOString().split('T')[0];
                const timeStr = lockDate.toTimeString().slice(0, 5);
                document.getElementById('lock-date').value = dateStr;
                document.getElementById('lock-time').value = timeStr;
            }
        } else {
            document.getElementById('lock-time-fields').classList.add('hidden');
            document.getElementById('lock-until-fields').classList.add('hidden');
        }

        // Populate text areas (websites/apps)
        document.getElementById('websites-blocked').value = block.websites_blocked || '';
        document.getElementById('websites-allowed').value = block.websites_allowed || '';
        document.getElementById('apps-blocked').value = block.apps_blocked || '';
        document.getElementById('apps-allowed').value = block.apps_allowed || '';

        // Open modal
        openModal('add-block-modal');

    } catch (error) {
        console.error('Failed to edit block:', error);
        showToast('Failed to load block for editing', 'error');
    }
}

/**
 * Start extension grace period
 */
async function startExtensionGracePeriod() {
    try {
        const result = await pywebview.api.start_extension_grace_period();

        if (result.success) {
            showToast('Grace period started - you have 30 seconds to add the extension', 'success');
            showGracePeriodBanner(result.remaining_seconds);
        } else {
            showToast(result.error || 'Failed to start grace period', 'error');
        }
    } catch (error) {
        console.error('Failed to start grace period:', error);
        showToast('Failed to start grace period', 'error');
    }
}

/**
 * Show grace period banner with countdown
 */
function showGracePeriodBanner(seconds) {
    const banner = document.getElementById('grace-period-banner');
    const timer = document.getElementById('grace-timer');

    if (!banner || !timer) return;

    banner.classList.remove('hidden');
    timer.textContent = `${seconds}s`;

    // Clear any existing interval
    if (gracePeriodInterval) {
        clearInterval(gracePeriodInterval);
    }

    let remaining = seconds;
    gracePeriodInterval = setInterval(() => {
        remaining--;
        timer.textContent = `${remaining}s`;

        if (remaining <= 0) {
            clearInterval(gracePeriodInterval);
            gracePeriodInterval = null;
            banner.classList.add('hidden');
            showToast('Grace period ended', 'info');
        }
    }, 1000);
}

/**
 * Refresh statistics
 */
async function refreshStats() {
    try {
        const stats = await pywebview.api.get_stats();

        // Dashboard stats
        document.getElementById('stat-websites').textContent = stats.websites_blocked_today || 0;
        document.getElementById('stat-apps').textContent = stats.apps_closed_today || 0;
        document.getElementById('stat-browsers').textContent = stats.browsers_killed_today || 0;

        // Stats page
        document.getElementById('stats-today').textContent = stats.total_blocks_today || 0;
        document.getElementById('stats-week').textContent = stats.total_blocks_week || 0;
        document.getElementById('stats-month').textContent = stats.total_blocks_month || 0;

        // Breakdown
        const breakdown = document.getElementById('stats-breakdown');
        breakdown.innerHTML = `
            <div class="breakdown-item">
                <span>Websites Blocked</span>
                <strong>${stats.websites_blocked_today || 0}</strong>
            </div>
            <div class="breakdown-item">
                <span>Apps Closed</span>
                <strong>${stats.apps_closed_today || 0}</strong>
            </div>
            <div class="breakdown-item">
                <span>Browsers Killed</span>
                <strong>${stats.browsers_killed_today || 0}</strong>
            </div>
        `;
    } catch (error) {
        console.error('Failed to refresh stats:', error);
    }
}

/**
 * Refresh browser list
 */
async function refreshBrowsers() {
    try {
        const browsers = await pywebview.api.get_browsers();

        // Dashboard browser list
        const browserList = document.getElementById('browser-list');
        if (browsers.length === 0) {
            browserList.innerHTML = '<p class="empty-message">No browsers detected</p>';
        } else {
            browserList.innerHTML = browsers.map(b => `
                <div class="browser-item">
                    <span class="browser-icon">${getBrowserIcon(b.browser)}</span>
                    <span class="browser-name">${capitalizeFirst(b.browser)}</span>
                    <span class="browser-status ${b.compliant ? '' : 'inactive'}">
                        ${b.compliant ? 'Active' : 'No Extension'}
                    </span>
                </div>
            `).join('');
        }

        // Browsers page grid
        const browsersGrid = document.getElementById('browsers-grid');
        if (browsers.length === 0) {
            browsersGrid.innerHTML = '<p class="empty-message">No browsers detected. Start a browser with the extension installed.</p>';
        } else {
            browsersGrid.innerHTML = browsers.map(b => `
                <div class="browser-card">
                    <div class="browser-card-header">
                        <span class="browser-icon" style="font-size: 24px">${getBrowserIcon(b.browser)}</span>
                        <h4>${capitalizeFirst(b.browser)}</h4>
                        <span class="status-badge ${b.compliant ? 'enabled' : 'disabled'}">
                            ${b.compliant ? 'Compliant' : 'Non-compliant'}
                        </span>
                    </div>
                    <div class="browser-card-details">
                        <p><strong>PID:</strong> ${b.pid}</p>
                        <p><strong>Last Heartbeat:</strong> ${formatTime(b.last_heartbeat)}</p>
                        <p><strong>Incognito Active:</strong> ${b.incognito_active ? 'Yes' : 'No'}</p>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to refresh browsers:', error);
    }
}

/**
 * Get browser icon
 */
function getBrowserIcon(browser) {
    const icons = {
        'firefox': '&#128293;',
        'chrome': '&#128308;',
        'chromium': '&#128309;',
        'brave': '&#129409;',
        'edge': '&#128310;',
        'opera': '&#127925;',
        'vivaldi': '&#127926;'
    };
    return icons[browser.toLowerCase()] || '&#127760;';
}

/**
 * Show a toast notification
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format date string
 */
function formatDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return dateStr;
    }
}

/**
 * Format time string
 */
function formatTime(dateStr) {
    if (!dateStr) return '-';
    try {
        const date = new Date(dateStr);
        return date.toLocaleTimeString();
    } catch (e) {
        return dateStr;
    }
}

/**
 * Format days of week
 */
function formatDays(days) {
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    if (days.length === 7) return 'Every day';
    if (days.length === 5 && !days.includes(5) && !days.includes(6)) return 'Weekdays';
    if (days.length === 2 && days.includes(5) && days.includes(6)) return 'Weekends';
    return days.map(d => dayNames[d]).join(', ');
}

/**
 * Capitalize first letter
 */
function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
