// JavaScript for job restart manager
let eventSource = null;

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    refreshJobs();
    setupEventListeners();
    setupTabNavigation();
    startProgressUpdates();
    checkRcloneStatus();
});

// Setup event listeners
function setupEventListeners() {
    // Action buttons
    document.getElementById('restart-all-failed').addEventListener('click', restartAllFailedJobs);
    document.getElementById('refresh-jobs').addEventListener('click', refreshJobs);
    document.getElementById('create-job').addEventListener('click', showCreateModal);
    
    // Create job form
    document.getElementById('create-job-form').addEventListener('submit', handleCreateJob);
    
    // Rsync options for command preview
    const rsyncInputs = document.querySelectorAll('input[name^="rsync_"], input[name="archive"], input[name="verbose"], input[name="human_readable"], input[name="progress"], input[name="compress"], input[name="delete"], input[name="remove_source_files"], input[name="dry_run"], input[name="checksum"], input[name="stats"], input[name="itemize_changes"], input[name="inplace"], input[name="sparse"], input[name="whole_file"], input[name="update"], input[name="ignore_existing"], input[name="bwlimit"], input[name="partial_dir"]');
    rsyncInputs.forEach(input => {
        input.addEventListener('change', updateCommandPreview);
        input.addEventListener('input', updateCommandPreview);
    });
    
    // Remove source files checkbox - show/hide confirmation
    document.getElementById('remove-source-files').addEventListener('change', function() {
        const confirmationDiv = document.getElementById('delete-confirmation');
        if (this.checked) {
            confirmationDiv.style.display = 'block';
        } else {
            confirmationDiv.style.display = 'none';
            document.getElementById('delete-confirmation-input').value = '';
            updateConfirmationStatus();
        }
    });
    
    // Delete confirmation input - real-time validation
    document.getElementById('delete-confirmation-input').addEventListener('input', updateConfirmationStatus);
    
    // Source/destination changes
    document.getElementById('job-source').addEventListener('input', updateCommandPreview);
    document.getElementById('job-destination').addEventListener('input', updateCommandPreview);
    document.getElementById('job-excludes').addEventListener('input', updateCommandPreview);
    
    // Rclone buttons
    if (document.getElementById('create-rclone-operation')) {
        document.getElementById('create-rclone-operation').addEventListener('click', showRcloneModal);
    }
    if (document.getElementById('rclone-status')) {
        document.getElementById('rclone-status').addEventListener('click', checkRcloneStatus);
    }
    
    // Rclone form
    if (document.getElementById('rclone-operation-form')) {
        document.getElementById('rclone-operation-form').addEventListener('submit', handleCreateRcloneOperation);
    }
    
    // Rclone options for command preview - all checkboxes and text inputs
    const rcloneCheckboxes = document.querySelectorAll('#rclone-operation-form input[type="checkbox"]');
    rcloneCheckboxes.forEach(input => {
        input.addEventListener('change', updateRcloneCommandPreview);
    });
    
    const rcloneTextInputs = document.querySelectorAll('#rclone-operation-form input[type="text"], #rclone-operation-form input[type="number"]');
    rcloneTextInputs.forEach(input => {
        input.addEventListener('input', updateRcloneCommandPreview);
    });
    
    // Rclone form input changes
    if (document.getElementById('rclone-operation-type')) {
        document.getElementById('rclone-operation-type').addEventListener('change', updateRcloneCommandPreview);
    }
    if (document.getElementById('rclone-source')) {
        document.getElementById('rclone-source').addEventListener('input', updateRcloneCommandPreview);
    }
    if (document.getElementById('rclone-destination')) {
        document.getElementById('rclone-destination').addEventListener('input', updateRcloneCommandPreview);
    }
    if (document.getElementById('rclone-excludes')) {
        document.getElementById('rclone-excludes').addEventListener('input', updateRcloneCommandPreview);
    }
}

// API helper functions
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `HTTP ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API call failed:', error);
        showStatus(error.message, 'error');
        throw error;
    }
}

// Job management functions
async function refreshJobs() {
    try {
        const data = await apiCall('/api/jobs');
        updateJobList(data.jobs);
        updateSummary(data.jobs);
    } catch (error) {
        console.error('Failed to refresh jobs:', error);
    }
}

async function startJob(jobId) {
    try {
        await apiCall(`/api/job/${jobId}/start`, { method: 'POST' });
        showStatus(`Job ${jobId} started`, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to start job:', error);
    }
}

async function restartJob(jobId) {
    try {
        await apiCall(`/api/job/${jobId}/restart`, { method: 'POST' });
        showStatus(`Job ${jobId} restarted`, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to restart job:', error);
    }
}

async function stopJob(jobId) {
    if (!confirm('Are you sure you want to stop this job?')) {
        return;
    }

    try {
        await apiCall(`/api/job/${jobId}/stop`, { method: 'POST' });
        showStatus(`Job ${jobId} stopped`, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to stop job:', error);
    }
}

async function pauseJob(jobId) {
    try {
        await apiCall(`/api/job/${jobId}/pause`, { method: 'POST' });
        showStatus(`Job ${jobId} paused`, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to pause job:', error);
        showStatus(`Failed to pause job: ${error.message}`, 'error');
    }
}

async function resumeJob(jobId) {
    try {
        await apiCall(`/api/job/${jobId}/resume`, { method: 'POST' });
        showStatus(`Job ${jobId} resumed`, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to resume job:', error);
        showStatus(`Failed to resume job: ${error.message}`, 'error');
    }
}

async function deleteJob(jobId) {
    if (!confirm('Are you sure you want to delete this job? This cannot be undone.')) {
        return;
    }
    
    try {
        await apiCall(`/api/job/${jobId}/delete`, { method: 'DELETE' });
        showStatus(`Job ${jobId} deleted`, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to delete job:', error);
    }
}

async function restartAllFailedJobs() {
    try {
        const result = await apiCall('/api/jobs/restart-failed', { method: 'POST' });
        showStatus(result.message, 'success');
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to restart jobs:', error);
    }
}

// Create job functions
function showCreateModal() {
    document.getElementById('create-job-modal').style.display = 'block';
    updateCommandPreview();
}

function closeCreateModal() {
    document.getElementById('create-job-modal').style.display = 'none';
    document.getElementById('create-job-form').reset();
    // Hide and clear confirmation section
    document.getElementById('delete-confirmation').style.display = 'none';
    document.getElementById('delete-confirmation-input').value = '';
    updateConfirmationStatus();
    updateCommandPreview();
}

async function handleCreateJob(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    
    // Check if dangerous option is selected
    const removeSourceFiles = formData.has('remove_source_files');
    if (removeSourceFiles) {
        const confirmationInput = document.getElementById('delete-confirmation-input').value.toLowerCase();
        if (confirmationInput !== 'delete') {
            showStatus('Please type "delete" to confirm source file deletion', 'error');
            return;
        }
    }
    
    const jobData = {
        name: formData.get('name'),
        source: formData.get('source'),
        destination: formData.get('destination'),
        excludes: formData.get('excludes'),
        max_retries: parseInt(formData.get('max_retries')),
        rsync_args: {
            archive: formData.has('archive'),
            verbose: formData.has('verbose'),
            human_readable: formData.has('human_readable'),
            progress: formData.has('progress'),
            compress: formData.has('compress'),
            delete: formData.has('delete'),
            dry_run: formData.has('dry_run'),
            remove_source_files: formData.has('remove_source_files'),
            checksum: formData.has('checksum'),
            stats: formData.has('stats'),
            itemize_changes: formData.has('itemize_changes'),
            inplace: formData.has('inplace'),
            sparse: formData.has('sparse'),
            whole_file: formData.has('whole_file'),
            update: formData.has('update'),
            ignore_existing: formData.has('ignore_existing'),
            bwlimit: formData.get('bwlimit'),
            partial_dir: formData.get('partial_dir')
        }
    };
    
    try {
        const result = await apiCall('/api/job/create', {
            method: 'POST',
            body: JSON.stringify(jobData)
        });
        
        showStatus('Job created successfully', 'success');
        closeCreateModal();
        setTimeout(refreshJobs, 1000);
    } catch (error) {
        console.error('Failed to create job:', error);
    }
}

// Command preview functions
function updateCommandPreview() {
    const source = document.getElementById('job-source').value;
    const destination = document.getElementById('job-destination').value;
    const excludes = document.getElementById('job-excludes').value;
    
    const rsyncArgs = {
        archive: document.querySelector('input[name="archive"]').checked,
        verbose: document.querySelector('input[name="verbose"]').checked,
        human_readable: document.querySelector('input[name="human_readable"]').checked,
        progress: document.querySelector('input[name="progress"]').checked,
        compress: document.querySelector('input[name="compress"]').checked,
        delete: document.querySelector('input[name="delete"]').checked,
        dry_run: document.querySelector('input[name="dry_run"]').checked,
        remove_source_files: document.querySelector('input[name="remove_source_files"]').checked,
        checksum: document.querySelector('input[name="checksum"]').checked,
        stats: document.querySelector('input[name="stats"]').checked,
        itemize_changes: document.querySelector('input[name="itemize_changes"]').checked,
        inplace: document.querySelector('input[name="inplace"]').checked,
        sparse: document.querySelector('input[name="sparse"]').checked,
        whole_file: document.querySelector('input[name="whole_file"]').checked,
        update: document.querySelector('input[name="update"]').checked,
        ignore_existing: document.querySelector('input[name="ignore_existing"]').checked
    };
    
    const bwlimit = document.getElementById('bwlimit').value.trim();
    const partial_dir = document.getElementById('partial_dir').value.trim();
    
    // Build command string locally for preview
    let command = 'rsync';
    
    if (rsyncArgs.archive) command += ' -a';
    if (rsyncArgs.verbose) command += ' -v';
    if (rsyncArgs.human_readable) command += ' -h';
    if (rsyncArgs.progress) command += ' -P';
    if (rsyncArgs.compress) command += ' --compress';
    if (rsyncArgs.delete) command += ' --delete';
    if (rsyncArgs.dry_run) command += ' --dry-run';
    if (rsyncArgs.remove_source_files) command += ' --remove-source-files';
    
    // Advanced options
    if (rsyncArgs.checksum) command += ' --checksum';
    if (rsyncArgs.stats) command += ' --stats';
    if (rsyncArgs.itemize_changes) command += ' --itemize-changes';
    if (rsyncArgs.inplace) command += ' --inplace';
    if (rsyncArgs.sparse) command += ' --sparse';
    if (rsyncArgs.whole_file) command += ' --whole-file';
    if (rsyncArgs.update) command += ' --update';
    if (rsyncArgs.ignore_existing) command += ' --ignore-existing';
    
    if (bwlimit) command += ` --bwlimit=${bwlimit}`;
    if (partial_dir) command += ` --partial-dir=${partial_dir}`;
    
    if (excludes.trim()) {
        const excludeList = excludes.trim().split(/\\s+/);
        excludeList.forEach(pattern => {
            command += ` --exclude='${pattern}'`;
        });
    }
    
    const finalSource = source.trim() || '[SOURCE]';
    const finalDestination = destination.trim() || '[DESTINATION]';
    command += ` ${finalSource} ${finalDestination}`;
    
    document.getElementById('command-preview').textContent = command;
}

function copyCommand() {
    const command = document.getElementById('command-preview').textContent;
    navigator.clipboard.writeText(command).then(() => {
        showStatus('Command copied to clipboard', 'success');
    }).catch(err => {
        console.error('Failed to copy command:', err);
        showStatus('Failed to copy command', 'error');
    });
}

// Confirmation status for delete source files
function updateConfirmationStatus() {
    const input = document.getElementById('delete-confirmation-input');
    const status = document.getElementById('confirmation-status');
    const value = input.value.toLowerCase();
    
    if (value === 'delete') {
        status.textContent = '✅ Confirmed';
        status.className = 'confirmation-status valid';
    } else if (value.length > 0) {
        status.textContent = '❌ Type "delete" exactly';
        status.className = 'confirmation-status invalid';
    } else {
        status.textContent = '';
        status.className = 'confirmation-status';
    }
}

// Logs functions
async function viewLogs(jobId) {
    try {
        const data = await apiCall(`/api/job/${jobId}/logs`);
        document.getElementById('logs-text').textContent = data.logs || 'No logs available';
        document.getElementById('logs-modal').style.display = 'block';
    } catch (error) {
        console.error('Failed to load logs:', error);
    }
}

function closeLogsModal() {
    document.getElementById('logs-modal').style.display = 'none';
}

// UI update functions
function updateJobList(jobs) {
    const jobList = document.getElementById('job-list');
    
    if (jobs.length === 0) {
        jobList.innerHTML = '<p style="text-align: center; color: #7f8c8d; padding: 40px;">No jobs found. Create your first job to get started.</p>';
        return;
    }
    
    jobList.innerHTML = jobs.map(job => createJobCard(job)).join('');
}

function createJobCard(job) {
    const statusClass = job.status ? `status-${job.status}` : 'status-unknown';
    const isRunning = job.status === 'running';
    const isPaused = job.status === 'paused';
    const isFailed = job.status === 'failed';
    const isCreated = job.status === 'created';
    const hasProgress = job.progress;

    return `
        <div class="job-card" data-job-id="${job.id}">
            <div class="job-header">
                <h3>${job.name}</h3>
                <span class="status ${statusClass}">${job.status ? job.status.toUpperCase() : 'UNKNOWN'}</span>
            </div>

            <div class="job-details">
                <div class="job-info">
                    <div class="info-row">
                        <strong>Source:</strong> ${job.source}
                    </div>
                    <div class="info-row">
                        <strong>Destination:</strong> ${job.destination}
                    </div>
                    <div class="info-row">
                        <strong>Retries:</strong> ${job.retry_count || 0}/${job.max_retries || 5}
                    </div>
                    ${job.error_message ? `
                    <div class="info-row error">
                        <strong>Error:</strong> ${job.error_message}
                    </div>` : ''}
                </div>

                <div class="job-actions">
                    ${isCreated ? `
                    <button class="btn btn-small btn-success" onclick="startJob('${job.id}')">
                        ▶️ Start
                    </button>` : ''}

                    ${isFailed ? `
                    <button class="btn btn-small btn-primary" onclick="restartJob('${job.id}')">
                        🔄 Restart
                    </button>` : ''}

                    ${isRunning ? `
                    <button class="btn btn-small btn-warning" onclick="pauseJob('${job.id}')">
                        ⏸️ Pause
                    </button>
                    <button class="btn btn-small btn-danger" onclick="stopJob('${job.id}')">
                        ⏹️ Stop
                    </button>` : ''}

                    ${isPaused ? `
                    <button class="btn btn-small btn-success" onclick="resumeJob('${job.id}')">
                        ▶️ Resume
                    </button>
                    <button class="btn btn-small btn-danger" onclick="stopJob('${job.id}')">
                        ⏹️ Stop
                    </button>` : ''}

                    <button class="btn btn-small btn-secondary" onclick="viewLogs('${job.id}')">
                        📋 Logs
                    </button>

                    <button class="btn btn-small btn-danger" onclick="deleteJob('${job.id}')">
                        🗑️ Delete
                    </button>
                </div>
            </div>
            
            ${hasProgress ? `
            <div class="progress-container">
                <div class="progress-bar" style="width: ${job.progress.percent || 0}%"></div>
                <span class="progress-text">${job.progress.percent || 0}%</span>
            </div>` : ''}
        </div>
    `;
}

function updateSummary(jobs) {
    const failedJobs = jobs.filter(job => job.status === 'failed');
    const runningJobs = jobs.filter(job => job.status === 'running');
    
    document.getElementById('failed-count').textContent = failedJobs.length;
    document.getElementById('running-count').textContent = runningJobs.length;
    document.getElementById('total-count').textContent = jobs.length;
}

// Status message functions
function showStatus(message, type = 'info') {
    const statusEl = document.getElementById('status-message');
    statusEl.textContent = message;
    statusEl.className = `status-message ${type} show`;
    
    setTimeout(() => {
        statusEl.classList.remove('show');
    }, 3000);
}

// Progress updates using Server-Sent Events
function startProgressUpdates() {
    if (eventSource) {
        eventSource.close();
    }
    
    try {
        eventSource = new EventSource('/api/progress');
        
        eventSource.onmessage = function(event) {
            try {
                const progressData = JSON.parse(event.data);
                
                progressData.forEach(update => {
                    updateJobProgress(update.job_id, update.progress);
                });
            } catch (error) {
                console.error('Error parsing progress data:', error);
            }
        };
        
        eventSource.onerror = function() {
            console.error('Progress stream error, retrying in 5 seconds...');
            setTimeout(startProgressUpdates, 5000);
        };
        
    } catch (error) {
        console.error('Failed to start progress updates:', error);
        // Fallback to polling
        setInterval(refreshJobs, 5000);
    }
}

function updateJobProgress(jobId, progress) {
    const jobCard = document.querySelector(`[data-job-id="${jobId}"]`);
    if (!jobCard) return;
    
    // Update progress bar
    const progressBar = jobCard.querySelector('.progress-bar');
    const progressText = jobCard.querySelector('.progress-text');
    
    if (progressBar && progress.percent !== undefined) {
        progressBar.style.width = `${progress.percent}%`;
        progressText.textContent = `${progress.percent}%`;
    }
    
    // Update status if changed
    const statusEl = jobCard.querySelector('.status');
    if (statusEl && progress.status) {
        statusEl.className = `status status-${progress.status}`;
        statusEl.textContent = progress.status.toUpperCase();
    }
}

// Modal close on outside click
window.onclick = function(event) {
    const createModal = document.getElementById('create-job-modal');
    const logsModal = document.getElementById('logs-modal');
    
    if (event.target === createModal) {
        closeCreateModal();
    }
    
    if (event.target === logsModal) {
        closeLogsModal();
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeCreateModal();
        closeLogsModal();
    }
    
    if (event.ctrlKey && event.key === 'n') {
        event.preventDefault();
        showCreateModal();
    }
    
    if (event.key === 'F5') {
        event.preventDefault();
        refreshJobs();
    }
});

// ==================== TAB NAVIGATION ====================

function setupTabNavigation() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    const selectedPane = document.getElementById(`${tabName}-tab`);
    if (selectedPane) {
        selectedPane.classList.add('active');
    }
    
    const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('active');
    }
    
    // Load tab-specific content
    if (tabName === 'rclone') {
        checkRcloneStatus();
        loadRcloneOperations();
    }
}

// ==================== RCLONE FUNCTIONS ====================

// Check rclone installation status
async function checkRcloneStatus() {
    try {
        const data = await apiCall('/api/rclone/status');
        displayRcloneStatus(data);
    } catch (error) {
        console.error('Failed to check rclone status:', error);
    }
}

function displayRcloneStatus(status) {
    const statusDiv = document.getElementById('rclone-status-info');
    if (!statusDiv) return;
    
    const installed = status.installed ? 'Yes' : 'No';
    const version = status.version || 'N/A';
    const classname = status.installed ? 'installed' : 'not-installed';
    
    statusDiv.innerHTML = `
        <div class="rclone-status-item ${classname}">
            <div class="rclone-status-label">Rclone Installed</div>
            <div class="rclone-status-value">${installed}</div>
        </div>
        <div class="rclone-status-item installed">
            <div class="rclone-status-label">Version</div>
            <div class="rclone-status-value">${version}</div>
        </div>
    `;
}

// Load rclone operations
async function loadRcloneOperations() {
    try {
        const data = await apiCall('/api/rclone/operations');
        updateRcloneOperationList(data.operations);
    } catch (error) {
        console.error('Failed to load rclone operations:', error);
    }
}

function updateRcloneOperationList(operations) {
    const operationList = document.getElementById('rclone-operation-list');
    
    if (operations.length === 0) {
        operationList.innerHTML = '<p style="text-align: center; color: #7f8c8d; padding: 40px;">No rclone operations found. Create your first operation to get started.</p>';
        return;
    }
    
    operationList.innerHTML = operations.map(op => createRcloneOperationCard(op)).join('');
}

function createRcloneOperationCard(operation) {
    const statusClass = operation.status ? `status-${operation.status}` : 'status-unknown';
    const isRunning = operation.status === 'running';
    const isPaused = operation.status === 'paused';
    const isFailed = operation.status === 'failed';
    const hasProgress = operation.progress;

    return `
        <div class="rclone-operation-card" data-operation-id="${operation.id}">
            <div class="rclone-operation-header">
                <div>
                    <div class="rclone-operation-name">${operation.name}</div>
                    <span class="status ${statusClass}">${operation.status ? operation.status.toUpperCase() : 'UNKNOWN'}</span>
                </div>
                <span class="rclone-operation-type">${operation.operation_type}</span>
            </div>

            <div class="rclone-operation-info">
                <div class="rclone-info-row">
                    <strong>Source:</strong> ${operation.source}
                </div>
                <div class="rclone-info-row">
                    <strong>Destination:</strong> ${operation.destination}
                </div>
                <div class="rclone-info-row">
                    <strong>Retries:</strong> ${operation.retry_count || 0}/${operation.max_retries || 3}
                </div>
                ${operation.error_message ? `
                <div class="rclone-info-row" style="color: #e74c3c;">
                    <strong>Error:</strong> ${operation.error_message}
                </div>` : ''}
            </div>

            <div class="rclone-operation-actions">
                ${isFailed ? `
                <button class="btn btn-small btn-primary" onclick="startRcloneOperation('${operation.id}')">
                    🔄 Restart
                </button>` : ''}

                ${isRunning ? `
                <button class="btn btn-small btn-warning" onclick="pauseRcloneOperation('${operation.id}')">
                    ⏸️ Pause
                </button>
                <button class="btn btn-small btn-danger" onclick="stopRcloneOperation('${operation.id}')">
                    ⏹️ Stop
                </button>` : ''}

                ${isPaused ? `
                <button class="btn btn-small btn-success" onclick="resumeRcloneOperation('${operation.id}')">
                    ▶️ Resume
                </button>
                <button class="btn btn-small btn-danger" onclick="stopRcloneOperation('${operation.id}')">
                    ⏹️ Stop
                </button>` : ''}

                <button class="btn btn-small btn-secondary" onclick="viewRcloneLogs('${operation.id}')">
                    📋 Logs
                </button>

                <button class="btn btn-small btn-danger" onclick="deleteRcloneOperation('${operation.id}')">
                    🗑️ Delete
                </button>
            </div>
            
            ${hasProgress ? `
            <div class="progress-container" style="margin-top: 15px;">
                <div class="progress-bar" style="width: ${operation.progress.percent || 0}%"></div>
                <span class="progress-text">${operation.progress.percent || 0}%</span>
            </div>` : ''}
        </div>
    `;
}

// Show rclone operation modal
function showRcloneModal() {
    document.getElementById('rclone-operation-modal').style.display = 'block';
    updateRcloneCommandPreview();
}

function closeRcloneModal() {
    document.getElementById('rclone-operation-modal').style.display = 'none';
    document.getElementById('rclone-operation-form').reset();
    updateRcloneCommandPreview();
}

function closeRcloneLogsModal() {
    document.getElementById('rclone-logs-modal').style.display = 'none';
}

// Handle rclone operation creation (with preview)
async function handleCreateRcloneOperation(event) {
    event.preventDefault();

    const formData = new FormData(event.target);
    const operationData = {
        name: formData.get('name'),
        source: formData.get('source'),
        destination: formData.get('destination'),
        operation_type: formData.get('operation_type'),
        excludes: formData.get('excludes'),
        max_retries: parseInt(formData.get('max_retries')),
        rclone_args: {
            verbose: formData.has('verbose'),
            progress: formData.has('progress'),
            dry_run: formData.has('dry_run'),
            checksum: formData.has('checksum'),
            delete: formData.has('delete'),
            stats: formData.has('stats'),
            fast_list: formData.has('fast_list'),
            no_traverse: formData.has('no_traverse'),
            update: formData.has('update'),
            ignore_existing: formData.has('ignore_existing'),
            size_only: formData.has('size_only'),
            ignore_size: formData.has('ignore_size'),
            use_server_modtime: formData.has('use_server_modtime'),
            track_renames: formData.has('track_renames'),
            inplace: formData.has('inplace'),
            transfers: formData.get('transfers'),
            checkers: formData.get('checkers'),
            bwlimit: formData.get('bwlimit'),
            retries: formData.get('retries'),
            low_level_retries: formData.get('low_level_retries'),
            timeout: formData.get('timeout'),
            contimeout: formData.get('contimeout'),
            buffer_size: formData.get('buffer_size'),
            drive_chunk_size: formData.get('drive_chunk_size'),
            min_size: formData.get('min_size'),
            max_size: formData.get('max_size'),
            min_age: formData.get('min_age'),
            max_age: formData.get('max_age'),
            max_delete: formData.get('max_delete')
        }
    };

    // Show preview modal with loading state
    showPreviewLoading();

    try {
        const result = await apiCall('/api/rclone/operation/create-with-preview', {
            method: 'POST',
            body: JSON.stringify(operationData)
        });

        if (result.success) {
            showPreviewResults(result.operation_id, result.stats);
        } else {
            showPreviewError(result.error, result.timeout);
        }
    } catch (error) {
        console.error('Failed to create preview:', error);
        showPreviewError(error.message || 'Failed to analyze transfer');
    }
}

// Show preview modal in loading state
function showPreviewLoading() {
    const modal = document.getElementById('preview-modal');
    const loading = document.getElementById('preview-loading');
    const results = document.getElementById('preview-results');
    const errorDiv = document.getElementById('preview-error');

    loading.style.display = 'block';
    results.style.display = 'none';
    errorDiv.style.display = 'none';
    modal.style.display = 'block';

    // Optional: Update progress text every few seconds
    let elapsed = 0;
    const progressText = document.getElementById('preview-progress-text');
    const interval = setInterval(() => {
        elapsed += 3;
        if (elapsed < 60) {
            progressText.textContent = `Scanning... ${elapsed}s elapsed`;
        } else {
            clearInterval(interval);
            progressText.textContent = 'This is taking longer than expected...';
        }
    }, 3000);

    // Store interval ID for cleanup
    modal.dataset.progressInterval = interval;
}

// Show preview results
function showPreviewResults(operationId, stats) {
    // Clear progress interval
    const modal = document.getElementById('preview-modal');
    if (modal.dataset.progressInterval) {
        clearInterval(parseInt(modal.dataset.progressInterval));
    }

    const loading = document.getElementById('preview-loading');
    const results = document.getElementById('preview-results');
    const errorDiv = document.getElementById('preview-error');

    loading.style.display = 'none';
    results.style.display = 'block';
    errorDiv.style.display = 'none';

    // Populate stats
    document.getElementById('preview-files').textContent =
        (stats.files_to_transfer || 0).toLocaleString();
    document.getElementById('preview-size').textContent =
        stats.size_formatted || '0 B';
    document.getElementById('preview-eta').textContent =
        stats.estimated_time || 'Unknown';
    document.getElementById('preview-checks').textContent =
        (stats.files_to_check || 0).toLocaleString();

    // Populate details
    document.getElementById('preview-transfer-type').textContent =
        stats.transfer_type || 'unknown';
    document.getElementById('preview-speed').textContent =
        stats.speed_estimate || 'Unknown';
    document.getElementById('preview-scan-time').textContent =
        stats.scan_time ? `${stats.scan_time.toFixed(1)}s` : 'Unknown';

    // Show warnings if any
    const warningsDiv = document.getElementById('preview-warnings');
    if (stats.warnings && stats.warnings.length > 0) {
        warningsDiv.innerHTML = stats.warnings.map(w =>
            `<div class="warning-item">${w}</div>`
        ).join('');
        warningsDiv.style.display = 'block';
    } else {
        warningsDiv.style.display = 'none';
    }

    // Store operation ID for approval
    document.getElementById('proceed-btn').dataset.operationId = operationId;
}

// Show preview error
function showPreviewError(errorMessage, isTimeout = false) {
    // Clear progress interval
    const modal = document.getElementById('preview-modal');
    if (modal.dataset.progressInterval) {
        clearInterval(parseInt(modal.dataset.progressInterval));
    }

    const loading = document.getElementById('preview-loading');
    const results = document.getElementById('preview-results');
    const errorDiv = document.getElementById('preview-error');
    const errorMsg = document.getElementById('preview-error-message');

    loading.style.display = 'none';
    results.style.display = 'none';
    errorDiv.style.display = 'block';

    if (isTimeout) {
        errorMsg.innerHTML = `
            <strong>Preview Timeout</strong><br>
            ${errorMessage}<br><br>
            The operation may be very large. You can try again or proceed without preview.
        `;
    } else {
        errorMsg.textContent = errorMessage;
    }
}

// Approve and start the pending transfer
async function approvePendingTransfer() {
    const btn = document.getElementById('proceed-btn');
    const operationId = btn.dataset.operationId;

    if (!operationId) {
        showStatus('No operation to approve', 'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Starting...';

    try {
        const result = await apiCall(`/api/rclone/operation/${operationId}/approve`, {
            method: 'POST'
        });

        if (result.success) {
            showStatus('Transfer approved and started', 'success');
            closePreviewModal();
            closeRcloneModal();
            setTimeout(loadRcloneOperations, 1000);
        } else {
            showStatus(result.error || 'Failed to start transfer', 'error');
            btn.disabled = false;
            btn.textContent = '✓ Proceed with Transfer';
        }
    } catch (error) {
        console.error('Failed to approve transfer:', error);
        showStatus('Failed to start transfer', 'error');
        btn.disabled = false;
        btn.textContent = '✓ Proceed with Transfer';
    }
}

// Cancel preview
async function cancelPreview() {
    const btn = document.getElementById('proceed-btn');
    const operationId = btn.dataset.operationId;

    if (operationId) {
        // Delete the pending operation
        try {
            await apiCall(`/api/rclone/operation/${operationId}/delete`, {
                method: 'DELETE'
            });
        } catch (error) {
            console.error('Failed to delete pending operation:', error);
        }
    }

    closePreviewModal();
}

// Close preview modal
function closePreviewModal() {
    // Clear progress interval
    const modal = document.getElementById('preview-modal');
    if (modal.dataset.progressInterval) {
        clearInterval(parseInt(modal.dataset.progressInterval));
        delete modal.dataset.progressInterval;
    }

    modal.style.display = 'none';

    // Reset button
    const btn = document.getElementById('proceed-btn');
    btn.disabled = false;
    btn.textContent = '✓ Proceed with Transfer';
    delete btn.dataset.operationId;
}

// Rclone operations
async function startRcloneOperation(operationId) {
    try {
        await apiCall(`/api/rclone/operation/${operationId}/start`, { method: 'POST' });
        showStatus(`Operation ${operationId} started`, 'success');
        setTimeout(loadRcloneOperations, 1000);
    } catch (error) {
        console.error('Failed to start rclone operation:', error);
    }
}

async function stopRcloneOperation(operationId) {
    if (!confirm('Are you sure you want to stop this operation?')) {
        return;
    }

    try {
        await apiCall(`/api/rclone/operation/${operationId}/stop`, { method: 'POST' });
        showStatus(`Operation ${operationId} stopped`, 'success');
        setTimeout(loadRcloneOperations, 1000);
    } catch (error) {
        console.error('Failed to stop rclone operation:', error);
    }
}

async function pauseRcloneOperation(operationId) {
    try {
        await apiCall(`/api/rclone/operation/${operationId}/pause`, { method: 'POST' });
        showStatus(`Operation ${operationId} paused`, 'success');
        setTimeout(loadRcloneOperations, 1000);
    } catch (error) {
        console.error('Failed to pause rclone operation:', error);
        showStatus(`Failed to pause operation: ${error.message}`, 'error');
    }
}

async function resumeRcloneOperation(operationId) {
    try {
        await apiCall(`/api/rclone/operation/${operationId}/resume`, { method: 'POST' });
        showStatus(`Operation ${operationId} resumed`, 'success');
        setTimeout(loadRcloneOperations, 1000);
    } catch (error) {
        console.error('Failed to resume rclone operation:', error);
        showStatus(`Failed to resume operation: ${error.message}`, 'error');
    }
}

async function deleteRcloneOperation(operationId) {
    if (!confirm('Are you sure you want to delete this operation? This cannot be undone.')) {
        return;
    }
    
    try {
        await apiCall(`/api/rclone/operation/${operationId}/delete`, { method: 'DELETE' });
        showStatus(`Operation ${operationId} deleted`, 'success');
        setTimeout(loadRcloneOperations, 1000);
    } catch (error) {
        console.error('Failed to delete rclone operation:', error);
    }
}

async function viewRcloneLogs(operationId) {
    try {
        const data = await apiCall(`/api/rclone/operation/${operationId}/logs`);
        document.getElementById('rclone-logs-text').textContent = data.logs || 'No logs available';
        document.getElementById('rclone-logs-modal').style.display = 'block';
    } catch (error) {
        console.error('Failed to load rclone logs:', error);
    }
}

// Rclone command preview
function updateRcloneCommandPreview() {
    const operationType = document.getElementById('rclone-operation-type').value || 'copy';
    const source = document.getElementById('rclone-source').value;
    const destination = document.getElementById('rclone-destination').value;
    const excludes = document.getElementById('rclone-excludes').value;
    
    const rcloneArgs = {
        verbose: document.querySelector('#rclone-operation-form input[name="verbose"]').checked,
        progress: document.querySelector('#rclone-operation-form input[name="progress"]').checked,
        dry_run: document.querySelector('#rclone-operation-form input[name="dry_run"]').checked,
        checksum: document.querySelector('#rclone-operation-form input[name="checksum"]').checked,
        delete: document.querySelector('#rclone-operation-form input[name="delete"]').checked,
        stats: document.querySelector('#rclone-operation-form input[name="stats"]').checked,
        fast_list: document.querySelector('#rclone-operation-form input[name="fast_list"]').checked,
        no_traverse: document.querySelector('#rclone-operation-form input[name="no_traverse"]').checked,
        update: document.querySelector('#rclone-operation-form input[name="update"]').checked,
        ignore_existing: document.querySelector('#rclone-operation-form input[name="ignore_existing"]').checked,
        size_only: document.querySelector('#rclone-operation-form input[name="size_only"]').checked,
        track_renames: document.querySelector('#rclone-operation-form input[name="track_renames"]').checked,
        inplace: document.querySelector('#rclone-operation-form input[name="inplace"]').checked
    };
    
    const transfers = document.getElementById('rclone-transfers').value.trim();
    const checkers = document.getElementById('rclone-checkers').value.trim();
    const bwlimit = document.getElementById('rclone-bwlimit').value.trim();
    const retries = document.getElementById('rclone-retries').value.trim();
    const minSize = document.getElementById('rclone-min-size').value.trim();
    const maxSize = document.getElementById('rclone-max-size').value.trim();
    
    let command = `rclone ${operationType}`;
    
    if (rcloneArgs.verbose) command += ' -v';
    if (rcloneArgs.progress) command += ' --progress';
    if (rcloneArgs.dry_run) command += ' --dry-run';
    if (rcloneArgs.checksum) command += ' --checksum';
    if (rcloneArgs.delete && operationType === 'sync') command += ' --delete-during';
    if (rcloneArgs.stats) command += ' --stats 1m';
    if (rcloneArgs.fast_list) command += ' --fast-list';
    if (rcloneArgs.no_traverse) command += ' --no-traverse';
    if (rcloneArgs.update) command += ' --update';
    if (rcloneArgs.ignore_existing) command += ' --ignore-existing';
    if (rcloneArgs.size_only) command += ' --size-only';
    if (rcloneArgs.track_renames) command += ' --track-renames';
    if (rcloneArgs.inplace) command += ' --inplace';
    
    if (transfers && transfers !== '4') command += ` --transfers ${transfers}`;
    if (checkers && checkers !== '8') command += ` --checkers ${checkers}`;
    if (bwlimit) command += ` --bwlimit ${bwlimit}`;
    if (retries && retries !== '3') command += ` --retries ${retries}`;
    if (minSize) command += ` --min-size ${minSize}`;
    if (maxSize) command += ` --max-size ${maxSize}`;
    
    if (excludes.trim()) {
        const excludeList = excludes.trim().split(/\s+/);
        excludeList.forEach(pattern => {
            command += ` --exclude='${pattern}'`;
        });
    }
    
    const finalSource = source.trim() || '[SOURCE]';
    const finalDestination = destination.trim() || '[DESTINATION]';
    command += ` ${finalSource} ${finalDestination}`;
    
    document.getElementById('rclone-command-preview').textContent = command;
}

function copyRcloneCommand() {
    const command = document.getElementById('rclone-command-preview').textContent;
    navigator.clipboard.writeText(command).then(() => {
        showStatus('Command copied to clipboard', 'success');
    }).catch(err => {
        console.error('Failed to copy command:', err);
        showStatus('Failed to copy command', 'error');
    });
}

// Modal close on outside click - add rclone modals
const originalWindowClick = window.onclick;
window.onclick = function(event) {
    originalWindowClick(event);
    
    const rcloneModal = document.getElementById('rclone-operation-modal');
    const rcloneLogsModal = document.getElementById('rclone-logs-modal');
    
    if (event.target === rcloneModal) {
        closeRcloneModal();
    }
    
    if (event.target === rcloneLogsModal) {
        closeRcloneLogsModal();
    }
}
