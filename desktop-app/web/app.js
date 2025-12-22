/**
 * Website Blocker Desktop App - Main JavaScript
 */

// State
let isLocked = false;
let currentRules = [];
let currentSchedules = [];

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
    if (pageName === 'rules') refreshRules();
    if (pageName === 'schedules') refreshSchedules();
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

    // Add rule button
    document.getElementById('add-rule-btn').addEventListener('click', () => {
        openModal('add-rule-modal');
    });

    // Add schedule button
    document.getElementById('add-schedule-btn').addEventListener('click', () => {
        openModal('add-schedule-modal');
        populateRulesChecklist();
    });

    // Schedule type toggle
    document.getElementById('schedule-type').addEventListener('change', (e) => {
        const timeRangeFields = document.getElementById('time-range-fields');
        const lockedUntilFields = document.getElementById('locked-until-fields');

        if (e.target.value === 'time_range') {
            timeRangeFields.classList.remove('hidden');
            lockedUntilFields.classList.add('hidden');
        } else {
            timeRangeFields.classList.add('hidden');
            lockedUntilFields.classList.remove('hidden');
        }
    });

    // Refresh browsers button
    document.getElementById('refresh-browsers-btn').addEventListener('click', refreshBrowsers);
}

/**
 * Setup form handlers
 */
function setupForms() {
    // Quick add form
    document.getElementById('quick-add-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const type = document.getElementById('quick-add-type').value;
        const target = document.getElementById('quick-add-target').value;

        if (!target.trim()) {
            showToast('Please enter a target', 'error');
            return;
        }

        await addRule(type, target);
        document.getElementById('quick-add-target').value = '';
    });

    // Add rule form
    document.getElementById('add-rule-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const type = document.getElementById('rule-type').value;
        const target = document.getElementById('rule-target').value;
        const enabled = document.getElementById('rule-enabled').checked;

        await addRule(type, target, enabled);
        closeModal('add-rule-modal');
        document.getElementById('add-rule-form').reset();
    });

    // Add schedule form
    document.getElementById('add-schedule-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await addSchedule();
        closeModal('add-schedule-modal');
        document.getElementById('add-schedule-form').reset();
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
}

/**
 * Populate rules checklist in schedule modal
 */
function populateRulesChecklist() {
    const container = document.getElementById('schedule-rules-list');
    if (currentRules.length === 0) {
        container.innerHTML = '<p class="empty-message">No rules available. Create rules first.</p>';
        return;
    }

    container.innerHTML = currentRules.map(rule => `
        <label>
            <input type="checkbox" name="schedule-rules" value="${rule.id}">
            <span class="type-badge ${rule.rule_type}">${rule.rule_type}</span>
            ${escapeHtml(rule.target)}
        </label>
    `).join('');
}

/**
 * Refresh all data
 */
async function refreshAll() {
    await Promise.all([
        refreshStatus(),
        refreshRules(),
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
                `${status.active_rules} rules | ${status.active_schedules} schedules | ${status.browsers_compliant}/${status.browsers_detected} browsers`;

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
function updateLockState(locked, lockEndTime) {
    isLocked = locked;

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
        disableModifications();
    } else {
        lockBanner.classList.add('hidden');
        enableModifications();
    }
}

/**
 * Disable modification buttons when locked
 */
function disableModifications() {
    document.querySelectorAll('.btn-primary, .btn-danger').forEach(btn => {
        if (!btn.classList.contains('no-lock')) {
            btn.disabled = true;
        }
    });
}

/**
 * Enable modification buttons when unlocked
 */
function enableModifications() {
    document.querySelectorAll('.btn-primary, .btn-danger').forEach(btn => {
        btn.disabled = false;
    });
}

/**
 * Refresh rules list
 */
async function refreshRules() {
    try {
        currentRules = await pywebview.api.get_rules();
        renderRules();
    } catch (error) {
        console.error('Failed to refresh rules:', error);
    }
}

/**
 * Render rules table
 */
function renderRules() {
    const tbody = document.getElementById('rules-tbody');
    const empty = document.getElementById('rules-empty');
    const table = document.getElementById('rules-table');

    if (currentRules.length === 0) {
        table.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
    }

    table.classList.remove('hidden');
    empty.classList.add('hidden');

    tbody.innerHTML = currentRules.map(rule => `
        <tr>
            <td><span class="type-badge ${rule.rule_type}">${rule.rule_type}</span></td>
            <td>${escapeHtml(rule.target)}</td>
            <td><span class="status-badge ${rule.enabled ? 'enabled' : 'disabled'}">${rule.enabled ? 'Enabled' : 'Disabled'}</span></td>
            <td>${formatDate(rule.created_at)}</td>
            <td class="actions">
                <button class="btn btn-small btn-secondary" onclick="toggleRule(${rule.id}, ${!rule.enabled})">
                    ${rule.enabled ? 'Disable' : 'Enable'}
                </button>
                <button class="btn btn-small btn-danger" onclick="deleteRule(${rule.id})">Delete</button>
            </td>
        </tr>
    `).join('');
}

/**
 * Add a new rule
 */
async function addRule(type, target, enabled = true) {
    if (isLocked) {
        showToast('Cannot modify rules during lock period', 'warning');
        return;
    }

    try {
        const result = await pywebview.api.add_rule(type, target, enabled);
        if (result.success) {
            showToast('Rule added successfully', 'success');
            await refreshRules();
        } else {
            showToast(result.error || 'Failed to add rule', 'error');
        }
    } catch (error) {
        showToast('Failed to add rule', 'error');
    }
}

/**
 * Toggle a rule's enabled state
 */
async function toggleRule(ruleId, enabled) {
    if (isLocked) {
        showToast('Cannot modify rules during lock period', 'warning');
        return;
    }

    try {
        const result = await pywebview.api.update_rule(ruleId, { enabled: enabled });
        if (result.success) {
            await refreshRules();
        } else {
            showToast(result.error || 'Failed to update rule', 'error');
        }
    } catch (error) {
        showToast('Failed to update rule', 'error');
    }
}

/**
 * Delete a rule
 */
async function deleteRule(ruleId) {
    if (isLocked) {
        showToast('Cannot modify rules during lock period', 'warning');
        return;
    }

    if (!confirm('Are you sure you want to delete this rule?')) {
        return;
    }

    try {
        const result = await pywebview.api.delete_rule(ruleId);
        if (result.success) {
            showToast('Rule deleted', 'success');
            await refreshRules();
        } else {
            showToast(result.error || 'Failed to delete rule', 'error');
        }
    } catch (error) {
        showToast('Failed to delete rule', 'error');
    }
}

/**
 * Refresh schedules list
 */
async function refreshSchedules() {
    try {
        currentSchedules = await pywebview.api.get_schedules();
        renderSchedules();
    } catch (error) {
        console.error('Failed to refresh schedules:', error);
    }
}

/**
 * Render schedules table
 */
function renderSchedules() {
    const tbody = document.getElementById('schedules-tbody');
    const empty = document.getElementById('schedules-empty');
    const table = document.getElementById('schedules-table');

    if (currentSchedules.length === 0) {
        table.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
    }

    table.classList.remove('hidden');
    empty.classList.add('hidden');

    tbody.innerHTML = currentSchedules.map(schedule => {
        let details = '';
        if (schedule.schedule_type === 'time_range') {
            const days = schedule.days_of_week ? formatDays(JSON.parse(schedule.days_of_week)) : 'All days';
            details = `${days} ${schedule.start_time} - ${schedule.end_time}`;
        } else {
            details = `Until ${formatDate(schedule.locked_until)}`;
        }

        return `
            <tr>
                <td>${escapeHtml(schedule.name)}</td>
                <td><span class="type-badge">${schedule.schedule_type === 'time_range' ? 'Time Range' : 'Lock Until'}</span></td>
                <td>${details}</td>
                <td>${schedule.rule_ids.length} rules</td>
                <td><span class="status-badge ${schedule.enabled ? 'enabled' : 'disabled'}">${schedule.enabled ? 'Enabled' : 'Disabled'}</span></td>
                <td class="actions">
                    <button class="btn btn-small btn-secondary" onclick="toggleSchedule(${schedule.id}, ${!schedule.enabled})">
                        ${schedule.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button class="btn btn-small btn-danger" onclick="deleteSchedule(${schedule.id})">Delete</button>
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Add a new schedule
 */
async function addSchedule() {
    if (isLocked) {
        showToast('Cannot modify schedules during lock period', 'warning');
        return;
    }

    const name = document.getElementById('schedule-name').value;
    const scheduleType = document.getElementById('schedule-type').value;
    const enabled = document.getElementById('schedule-enabled').checked;

    // Get selected rules
    const ruleCheckboxes = document.querySelectorAll('input[name="schedule-rules"]:checked');
    const ruleIds = Array.from(ruleCheckboxes).map(cb => parseInt(cb.value));

    const data = {
        name: name,
        schedule_type: scheduleType,
        enabled: enabled,
        rule_ids: ruleIds
    };

    if (scheduleType === 'time_range') {
        const dayCheckboxes = document.querySelectorAll('input[name="days"]:checked');
        const days = Array.from(dayCheckboxes).map(cb => parseInt(cb.value));
        data.days_of_week = JSON.stringify(days);
        data.start_time = document.getElementById('schedule-start').value;
        data.end_time = document.getElementById('schedule-end').value;
    } else {
        const date = document.getElementById('schedule-date').value;
        const time = document.getElementById('schedule-time').value;
        if (date && time) {
            data.locked_until = `${date}T${time}:00`;
        }
    }

    try {
        const result = await pywebview.api.add_schedule(data);
        if (result.success) {
            showToast('Schedule added successfully', 'success');
            await refreshSchedules();
        } else {
            showToast(result.error || 'Failed to add schedule', 'error');
        }
    } catch (error) {
        showToast('Failed to add schedule', 'error');
    }
}

/**
 * Toggle a schedule's enabled state
 */
async function toggleSchedule(scheduleId, enabled) {
    if (isLocked) {
        showToast('Cannot modify schedules during lock period', 'warning');
        return;
    }

    try {
        const result = await pywebview.api.update_schedule(scheduleId, { enabled: enabled });
        if (result.success) {
            await refreshSchedules();
        } else {
            showToast(result.error || 'Failed to update schedule', 'error');
        }
    } catch (error) {
        showToast('Failed to update schedule', 'error');
    }
}

/**
 * Delete a schedule
 */
async function deleteSchedule(scheduleId) {
    if (isLocked) {
        showToast('Cannot modify schedules during lock period', 'warning');
        return;
    }

    if (!confirm('Are you sure you want to delete this schedule?')) {
        return;
    }

    try {
        const result = await pywebview.api.delete_schedule(scheduleId);
        if (result.success) {
            showToast('Schedule deleted', 'success');
            await refreshSchedules();
        } else {
            showToast(result.error || 'Failed to delete schedule', 'error');
        }
    } catch (error) {
        showToast('Failed to delete schedule', 'error');
    }
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
