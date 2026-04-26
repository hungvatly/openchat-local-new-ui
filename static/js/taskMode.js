// ── Cowork Task Mode ─────────────────────────────────────────────────────────

const TASK_FOLDERS_KEY = 'cowork_saved_folders';
let currentTaskSSE = null;
let currentTaskId = null;

// ── Saved Folders Persistence ─────────────────────────────────────────────────

function getSavedFolders() {
    try { return JSON.parse(localStorage.getItem(TASK_FOLDERS_KEY) || '[]'); }
    catch { return []; }
}

function saveFoldersList(folders) {
    localStorage.setItem(TASK_FOLDERS_KEY, JSON.stringify(folders));
}

function addSavedFolder(path) {
    if (!path.trim()) return false;
    const folders = getSavedFolders();
    if (folders.includes(path)) return false; // already saved
    folders.unshift(path); // most-recent first
    saveFoldersList(folders);
    refreshFolderUI();
    return true;
}

function removeSavedFolder(path) {
    const folders = getSavedFolders().filter(f => f !== path);
    saveFoldersList(folders);
    refreshFolderUI();
}

function refreshFolderUI() {
    const folders = getSavedFolders();

    // ── Update badge ──
    const badge = document.getElementById('task-folders-badge');
    if (badge) {
        badge.textContent = folders.length;
        badge.style.display = folders.length > 0 ? 'inline-block' : 'none';
    }

    // ── Quick-select chips on Run Task tab ──
    const quickSection = document.getElementById('task-quick-folders');
    const quickList = document.getElementById('task-quick-folder-list');
    if (quickSection && quickList) {
        if (folders.length > 0) {
            quickSection.style.display = 'block';
            quickList.innerHTML = folders.map(f => `
                <button onclick="selectQuickFolder(this)" data-path="${escapeAttr(f)}" title="${escapeAttr(f)}"
                    style="padding:5px 12px; background:rgba(255,255,255,0.06); border:1px solid var(--border); border-radius:20px;
                           color:var(--text-secondary); font-size:12px; font-family:var(--font-mono); cursor:pointer;
                           transition:all 0.15s; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"
                    onmouseenter="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'"
                    onmouseleave="this.style.borderColor='var(--border)';this.style.color='var(--text-secondary)'">
                    ${shortenPath(f)}
                </button>
            `).join('');
        } else {
            quickSection.style.display = 'none';
        }
    }

    // ── Folder Manager list ──
    const managerList = document.getElementById('task-folder-manager-list');
    if (managerList) {
        if (folders.length === 0) {
            managerList.innerHTML = `
                <div style="text-align:center; padding:40px 20px; color:var(--text-muted); font-size:13px;">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:10px; opacity:0.4;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    <p>No saved folders yet.<br>Add folders to quickly select them when running tasks.</p>
                </div>`;
        } else {
            managerList.innerHTML = folders.map(f => `
                <div style="display:flex; align-items:center; gap:12px; padding:14px 18px; background:var(--bg-tertiary);
                            border:1px solid var(--border); border-radius:8px;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" style="flex-shrink:0;">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                    </svg>
                    <span style="flex:1; font-family:var(--font-mono); font-size:13px; color:var(--text-primary);
                                 overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeAttr(f)}">${f}</span>
                    <button onclick="useFolderInTask('${escapeAttr(f)}')" title="Use for task"
                        style="padding:5px 10px; background:transparent; border:1px solid var(--border); border-radius:5px;
                               color:var(--text-muted); font-size:12px; cursor:pointer; transition:all 0.15s; white-space:nowrap;"
                        onmouseenter="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'"
                        onmouseleave="this.style.borderColor='var(--border)';this.style.color='var(--text-muted)'">
                        Use
                    </button>
                    <button onclick="removeSavedFolder('${escapeAttr(f)}')" title="Remove folder"
                        style="padding:5px 8px; background:transparent; border:1px solid transparent; border-radius:5px;
                               color:var(--text-muted); cursor:pointer; transition:all 0.15s;"
                        onmouseenter="this.style.borderColor='var(--error,#ff453a)';this.style.color='var(--error,#ff453a)'"
                        onmouseleave="this.style.borderColor='transparent';this.style.color='var(--text-muted)'">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            `).join('');
        }
    }
}

function escapeAttr(str) {
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function shortenPath(path) {
    const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
    if (parts.length <= 2) return path;
    return '…/' + parts.slice(-2).join('/');
}

// ── Tab switching ──────────────────────────────────────────────────────────────

function switchTaskTab(tab) {
    const runPanel = document.getElementById('task-panel-run');
    const foldersPanel = document.getElementById('task-panel-folders');
    const tabRun = document.getElementById('task-tab-run');
    const tabFolders = document.getElementById('task-tab-folders');

    if (tab === 'run') {
        runPanel.style.display = 'block';
        foldersPanel.style.display = 'none';
        tabRun.classList.add('task-tab-active');
        tabFolders.classList.remove('task-tab-active');
    } else {
        runPanel.style.display = 'none';
        foldersPanel.style.display = 'block';
        tabRun.classList.remove('task-tab-active');
        tabFolders.classList.add('task-tab-active');
        refreshFolderUI(); // ensure up-to-date
    }
}

// ── Mode open / close ─────────────────────────────────────────────────────────

function openTaskMode() {
    const chatArea = document.querySelector('.chat-area');
    const inputArea = document.querySelector('.input-area');
    const welcome = document.querySelector('.welcome');
    if (chatArea) chatArea.style.display = 'none';
    if (inputArea) inputArea.style.display = 'none';
    if (welcome) welcome.style.display = 'none';

    const pane = document.getElementById('task-mode-pane');
    if (pane) pane.style.display = 'flex';

    // Default to Run Task tab
    switchTaskTab('run');
    refreshFolderUI();
}

function closeTaskMode() {
    const pane = document.getElementById('task-mode-pane');
    if (pane) pane.style.display = 'none';

    const hasMessages = window.state && window.state.messages && window.state.messages.length > 0;
    const chatArea = document.querySelector('.chat-area');
    const inputArea = document.querySelector('.input-area');
    const welcome = document.querySelector('.welcome');

    if (chatArea) chatArea.style.display = '';
    if (welcome) welcome.style.display = hasMessages ? 'none' : 'flex';
    if (inputArea) inputArea.style.display = '';
}

// ── Folder helpers ────────────────────────────────────────────────────────────

function taskBrowseFolder() {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.nativeApp) {
        nativeAction('browse_folder').then(res => {
            if (res && res.path) {
                document.getElementById('task-folder').value = res.path;
            }
        });
    } else {
        // Fallback for non-native (browser testing)
        const path = prompt('Enter folder path:');
        if (path) document.getElementById('task-folder').value = path;
    }
}

function taskSaveFolder() {
    const path = (document.getElementById('task-folder').value || '').trim();
    if (!path) { return; }
    const added = addSavedFolder(path);
    if (!added) {
        // show brief feedback that it's already saved
        const btn = event && event.target ? event.target.closest('button') : null;
        if (btn) {
            const orig = btn.innerHTML;
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Saved!';
            setTimeout(() => { btn.innerHTML = orig; }, 1500);
        }
    }
}

function taskBrowseAndSave() {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.nativeApp) {
        nativeAction('browse_folder').then(res => {
            if (res && res.path) {
                addSavedFolder(res.path);
            }
        });
    } else {
        const path = prompt('Enter folder path to save:');
        if (path) addSavedFolder(path);
    }
}

function selectQuickFolder(btn) {
    const path = btn.getAttribute('data-path');
    document.getElementById('task-folder').value = path;
    // Visual feedback
    const orig = btn.style.borderColor;
    btn.style.borderColor = 'var(--accent)';
    btn.style.background = 'rgba(99,102,241,0.1)';
    setTimeout(() => {
        btn.style.borderColor = orig;
        btn.style.background = 'rgba(255,255,255,0.06)';
    }, 600);
}

function useFolderInTask(path) {
    document.getElementById('task-folder').value = path;
    switchTaskTab('run');
}

// ── Task execution ────────────────────────────────────────────────────────────

async function startTask() {
    const folder = (document.getElementById('task-folder').value || '').trim();
    const task = (document.getElementById('task-desc').value || '').trim();

    if (!folder || !task) {
        alert('Please provide both a folder path and a task description.');
        return;
    }

    document.getElementById('task-start-btn').style.opacity = '0.5';
    document.getElementById('task-start-btn').disabled = true;
    document.getElementById('task-stop-btn').style.display = 'block';
    document.getElementById('task-stream').innerHTML = '';

    try {
        const res = await fetch('/api/task/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folder, task: task })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        currentTaskId = data.task_id;
        connectTaskStream(currentTaskId);
    } catch (e) {
        alert('Failed to start task: ' + e.message);
        cleanupTaskUI();
    }
}

async function stopTask() {
    if (!currentTaskId) return;
    try { await fetch(`/api/task/${currentTaskId}/stop`, { method: 'POST' }); }
    catch (e) { console.error('Stop failed', e); }
}

function connectTaskStream(taskId) {
    if (currentTaskSSE) currentTaskSSE.close();
    currentTaskSSE = new EventSource(`/api/task/${taskId}/stream`);

    currentTaskSSE.onmessage = function(e) {
        const payload = JSON.parse(e.data);
        const ev = payload.event;
        const data = payload.data;

        if (ev === 'started') {
            appendStepBlock('system', `Task started in <code style="font-family:var(--font-mono)">${data.folder}</code>`);
        } else if (ev === 'thinking') {
            upsertStepBlock(data.step, 'thinking', 'Analyzing next step…', null);
        } else if (ev === 'action_proposed') {
            upsertStepBlock(data.step, 'proposed', `[${data.action.type}] ${data.action.progress_message || ''}`, null);
        } else if (ev === 'awaiting_approval') {
            upsertStepBlock(data.step, 'approval', `Requires permission: <strong>${data.action.type}</strong>`, data.action);
        } else if (ev === 'action_skipped') {
            upsertStepBlock(data.step, 'skipped', 'Skipped by user.');
        } else if (ev === 'executing') {
            upsertStepBlock(data.step, 'executing', `Executing <strong>${data.action.type}</strong>…`);
        } else if (ev === 'action_completed') {
            const status = data.result.status === 'ok' ? 'done' : 'error';
            upsertStepBlock(data.step, status, data.result.message || `Done (${data.result.status})`);
        } else if (ev === 'error') {
            upsertStepBlock(data.step, 'error', `Error: ${data.error}`);
        } else if (ev === 'done') {
            appendStepBlock('done', `✓ Task complete: ${data.summary}`);
            cleanupTaskUI();
        } else if (ev === 'closed') {
            cleanupTaskUI();
        }
    };

    currentTaskSSE.onerror = function() {
        cleanupTaskUI();
    };
}

function cleanupTaskUI() {
    if (currentTaskSSE) { currentTaskSSE.close(); currentTaskSSE = null; }
    const startBtn = document.getElementById('task-start-btn');
    const stopBtn = document.getElementById('task-stop-btn');
    if (startBtn) { startBtn.style.opacity = '1'; startBtn.disabled = false; }
    if (stopBtn) stopBtn.style.display = 'none';
}

// ── Step rendering ────────────────────────────────────────────────────────────

const STATE_STYLES = {
    thinking:  { color: 'var(--text-muted)',    border: 'var(--border)',              icon: 'spinner' },
    proposed:  { color: 'var(--accent)',         border: 'rgba(99,102,241,0.3)',       icon: 'dot' },
    approval:  { color: '#f59e0b',               border: 'rgba(245,158,11,0.35)',      icon: 'warn' },
    executing: { color: 'var(--accent)',         border: 'rgba(99,102,241,0.3)',       icon: 'spinner' },
    done:      { color: 'var(--success,#30d158)', border: 'rgba(48,209,88,0.25)',      icon: 'check' },
    error:     { color: 'var(--error,#ff453a)', border: 'rgba(255,69,58,0.3)',         icon: 'x' },
    skipped:   { color: 'var(--text-muted)',    border: 'var(--border)',              icon: 'dash' },
    system:    { color: 'var(--text-muted)',    border: 'var(--border)',              icon: 'info' },
};

function iconSVG(type) {
    if (type === 'spinner') return `<span class="loading-spinner" style="width:12px;height:12px;border-width:2px;display:inline-block;vertical-align:-2px;"></span>`;
    if (type === 'check') return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
    if (type === 'warn')  return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    if (type === 'x')    return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
    if (type === 'dash') return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
    if (type === 'info') return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    return `<span style="width:8px;height:8px;border-radius:50%;background:currentColor;display:inline-block;margin:auto 2px;"></span>`;
}

function appendStepBlock(stateName, html) {
    const stream = document.getElementById('task-stream');
    const style = STATE_STYLES[stateName] || STATE_STYLES.system;
    const div = document.createElement('div');
    div.style.cssText = `padding:12px 16px; background:var(--bg-tertiary); border:1px solid ${style.border}; border-radius:8px; font-size:13px; color:${style.color}; display:flex; align-items:center; gap:10px;`;
    div.innerHTML = `<span style="color:${style.color}; flex-shrink:0;">${iconSVG(style.icon)}</span><span>${html}</span>`;
    stream.appendChild(div);
    stream.parentElement.scrollTop = stream.parentElement.scrollHeight;
}

function upsertStepBlock(stepInt, stateName, message, actionData) {
    const stream = document.getElementById('task-stream');
    let div = document.getElementById(`task-step-${stepInt}`);
    if (!div) {
        div = document.createElement('div');
        div.id = `task-step-${stepInt}`;
        stream.appendChild(div);
    }

    const style = STATE_STYLES[stateName] || STATE_STYLES.system;

    let inner = `
        <div style="padding:12px 16px; background:var(--bg-tertiary); border:1px solid ${style.border}; border-radius:8px; font-size:13px;">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;">
                <span style="font-size:11px; color:var(--text-muted); font-weight:600; text-transform:uppercase; letter-spacing:.05em;">Step ${stepInt}</span>
                <span style="color:${style.color}; display:flex; align-items:center;">${iconSVG(style.icon)}</span>
            </div>
            <div style="color:var(--text-primary);">${message}</div>
    `;

    if (stateName === 'approval' && actionData) {
        inner += `
            <div style="margin-top:10px; padding:12px; background:rgba(245,158,11,0.08); border:1px dashed rgba(245,158,11,0.4); border-radius:6px;">
                <pre style="margin:0 0 10px; font-family:var(--font-mono); font-size:11px; color:var(--text-secondary); overflow-x:auto; white-space:pre-wrap;">${JSON.stringify(actionData.params, null, 2)}</pre>
                <div style="display:flex; gap:8px;">
                    <button onclick="submitDecision(${stepInt},'approve')" style="flex:1; padding:7px; background:#30d158; border:none; border-radius:5px; color:#000; font-size:12px; font-weight:600; cursor:pointer;">✓ Approve</button>
                    <button onclick="submitDecision(${stepInt},'skip')" style="flex:1; padding:7px; background:var(--bg-secondary); border:1px solid var(--border); border-radius:5px; color:var(--text-primary); font-size:12px; cursor:pointer;">⊘ Skip</button>
                </div>
            </div>`;
    }

    inner += '</div>';
    div.innerHTML = inner;
    stream.parentElement.scrollTop = stream.parentElement.scrollHeight;
}

async function submitDecision(stepInt, decision) {
    if (!currentTaskId) return;
    upsertStepBlock(stepInt, 'thinking', `Decision: <strong>${decision}</strong>…`);
    try {
        await fetch(`/api/task/${currentTaskId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision })
        });
    } catch (e) { console.error('Decision failed', e); }
}

// ── CSS for tabs (injected at load time) ─────────────────────────────────────

(function injectTaskStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .task-tab {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 10px 20px;
            background: none;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--text-muted);
            font-size: 13px;
            font-family: var(--font-main);
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
        }
        .task-tab:hover { color: var(--text-primary); }
        .task-tab-active {
            color: var(--accent) !important;
            border-bottom-color: var(--accent) !important;
        }
        #task-mode-pane { display: flex; flex-direction: column; }
    `;
    document.head.appendChild(style);
})();
