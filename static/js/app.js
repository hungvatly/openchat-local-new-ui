/**
 * OpenChat Local — Frontend
 */

const state = {
    messages: [],
    messageMap: {}, // id -> message node
    activeLeafId: null,
    messageMap: {}, // id -> message node
    activeLeafId: null,
    model: null,
    models: [],
    mode: "docs",
    isStreaming: false,
    uploadedFiles: [],
    profile: "medium",
    recommendedModels: [],
    conversationId: null,
    pendingImages: [],  // base64 images for vision
    isRecording: false,
    mediaRecorder: null,
    sessionSystemPrompt: "",   // per-session system prompt (cleared on new conversation)
    ttsEnabled: false,
    userId: localStorage.getItem('ocl_user_id') || 'default',
    userName: localStorage.getItem('ocl_user_name') || 'Default User',
    userColor: localStorage.getItem('ocl_user_color') || '#6366f1',
    privateMode: false,
    deepThink: false,
};

// ── Native Bridge ──────────────────────

function nativeAction(action, payload = {}) {
    return new Promise((resolve) => {
        const callbackId = 'cb_' + Math.random().toString(36).substr(2, 9);
        window._nativeCallback = window._nativeCallback || function(id, data) {
            if (window._nativeCallbacks && window._nativeCallbacks[id]) { 
                window._nativeCallbacks[id](data); 
                delete window._nativeCallbacks[id]; 
            }
        };
        window._nativeCallbacks = window._nativeCallbacks || {};
        window._nativeCallbacks[callbackId] = resolve;
        
        payload.action = action;
        payload.callbackId = callbackId;
        window.webkit.messageHandlers.nativeApp.postMessage(payload);
    });
}

function browseFolder(inputId) {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.nativeApp) {
        nativeAction("browse_folder").then(res => {
            if (res.path) {
                document.getElementById(inputId).value = res.path;
            }
        });
    } else {
        alert("Folder browsing is only available natively. Please paste the path.");
    }
}

function togglePrivateMode(checkbox) {
    if (checkbox.checked) {
        checkbox.checked = false; // reset pending auth
        if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.nativeApp) {
            nativeAction("touch_id", { reason: "Authenticate to enable Private Session" }).then(res => {
                if (res.success) {
                    state.privateMode = true;
                    checkbox.checked = true;
                } else {
                    alert("Authentication failed.");
                }
            });
        } else {
            state.privateMode = true; // Web fallback
            checkbox.checked = true;
        }
    } else {
        state.privateMode = false;
    }
}

function openNewUserModal() {
    closeUserPanel();
    document.getElementById('new-user-name').value = '';
    document.getElementById('new-user-password').value = '';
    document.getElementById('new-user-modal').classList.add('active');
}

// ── DOM refs ───────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const welcomeEl = $(".welcome");
const chatContainerEl = $(".chat-container");
const chatAreaEl = $(".chat-area");
const textareaEl = $("#chat-input");
const sendBtn = $("#send-btn");
const modelSelect = $("#model-select");
const charCount = $(".char-count");
const statusDot = $(".status-dot");
const modeSelect = $("#mode-select");

// ── Init ───────────────────────────

async function init() {
    // Configure marked.js for rich rendering
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            highlight: function(code, lang) {
                if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                return typeof hljs !== 'undefined' ? hljs.highlightAuto(code).value : code;
            },
            breaks: true,
            gfm: true,
        });
    }
    if (typeof mermaid !== 'undefined') {
        mermaid.initialize({ startOnLoad: false, theme: 'dark' });
    }

    // ── Load theme FIRST so CSS vars are available everywhere (including setup screen) ──
    await loadTheme();

    // ── Setup Block Check ──
    try {
        const setupRes = await fetch("/api/setup/status");
        if (setupRes.ok) {
            const setupInfo = await setupRes.json();
            if (!setupInfo.has_admin) {
                // Halt init and show polished setup screen
                const lang = localStorage.getItem('openchat_lang') || 'en';
                const t = (key, fallback) => (translations[lang] && translations[lang][key]) || (translations['en'] && translations['en'][key]) || fallback;

                document.body.innerHTML = '';
                const screen = document.createElement('div');
                screen.id = 'admin-setup-screen';
                screen.style.cssText = 'display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;background:var(--bg-primary);font-family:var(--font-main);';
                screen.innerHTML = `
                    <div style="text-align:center;margin-bottom:28px;">
                        <div style="width:64px;height:64px;background:var(--accent);border-radius:16px;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        </div>
                        <h2 style="font-size:22px;font-weight:700;color:var(--text-primary);margin:0 0 8px;">${t('setup_welcome', 'Welcome to OpenChat Local')}</h2>
                        <p style="font-size:14px;color:var(--text-muted);margin:0;">${t('setup_desc', 'Create the Administrator account to get started')}</p>
                    </div>
                    <div style="background:var(--bg-secondary);padding:28px;border-radius:12px;border:1px solid var(--border);width:340px;box-shadow:0 8px 24px rgba(0,0,0,0.3);">

                        <label style="display:block;font-size:11px;font-weight:600;color:var(--text-muted);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;">${t('setup_password', 'Password (Required)')}</label>
                        <input type="password" id="setup-admin-pass" placeholder="Choose a strong password" autocomplete="new-password"
                            style="width:100%;box-sizing:border-box;padding:10px 12px;background:rgba(255,255,255,0.06);border:1px solid var(--border);border-radius:8px;color:var(--text-primary);font-size:14px;font-family:var(--font-main);outline:none;margin-bottom:24px;transition:border-color 0.2s;"
                            onfocus="this.style.borderColor='var(--accent)'" onblur="this.style.borderColor='var(--border)'">

                        <div id="setup-error" style="display:none;color:#f87171;font-size:12px;margin-bottom:12px;padding:8px 12px;background:rgba(239,68,68,0.1);border-radius:6px;border:1px solid rgba(239,68,68,0.25);"></div>

                        <button id="setup-admin-btn"
                            style="width:100%;padding:12px;background:var(--accent);border:none;border-radius:8px;color:#fff;font-weight:600;font-size:15px;font-family:var(--font-main);cursor:pointer;transition:opacity 0.2s;letter-spacing:0.01em;"
                            onmouseenter="this.style.opacity='0.88'" onmouseleave="this.style.opacity='1'">
                            ${t('setup_btn', 'Set Password')}
                        </button>
                    </div>
                    <p style="margin-top:20px;font-size:12px;color:var(--text-muted);text-align:center;max-width:300px;">${t('setup_tip', 'This account will have full admin privileges. Keep your password safe.')}</p>
                `;
                document.body.appendChild(screen);

                const btn = document.getElementById('setup-admin-btn');
                const errEl = document.getElementById('setup-error');

                const doSetup = async () => {
                    const name = "Admin";
                    const pass = document.getElementById('setup-admin-pass').value;
                    if (!pass || pass.length < 4) {
                        errEl.textContent = t('setup_err_pass', 'Password must be at least 4 characters.');
                        errEl.style.display = 'block';
                        return;
                    }
                    errEl.style.display = 'none';
                    btn.textContent = t('setup_creating', 'Creating…');
                    btn.disabled = true;
                    btn.style.opacity = '0.6';

                    try {
                        const res = await fetch('/api/users', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name, password: pass, avatar_color: '#f59e0b' })
                        });
                        if (res.ok) {
                            window.location.reload();
                        } else {
                            const d = await res.json().catch(() => ({}));
                            errEl.textContent = d.error || t('setup_err_generic', 'Failed to create admin. Please try again.');
                            errEl.style.display = 'block';
                            btn.textContent = t('setup_btn', 'Set Password');
                            btn.disabled = false;
                            btn.style.opacity = '1';
                        }
                    } catch (e) {
                        errEl.textContent = t('setup_err_generic', 'Network error. Is the server running?');
                        errEl.style.display = 'block';
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.textContent = t('setup_btn', 'Set Password');
                    }
                };

                btn.addEventListener('click', doSetup);
                document.getElementById('setup-admin-pass').addEventListener('keydown', e => { if (e.key === 'Enter') doSetup(); });

                return; // Halt initialization until admin is set up
            }
        }
    } catch (e) {
        console.error("Failed to check setup status", e);
    }

    // Load admin user and enforce lock screen
    await loadUsers();
    const adminUser = _users.find(u => u.is_admin === 1) || _users[0];
    if (adminUser) {
        state.userId = adminUser.id;
        state.userName = adminUser.name;
        
        // Update welcome greeting
        const greetSpan = document.querySelector('.welcome h1 span');
        if (greetSpan) greetSpan.textContent = state.userName.split(' ')[0];

        if (adminUser.has_password && !sessionStorage.getItem('ocl_authenticated')) {
            pendingAuthUser = adminUser;
            document.getElementById('auth-modal').classList.add('active');
            document.getElementById('auth-password').focus();
            return; // Halt initialization until logged in
        }
    }
    
    await finishInit();
}

async function finishInit() {
    await checkHealth();
    await loadModels();
    await loadConversations();
    await loadFolders();
    await loadKnowledgeFolders();
    setupListeners();
    textareaEl.focus();
}

async function checkHealth() {
    try {
        const res = await fetch("/api/health");
        const data = await res.json();
        statusDot.classList.toggle("connected", data.engine_ready);
        state.profile = data.profile || "medium";
        state.recommendedModels = data.recommended_models || [];
        if (data.rag) {
            const statsEl = $("#rag-stats");
            if (statsEl) statsEl.remove();
        }
        const profileEl = $("#hw-profile");
        if (profileEl) profileEl.textContent = state.profile;
    } catch {
        statusDot.classList.remove("connected");
    }
}

async function loadModels() {
    try {
        const res = await fetch("/api/models");
        const data = await res.json();
        state.models = data.models || [];
        state.model = data.default;

        modelSelect.innerHTML = "";
        if (state.models.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No models found";
            modelSelect.appendChild(opt);
            return;
        }

        const hasOllama = state.models.some(m => m.provider === "ollama");
        const hasLocal  = state.models.some(m => m.provider === "local");

        state.models.forEach((m) => {
            const opt = document.createElement("option");
            opt.value = m.name;
            // Show provider prefix only when both types exist
            let label = m.name;
            if (hasOllama && hasLocal) {
                label = m.provider === "ollama" ? `[Ollama] ${m.name}` : `[Local] ${m.name}`;
            }
            opt.textContent = label;
            if (m.name === state.model) opt.selected = true;
            modelSelect.appendChild(opt);
        });

        // If nothing was pre-selected, pick the first one
        if (!state.model && state.models.length > 0) {
            state.model = state.models[0].name;
            modelSelect.value = state.model;
        }
    } catch {
        modelSelect.innerHTML = '<option value="">No models found</option>';
    }
}

// ── Listeners ──────────────────────

function setupListeners() {
    textareaEl.addEventListener("input", () => {
        textareaEl.style.height = "auto";
        textareaEl.style.height = Math.min(textareaEl.scrollHeight, 160) + "px";
        charCount.textContent = `${textareaEl.value.length}/1000`;
    });

    textareaEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            // Use window.sendMessage so the compare-mode patch (set in DOMContentLoaded) is respected
            (window.sendMessage || sendMessage)();
        }
    });

    sendBtn.addEventListener("click", () => {
        if (state.isStreaming) {
            stopGenerating();
            return;
        }
        (window.sendMessage || sendMessage)();
    });
    modelSelect.addEventListener("change", (e) => (state.model = e.target.value));

    if (modeSelect) {
        modeSelect.addEventListener("change", (e) => {
            state.mode = e.target.value;
        });
    }

    $$(".prompt-card").forEach((card) => {
        card.addEventListener("click", () => {
            textareaEl.value = card.querySelector(".prompt-card-text").textContent;
            textareaEl.dispatchEvent(new Event("input"));
            sendMessage();
        });
    });

    $(".refresh-btn").addEventListener("click", shufflePrompts);

    // Sidebar
    $("#btn-new-chat").addEventListener("click", showNewChatPicker);
    const toggle = $("#sidebar-toggle");
    if (toggle) {
        toggle.addEventListener("click", () => {
            const sidebar = $(".sidebar");
            const isMobile = window.innerWidth <= 768;
            if (isMobile) {
                // Mobile: overlay mode
                const isOpen = sidebar.classList.contains("mobile-open");
                sidebar.classList.toggle("mobile-open", !isOpen);
                let backdrop = $(".sidebar-backdrop");
                if (!backdrop) {
                    backdrop = document.createElement("div");
                    backdrop.className = "sidebar-backdrop";
                    document.body.appendChild(backdrop);
                    backdrop.addEventListener("click", () => {
                        sidebar.classList.remove("mobile-open");
                        backdrop.classList.remove("active");
                    });
                }
                backdrop.classList.toggle("active", !isOpen);
            } else {
                sidebar.classList.toggle("collapsed");
            }
        });
    }


    // Panels
    $$(".panel-overlay").forEach((overlay) => {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) overlay.classList.remove("active");
        });
    });
}

// ── Chat ───────────────────────────

async function sendMessage(overrideText = undefined, overrideParentId = undefined) {
    const text = overrideText !== undefined ? overrideText : textareaEl.value.trim();
    if (!text || state.isStreaming) return;

    const parentId = overrideParentId !== undefined ? overrideParentId : state.activeLeafId;

    // UI Branching Truncation: Rewind the visual thread to the parent node immediately if we are editing/branching
    if (overrideParentId !== undefined && overrideParentId !== state.activeLeafId) {
        state.activeLeafId = overrideParentId;
        renderActiveThread();
    }

    state.isStreaming = true;
    sendBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12"/></svg>`;
    sendBtn.title = "Stop generating";

    siriGlow.start();

    welcomeEl.classList.add("hidden");
    chatAreaEl.classList.add("active");

    // Show image previews if attached
    const isBranching = overrideParentId !== undefined;
    if (!isBranching) {
        // Normal send: immediately show user bubble in DOM (streaming feel)
        if (state.pendingImages.length > 0) {
            const imgPreview = document.createElement("div");
            imgPreview.className = "message message-user";
            imgPreview.innerHTML = `<div class="message-content"><img src="data:image/jpeg;base64,${state.pendingImages[0]}" style="max-width:200px;border-radius:8px;margin-bottom:4px"><br>${escapeHtml(text)}</div>`;
            chatAreaEl.appendChild(imgPreview);
        } else {
            appendMessage("user", text);
        }
        state.messages.push({ role: "user", content: text });
    }

    // Reset height, clear input immediately
    textareaEl.value = "";
    textareaEl.style.height = "auto";
    charCount.textContent = "0/1000";

    const aiMsgEl = appendMessage("ai", "");
    const contentEl = aiMsgEl.querySelector(".message-content");
    contentEl.innerHTML = '<div class="loading-status"><div class="loading-spinner"></div> Model is thinking...</div>';

    let fullText = "";
    const lang = localStorage.getItem('openchat_lang') || 'en';
    const langMap = { "en": "English", "vi": "Vietnamese", "zh-TW": "Traditional Chinese", "ru": "Russian" };
    
    const defaultSysPrompt = `LANGUAGE RULE (HIGHEST PRIORITY): You MUST respond in the exact same language as the user's message. If the user writes in Vietnamese → respond entirely in Vietnamese. If in English → respond in English. Never switch languages. This overrides everything else.

You are a helpful, harmless, and honest AI assistant. Your goal is to be genuinely useful while being thoughtful about safety and accuracy.

## Core Behavior
- Be warm, direct, and conversational. Avoid over-formatting with bullet points, headers, and bold text unless the user asks for it or the content genuinely requires structure.
- Write in natural prose and paragraphs for most responses. Keep casual conversations short — a few sentences is often enough.
- Don't start responses with "Great question!" or similar filler. Just answer.
- Don't use emojis unless the user does.
- Avoid words like "genuinely," "honestly," "straightforward," and "delve."
- Don't ask more than one clarifying question per response. When a request is slightly ambiguous, make a reasonable assumption, proceed, and note the assumption briefly.`;

    const activeSystemPrompt = state.sessionSystemPrompt || defaultSysPrompt;

    state.abortController = new AbortController();
    let lastDoneData = null;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: state.abortController.signal,
            body: JSON.stringify({
                message: text,
                model: state.model,
                mode: state.mode,
                history: state.messages.slice(-10),
                parent_id: parentId,
                conversation_id: state.conversationId,
                images: state.pendingImages,
                session_system_prompt: activeSystemPrompt,
                user_id: state.userId,
                folder_ids: _knowledgeFolderIds,
                is_private: state.privateMode,
                deep_think: state.deepThink,
            }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let sources = [];
        let fileInfo = null;
        let gotFirstToken = false;
        let thinkText = "";
        let responseText = "";
        let inThinkBlock = false;
        let thinkDone = false;

        // ── Split bubble into two live zones ──────────────────────────────
        //   [thinkZone]    — animated panel while model reasons
        //   [responseZone] — final answer streamed after </think>
        let thinkZone = null;
        let thinkContent = null;
        let responseZone = contentEl;

        function _ensureThinkZone() {
            if (thinkZone) return;
            thinkZone = document.createElement('div');
            thinkZone.className = 'think-live-panel think-live-active';
            thinkZone.innerHTML = [
                '<div class="think-live-header">',
                '  <span class="think-live-dots"><span></span><span></span><span></span></span>',
                '  <span class="think-live-label">Thinking...</span>',
                '</div>',
                '<div class="think-live-body"></div>'
            ].join('');
            aiMsgEl.insertBefore(thinkZone, contentEl);
            thinkContent = thinkZone.querySelector('.think-live-body');

            const rz = document.createElement('div');
            rz.className = 'message-content think-response-zone';
            aiMsgEl.insertBefore(rz, contentEl);
            contentEl.style.display = 'none';
            responseZone = rz;
        }

        function _finaliseThinkZone() {
            if (!thinkZone || thinkDone) return;
            thinkDone = true;
            thinkZone.classList.remove('think-live-active');
            thinkZone.classList.add('think-live-done');
            const header = thinkZone.querySelector('.think-live-header');
            header.innerHTML = [
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">',
                '  <path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/>',
                '</svg>',
                '<span class="think-live-label">Thought for a moment</span>',
                '<button class="think-toggle-btn" onclick="this.closest(\'.think-live-panel\').classList.toggle(\'think-expanded\')">',
                '  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">',
                '    <polyline points="6 9 12 15 18 9"/>',
                '  </svg>',
                '</button>'
            ].join('');
        }

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\n");

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                try {
                    const evt = JSON.parse(line.slice(6));
                    if (evt.token !== undefined) {
                        if (!gotFirstToken) {
                            contentEl.innerHTML = "";
                            gotFirstToken = true;
                        }

                        fullText += evt.token;

                        const thinkOpen  = fullText.indexOf('<think>');
                        const thinkClose = fullText.indexOf('</think>');

                        if (thinkOpen !== -1 && !thinkDone) {
                            _ensureThinkZone();
                            inThinkBlock = thinkClose === -1;

                            if (thinkClose !== -1) {
                                thinkText    = fullText.slice(thinkOpen + 7, thinkClose);
                                responseText = fullText.slice(thinkClose + 8);
                                thinkContent.innerHTML = renderMarkdown(thinkText);
                                _finaliseThinkZone();
                                responseZone.innerHTML = renderMarkdown(responseText);
                            } else {
                                thinkText = fullText.slice(thinkOpen + 7);
                                thinkContent.innerHTML = renderMarkdown(thinkText);
                            }
                        } else if (thinkDone) {
                            responseText = fullText.slice(fullText.indexOf('</think>') + 8);
                            responseZone.innerHTML = renderMarkdown(responseText);
                        } else {
                            responseZone.innerHTML = renderMarkdown(fullText);
                        }

                        chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
                    }
                    if (evt.done) {
                        sources = evt.sources || [];
                        if (evt.conversation_id) {
                            state.conversationId = evt.conversation_id;
                            _updateSessionPromptBar();
                        }
                        fileInfo = evt.file || null;
                        lastDoneData = evt;
                        if (thinkZone && !thinkDone) _finaliseThinkZone();
                        // Animate sidebar title as soon as it arrives
                        if (evt.title && evt.conversation_id) {
                            _animateSidebarTitle(evt.conversation_id, evt.title);
                        }
                    }
                } catch {}
            }
        }

        // Show sources
        if (sources.length > 0) {
            const srcDiv = document.createElement("div");
            srcDiv.className = "sources";
            const seen = new Set();
            sources.forEach((s) => {
                if (seen.has(s.source)) return;
                seen.add(s.source);
                if (s.url) {
                    const link = document.createElement("a");
                    link.className = "source-tag source-link";
                    link.href = s.url;
                    link.target = "_blank";
                    link.rel = "noopener";
                    link.textContent = s.source;
                    srcDiv.appendChild(link);
                } else {
                    const tag = document.createElement("button");
                    tag.className = "source-tag source-doc";
                    tag.dataset.source = s.source;
                    const cIds = s.chunk_indexes || [];
                    const col = s.collection || 'documents';
                    tag.onclick = () => openSourceViewer(s.source, cIds, col);
                    tag.textContent = s.source;
                    srcDiv.appendChild(tag);
                }
            });
            aiMsgEl.appendChild(srcDiv);
        }

        // Save the new nodes to the branch tree and re-render with toolbars
        if (lastDoneData && lastDoneData.user_message_id && lastDoneData.message_id) {
            const uId = lastDoneData.user_message_id;
            const aId = lastDoneData.message_id;

            if (!state.messageMap[uId]) {
                state.messageMap[uId] = {
                    id: uId,
                    parent_id: parentId !== undefined ? parentId : null,
                    active_child_index: 0,
                    role: "user",
                    content: text,
                    children: [],
                    _sources: [],
                };
            }
            // Wire into parent's children (handles branching)
            const pIdStr = (parentId === undefined || parentId === null) ? 'root' : parentId;
            if (state.messageMap[pIdStr]) {
                const par = state.messageMap[pIdStr];
                if (!par.children.includes(uId)) {
                    par.children.push(uId);
                }
                // Always point parent's active_child_index at this new branch
                const newChildIdx = par.children.indexOf(uId);
                par.active_child_index = newChildIdx;
                // Persist to DB so reload shows correct branch (or LocalStorage for root)
                if (pIdStr === 'root') {
                    localStorage.setItem(`conv_${state.conversationId}_root_idx`, newChildIdx);
                } else {
                    fetch(`/api/messages/${parentId}/switch-branch`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ direction: '_set', index: newChildIdx })
                    }).catch(() => {});
                }
            }

            if (!state.messageMap[aId]) {
                state.messageMap[aId] = {
                    id: aId,
                    parent_id: uId,
                    active_child_index: 0,
                    role: "assistant",
                    content: fullText,
                    children: [],
                    _sources: sources,
                };
                state.messageMap[uId].children.push(aId);
            }
            state.activeLeafId = aId;

            renderActiveThread();
            postRenderEnhance();
            if (state.ttsEnabled && fullText) speakText(fullText);
            // loadConversations() is called after _animateSidebarTitle settles,
            // but we still need a reload to persist the new item in the list
            if (lastDoneData && lastDoneData.title) {
                _animateSidebarTitle(state.conversationId, lastDoneData.title);
            }
            loadConversations();
            generateFollowUps(fullText, document.getElementById(`msg-${aId}`));
            return;  // ← skip finally's loadConversation timeout
        }

        // Fallback for private mode (no IDs)
        if (fileInfo) {
            const dlDiv = document.createElement("div");
            dlDiv.className = "doc-download-row";
            dlDiv.innerHTML = `
                <a href="${fileInfo.url}" download="${fileInfo.filename}" class="doc-preview-btn primary">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Download
                </a>
                <button class="doc-preview-btn" onclick="openArtifactViewer('', '${fileInfo.filename}', '${fileInfo.url}', '${fileInfo.filename.split('.').pop().toUpperCase()}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    Preview
                </button>
            `;
            aiMsgEl.appendChild(dlDiv);
        }

        // Render citations naturally for finished texts inside loop block
        if (state.messages && fullText) {
            state.messages.push({ role: "assistant", content: fullText });
        }
        state.pendingImages = [];
        clearImagePreview();
        postRenderEnhance();
        if (state.ttsEnabled && fullText) speakText(fullText);
        loadConversations();
        generateFollowUps(fullText, aiMsgEl);
        siriGlow.stop();

    } catch (err) {
        if (err.name === "AbortError") {
            // User stopped generation — show a subtle stopped badge on the bubble
            if (fullText) {
                contentEl.innerHTML = renderMarkdown(fullText);
            } else {
                contentEl.innerHTML = '';
            }
            const stoppedBadge = document.createElement('div');
            stoppedBadge.style.cssText = 'display:inline-flex;align-items:center;gap:5px;margin-top:8px;font-size:11px;color:var(--text-muted);background:rgba(255,255,255,0.05);border:1px solid var(--border);border-radius:5px;padding:3px 9px;';
            stoppedBadge.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12"/></svg> Generation stopped`;
            contentEl.appendChild(stoppedBadge);
            state.wasStopped = true;
        } else {
            contentEl.innerHTML = `<p style="color:var(--error)">Error: ${err.message}. Do you have a model loaded?</p>`;
        }
    } finally {
        state.isStreaming = false;
        state.wasStopped = false;
        sendBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;
        sendBtn.title = "";
        sendBtn.disabled = false;
        siriGlow.stop();
        textareaEl.focus();
        // Only reload from DB on abort if there was NO partial text shown
        // (avoids wiping streamed content the user can still read)
        if (!lastDoneData && state.conversationId && !fullText) {
            setTimeout(() => loadConversation(state.conversationId), 500);
        }
    }
}

function stopGenerating() {
    if (state.abortController) {
        state.abortController.abort();
    }
    // Immediate UI feedback: flicker the button to show it registered
    sendBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"/></svg>`;
    sendBtn.disabled = true;
}

function appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = `message message-${role}`;
    div.innerHTML = `<div class="message-content">${role === "user" ? escapeHtml(text) : renderMarkdown(text)}</div>`;

    // Add export toolbar to AI messages
    if (role === "ai" && text) {
        const toolbar = document.createElement("div");
        toolbar.className = "message-export-toolbar";
        toolbar.innerHTML = `
            <button class="export-btn" onclick="exportResponse(this, 'pdf')" title="Export as PDF">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                PDF
            </button>
            <button class="export-btn" onclick="exportResponse(this, 'docx')" title="Export as Word">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                DOCX
            </button>
            <button class="export-btn" onclick="exportResponse(this, 'xlsx')" title="Export as Excel">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
                XLSX
            </button>
            <button class="export-btn" onclick="copyResponse(this)" title="Copy text">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                Copy
            </button>
        `;
        div.appendChild(toolbar);
    }

    chatAreaEl.appendChild(div);
    chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
    return div;
}

function renderActiveThread() {
    chatAreaEl.innerHTML = "";
    state.messages = [];

    if (!state.activeLeafId || !state.messageMap[state.activeLeafId]) return;

    // Walk UP from leaf to collect the active path, then reverse
    let path = [];
    let curr = state.activeLeafId;
    while (curr && state.messageMap[curr]) {
        path.unshift(state.messageMap[curr]);
        curr = state.messageMap[curr].parent_id;
    }

    path.forEach(m => {
        _appendNodeToUI(m);
        state.messages.push({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content });
    });

    chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
    postRenderEnhance();
}

async function switchBranch(parentMsgId, direction) {
    try {
        const parentNode = state.messageMap[parentMsgId];
        if (!parentNode || !parentNode.children || parentNode.children.length <= 1) return;

        let newIdx;
        if (parentMsgId === 'root') {
            let curIdx = parentNode.active_child_index || 0;
            if (direction === 'prev') {
                newIdx = Math.max(0, curIdx - 1);
            } else if (direction === 'next') {
                newIdx = Math.min(parentNode.children.length - 1, curIdx + 1);
            } else {
                newIdx = curIdx; // _set is not currently used by UI for root, but if it is:
            }
            localStorage.setItem(`conv_${state.conversationId}_root_idx`, newIdx);
            parentNode.active_child_index = newIdx;
        } else {
            // Persist the branch switch to the DB so it survives reload
            const res = await fetch(`/api/messages/${parentMsgId}/switch-branch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ direction })
            });
            const data = await res.json();
            if (!res.ok) return;
            newIdx = data.active_child_index;
            parentNode.active_child_index = newIdx;
        }

        // Walk to its leaf following active_child_index.
        let curr = state.messageMap[parentNode.children[newIdx]];
        if (!curr) return;
        while (curr.children && curr.children.length > 0) {
            const ci = Math.min(curr.active_child_index || 0, curr.children.length - 1);
            curr = state.messageMap[curr.children[ci]];
        }
        state.activeLeafId = curr.id;
        renderActiveThread();
    } catch(e) {
        console.error('switchBranch error:', e);
    }
}

function beginEditMessage(id) {
    const el = document.getElementById("msg-content-" + id);
    if (!el) return;
    const node = state.messageMap[id];
    el.innerHTML = `
        <div style="background:var(--bg-secondary); border-radius:12px; padding:12px; display:flex; flex-direction:column; gap:8px;">
            <div style="border:1px solid var(--accent); border-radius:8px; padding:8px; background:var(--bg-primary); transition:all 0.2s;">
                <textarea class="message-edit-box" id="msg-edit-ta-${id}" style="width:100%; border:none; background:transparent; color:var(--text-primary); outline:none; resize:vertical; font-family:var(--font-main); font-size:14px; min-height:60px;" onfocus="this.parentElement.style.borderColor='var(--accent)'" onblur="this.parentElement.style.borderColor='var(--border)'">${escapeHtml(node.content)}</textarea>
            </div>
            <div style="display:flex; align-items:center; justify-content:space-between; margin-top:2px;">
                <div style="font-size:12px; color:var(--text-muted); display:flex; align-items:flex-start; gap:6px; max-width:65%; line-height:1.4;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-top:2px; flex-shrink:0;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                    <span>Editing creates a new branch. Use ‹ › arrows to switch between branches.</span>
                </div>
                <div class="message-edit-actions" style="display:flex; gap:8px; margin-top:0;">
                    <button class="btn btn-outline" style="padding:6px 14px; font-size:13px;" onclick="renderActiveThread()">Cancel</button>
                    <button class="btn" style="padding:6px 14px; font-size:13px; background:var(--text-primary); color:var(--bg-primary);" onclick="submitEditMessage(${id})">Save</button>
                </div>
            </div>
        </div>
    `;
}

function submitEditMessage(id) {
    const node = state.messageMap[id];
    const ta = document.getElementById("msg-edit-ta-" + id);
    if (!ta) return;
    const newText = ta.value.trim();
    if (!newText || newText === node.content) {
        renderActiveThread();
        return;
    }
    // Branch off from this message's parent
    // node.parent_id = the message above this one.
    // We send newText as a NEW message whose parent is node.parent_id
    sendMessage(newText, node.parent_id);
}

function regenerateMessage(id) {
    const node = state.messageMap[id]; // AI message
    if (!node) return;
    // Branch off from the user message that prompted this AI response
    const parentNode = node.parent_id !== null ? state.messageMap[node.parent_id] : null;
    if (parentNode && parentNode.role === 'user') {
        // Resend same user text, branching from parentNode's parent
        sendMessage(parentNode.content, parentNode.parent_id);
    }
}

function _appendNodeToUI(m) {
    const role = m.role === "user" ? "user" : "ai";
    const div = document.createElement("div");
    div.className = `message message-${role}`;
    div.id = `msg-${m.id}`;

    let contentHtml = `<div class="message-content" id="msg-content-${m.id}">${role === "user" ? escapeHtml(m.content) : renderMarkdown(m.content)}</div>`;

    let toolbarHtml = `<div class="message-export-toolbar">`;
    if (role === "user") {
        toolbarHtml += `
            <button class="export-btn" onclick="beginEditMessage(${m.id})" title="Edit & resend">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                Edit
            </button>
        `;
    } else {
        toolbarHtml += `
            <button class="export-btn" onclick="regenerateMessage(${m.id})" title="Regenerate answer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
                Regen
            </button>
            <button class="export-btn" onclick="exportResponse(this,'pdf')" title="Export PDF">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                PDF
            </button>
        `;
    }

    toolbarHtml += `
        <button class="export-btn" onclick="copyResponse(this)" title="Copy text">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            Copy
        </button>
        ${ role === 'ai' ? `<button class="export-btn" onclick="speakMessageById(${m.id})" title="Read aloud">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>
            Read
        </button>` : '' }
    </div>`;

    // Branch Navigation: show ‹ 2/3 › on any message that is a non-first-or-only child
    let navHtml = "";
    const pIdStr = (m.parent_id === null || m.parent_id === undefined) ? 'root' : m.parent_id;
    if (state.messageMap[pIdStr]) {
        const parent = state.messageMap[pIdStr];
        if (parent.children && parent.children.length > 1) {
            const idx = parent.children.indexOf(m.id);
            const total = parent.children.length;
            const prevDir = 'prev';
            const nextDir = 'next';
            const pIdArg = pIdStr === 'root' ? "'root'" : pIdStr;
            navHtml = `
            <div class="branch-nav">
                <button class="branch-nav-btn" ${idx === 0 ? "disabled style='opacity:0.3'" : ""} onclick="switchBranch(${pIdArg}, '${prevDir}')">‹</button>
                <span>${idx + 1} / ${total}</span>
                <button class="branch-nav-btn" ${idx === total - 1 ? "disabled style='opacity:0.3'" : ""} onclick="switchBranch(${pIdArg}, '${nextDir}')">›</button>
            </div>`;
        }
    }

    if (role === "user") {
        div.innerHTML = toolbarHtml + navHtml + contentHtml;
    } else {
        div.innerHTML = contentHtml + navHtml + toolbarHtml;
    }

    // Render sources if stored (e.g. after reload)
    const srcs = m._sources || [];
    if (srcs.length > 0) {
        const srcDiv = document.createElement("div");
        srcDiv.className = "sources";
        const seen = new Set();
        srcs.forEach(s => {
            if (seen.has(s.source)) return;
            seen.add(s.source);
            if (s.url) {
                const a = document.createElement("a");
                a.className = "source-tag source-link";
                a.href = s.url; a.target = "_blank"; a.rel = "noopener";
                a.textContent = s.source;
                srcDiv.appendChild(a);
            } else {
                const btn = document.createElement("button");
                btn.className = "source-tag source-doc";
                btn.dataset.source = s.source;
                const col = s.collection || 'documents';
                btn.onclick = () => openSourceViewer(s.source, s.chunk_indexes || [], col);
                btn.textContent = s.source;
                srcDiv.appendChild(btn);
            }
        });
        div.appendChild(srcDiv);
    }

    chatAreaEl.appendChild(div);
    return div;
}


function clearChat() {
    state.messages = [];
    state.messageMap = {
        'root': {
            id: 'root',
            parent_id: null,
            active_child_index: 0,
            children: []
        }
    };
    state.activeLeafId = null;
    state.conversationId = null;
    state.pendingImages = [];
    state.sessionSystemPrompt = '';   // reset per-session prompt on new chat
    chatAreaEl.innerHTML = "";
    chatAreaEl.classList.remove("active");
    welcomeEl.classList.remove("hidden");
    clearImagePreview();
    const bar = $('#session-prompt-btn');
    if (bar) bar.style.display = 'none';
    const dot = $('#session-prompt-dot');
    if (dot) dot.style.display = 'none';
    textareaEl.focus();
}

// ── Markdown (rich rendering) ─────

function renderMarkdown(text) {
    if (!text) return "";

    // Parse <think> tags — for historical messages. Live streaming uses split-DOM in sendMessage.
    text = text.replace(/<think>([\s\S]*?)(<\/think>|$)/g, function(match, thought, closing) {
        var isClosed = closing === '<\/think>';
        var label = isClosed ? 'Thought for a moment' : 'Thinking...';
        var checkIcon = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>';
        var dotsHtml = '<span class="think-live-dots"><span></span><span></span><span></span></span>';
        var toggleBtn = '<button class="think-toggle-btn" onclick="this.closest(\'.think-live-panel\').classList.toggle(\'think-expanded\')">'
            + '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg></button>';
        var panelClass = isClosed ? 'think-live-panel think-live-done' : 'think-live-panel think-live-active';
        var headerHtml = isClosed
            ? (checkIcon + '<span class="think-live-label">' + label + '</span>' + toggleBtn)
            : (dotsHtml + '<span class="think-live-label">' + label + '</span>');
        var bodyClass = isClosed ? 'think-live-body think-body-collapsed' : 'think-live-body';
        return '\n\n<div class="' + panelClass + '">'
            + '<div class="think-live-header">' + headerHtml + '</div>'
            + '<div class="' + bodyClass + '">' + thought.trim() + '</div>'
            + '</div>\n\n';
    });

    // Use marked.js if available
    if (typeof marked !== 'undefined') {
        try {
            // Custom renderer for code blocks with copy button
            const renderer = new marked.Renderer();
            const origCode = renderer.code;
            renderer.code = function(code, lang) {
                // Mermaid diagrams
                if (lang === 'mermaid') {
                    return `<div class="mermaid-container"><div class="mermaid">${escapeHtml(typeof code === 'object' ? code.text || '' : code)}</div><div class="mermaid-label">Diagram</div></div>`;
                }
                const codeText = typeof code === 'object' ? code.text || '' : code;
                const codeLang = typeof code === 'object' ? code.lang || '' : (lang || '');
                let highlighted = escapeHtml(codeText);
                if (typeof hljs !== 'undefined') {
                    try {
                        highlighted = codeLang && hljs.getLanguage(codeLang)
                            ? hljs.highlight(codeText, { language: codeLang }).value
                            : hljs.highlightAuto(codeText).value;
                    } catch(e) {}
                }
                const langLabel = codeLang ? `<span class="code-lang">${codeLang}</span>` : '';
                const isPreviewable = ['html', 'svg', 'xml', 'htm'].includes(codeLang.toLowerCase());
                const previewBtn = isPreviewable ? `<button class="code-preview-btn" onclick="previewCanvas(this)" style="position:absolute; right:55px; top:4px; padding:2px 8px; font-size:11px; border-radius:4px; background:rgba(255,255,255,0.1); border:1px solid var(--border); color:var(--text-secondary); cursor:pointer; font-family:var(--font-main);">Preview</button>` : '';
                return `<div class="code-block" style="position:relative">${langLabel}${previewBtn}<button class="code-copy-btn" onclick="copyCode(this)">Copy</button><pre><code class="hljs language-${codeLang}">${highlighted}</code></pre></div>`;
            };

            // Wrap tables in scrollable container
            renderer.table = function(header, body) {
                const headerContent = typeof header === 'object' ? header.header || '' : header || '';
                const bodyContent = typeof header === 'object' ? header.rows?.map(r => `<tr>${r.map(c => `<td>${c.text}</td>`).join('')}</tr>`).join('') : body || '';
                // For marked v12+, header is an object with { header, rows }
                if (typeof header === 'object' && header.header) {
                    const hdrCells = header.header.map(h => `<th>${h.text}</th>`).join('');
                    const bodyRows = (header.rows || []).map(r => `<tr>${r.map(c => `<td>${c.text}</td>`).join('')}</tr>`).join('');
                    return `<div class="table-wrapper"><table><thead><tr>${hdrCells}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
                }
                return `<div class="table-wrapper"><table><thead>${headerContent}</thead><tbody>${bodyContent}</tbody></table></div>`;
            };

            return marked.parse(text, { renderer: renderer, breaks: true, gfm: true });
        } catch(e) {
            console.error('marked.js error:', e);
        }
    }

    // Fallback: basic markdown
    let html = escapeHtml(text);
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => `<pre><code>${code.trim()}</code></pre>`);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");
    html = html.split("\n\n").map(p => { p=p.trim(); if(!p) return ""; if(p.startsWith("<")) return p; return `<p>${p}</p>`; }).join("");
    return html;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function copyCode(btn) {
    const code = btn.closest('.code-block').querySelector('code');
    navigator.clipboard.writeText(code.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 1500);
    });
}

function copyResponse(btn) {
    const msg = btn.closest('.message');
    const content = msg.querySelector('.message-content');
    // Get text content (strips HTML)
    navigator.clipboard.writeText(content.innerText).then(() => {
        const origText = btn.innerHTML;
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
        setTimeout(() => btn.innerHTML = origText, 1500);
    });
}

async function exportResponse(btn, format) {
    const msg = btn.closest('.message');
    const content = msg.querySelector('.message-content');
    const text = content.innerText;

    // Show loading state
    const origText = btn.innerHTML;
    btn.innerHTML = `<span class="typing-indicator" style="display:inline-flex;gap:2px;margin-right:4px"><span></span><span></span><span></span></span> Generating…`;
    btn.disabled = true;

    try {
        // Determine a title from the first line or heading
        const lines = text.split('\n').filter(l => l.trim());
        let title = lines[0] || 'Document';
        title = title.replace(/^#+\s*/, '').substring(0, 60);

        const endpoint = format === 'xlsx' ? '/api/generate/xlsx'
                       : format === 'docx' ? '/api/generate/docx'
                       : '/api/generate/pdf';

        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, content: text }),
        });
        const data = await res.json();

        if (data.status === 'ok' && data.url) {
            // Trigger download
            const a = document.createElement('a');
            a.href = data.url;
            a.download = data.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Downloaded!`;
            setTimeout(() => { btn.innerHTML = origText; }, 2000);
        } else {
            btn.innerHTML = `✕ ${data.message || 'Error'}`;
            setTimeout(() => { btn.innerHTML = origText; }, 3000);
        }
    } catch (err) {
        btn.innerHTML = `✕ Failed`;
        setTimeout(() => { btn.innerHTML = origText; }, 2000);
    }
    btn.disabled = false;
}

function postRenderEnhance() {
    // Render mermaid diagrams
    if (typeof mermaid !== 'undefined') {
        try {
            document.querySelectorAll('.mermaid:not([data-processed])').forEach(el => {
                el.setAttribute('data-processed', 'true');
                const id = 'mermaid-' + Math.random().toString(36).substr(2, 9);
                mermaid.render(id, el.textContent).then(({svg}) => {
                    el.innerHTML = svg;
                }).catch(() => {});
            });
        } catch(e) {}
    }

    // Wrap any unwrapped tables in scrollable containers
    document.querySelectorAll('.message-ai .message-content table:not(.wrapped)').forEach(table => {
        table.classList.add('wrapped');
        if (!table.parentElement.classList.contains('table-wrapper')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'table-wrapper';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        }
    });

    // Render KaTeX math: $...$ and $$...$$
    if (typeof katex !== 'undefined') {
        document.querySelectorAll('.message-ai .message-content').forEach(el => {
            // Block math: $$...$$
            el.innerHTML = el.innerHTML.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex) => {
                try { return katex.renderToString(tex.trim(), { displayMode: true }); }
                catch(e) { return `<code>${tex}</code>`; }
            });
            // Inline math: $...$
            el.innerHTML = el.innerHTML.replace(/\$([^\$\n]+?)\$/g, (_, tex) => {
                try { return katex.renderToString(tex.trim(), { displayMode: false }); }
                catch(e) { return `<code>${tex}</code>`; }
            });
        });
    }
}

// ── Prompt cards ───────────────────

const PROMPTS = [
    "Summarize the key points from my documents",
    "What are the main topics covered in my files?",
    "Generate a to-do list from my notes",
    "Write an email reply based on my documents",
    "Find any dates or deadlines mentioned in my files",
    "Explain the technical concepts in my documents",
    "Compare the ideas across my uploaded files",
    "Create a study guide from my materials",
    "What questions do my documents leave unanswered?",
    "Extract all names and entities from my files",
    "Summarize each uploaded document in one sentence",
    "What are the action items from my meeting notes?",
];

function shufflePrompts() {
    const cards = $$(".prompt-card-text");
    const shuffled = [...PROMPTS].sort(() => Math.random() - 0.5);
    cards.forEach((card, i) => {
        if (shuffled[i]) card.textContent = shuffled[i];
    });
}

// ── Upload Panel ───────────────────

function openUploadPanel() {
    $("#upload-panel").classList.add("active");
    loadWatcherStatus();
}

// Called by the static hidden file input's onchange (works in WKWebView)
function toggleProgress(type, show) {
    const progressContainer = $(`#${type}-progress-container`);
    const progressBar = $(`#${type}-progress-bar`);
    if (!progressContainer || !progressBar) return;
    
    if (show) {
        progressContainer.classList.add("active");
        progressBar.classList.add("indeterminate");
        progressBar.style.width = "30%"; // reset for indeterminate
    } else {
        progressBar.classList.remove("indeterminate");
        progressBar.style.width = "100%";
        setTimeout(() => {
            progressContainer.classList.remove("active");
            progressBar.style.width = "0%";
        }, 500);
    }
}

async function pollTask(taskId, statusEl, type, onSuccess) {
    return new Promise((resolve) => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks/${taskId}`);
                const task = await res.json();
                
                if (task.status === "running") {
                    const percent = task.total > 0 ? Math.round((task.progress / task.total) * 100) : 0;
                    if (task.message) {
                        statusEl.textContent = task.total > 0 ? `${task.message} — ${percent}%` : task.message;
                    }
                    const progressBar = $(`#${type}-progress-bar`);
                    if (progressBar && task.total > 0) {
                        progressBar.classList.remove("indeterminate");
                        progressBar.style.width = `${percent}%`;
                    }
                } else if (task.status === "completed") {
                    clearInterval(interval);
                    if (onSuccess && task.result) await onSuccess(task.result);
                    resolve();
                } else if (task.status === "error") {
                    clearInterval(interval);
                    statusEl.textContent = `Error: ${task.error}`;
                    resolve();
                }
            } catch (err) {
                // Ignore transient network errors during polling
            }
        }, 500);
    });
}

async function handleFileUpload(input) {
    const statusEl = $("#upload-status");
    const listEl = $("#file-list");
    
    if (!input.files || input.files.length === 0) return;

    for (const file of input.files) {
        const isPdf = file.name.toLowerCase().endsWith(".pdf");
        statusEl.textContent = isPdf
            ? `Processing ${file.name}… (scanned PDFs may take up to 30s for OCR)`
            : `Uploading & Indexing ${file.name}…`;

        // Show indeterminate progress animation
        toggleProgress('upload', true);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/documents/upload", {
                method: "POST",
                body: formData,
            });
            const data = await res.json();

            if (data.status === "processing") {
                await pollTask(data.task_id, statusEl, 'upload', (result) => {
                    if (result.status === "ok") {
                        const item = document.createElement("div");
                        item.className = "file-item";
                        const chunkNote = result.chunks === 0
                            ? `<span style="color:var(--error);font-size:12px">0 chunks — file may be empty or unreadable</span>`
                            : `<span class="file-chunks">${result.chunks} chunks</span>`;
                        item.innerHTML = `<span class="file-name">${result.filename}</span>${chunkNote}`;
                        listEl.appendChild(item);
                        state.uploadedFiles.push(result.filename);
                        statusEl.textContent = result.chunks > 0
                            ? `✓ ${result.filename} indexed (${result.chunks} chunks)`
                            : `⚠ ${result.filename} uploaded but no text extracted`;
                    } else {
                        statusEl.textContent = `Error: ${result.error || result.message}`;
                    }
                });
            } else {
                statusEl.textContent = `Error: ${data.error || data.message}`;
            }
        } catch (err) {
            statusEl.textContent = `Upload failed: ${err.message}`;
        }
        
        // Hide progress bar when done
        toggleProgress('upload', false);
    }

    // Reset input so same file can be re-uploaded if needed
    input.value = "";
    await checkHealth();
}

// Legacy — kept for any other callers
function uploadFile() {
    const input = $("#file-upload-input");
    if (input) input.click();
}

async function ingestFolder() {
    const folderInput = $("#folder-path");
    const path = folderInput.value.trim();
    if (!path) return;

    const statusEl = $("#upload-status");
    statusEl.textContent = "Indexing folder...";
    toggleProgress('upload', true);

    try {
        const res = await fetch("/api/documents/folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder_path: path }),
        });
        const data = await res.json();

        if (data.status === "processing") {
            await pollTask(data.task_id, statusEl, 'upload', (result) => {
                if (result.status === "ok") {
                    statusEl.textContent = `Indexed ${result.files_processed} files`;
                    const listEl = $("#file-list");
                    result.details.forEach((f) => {
                        const item = document.createElement("div");
                        item.className = "file-item";
                        item.innerHTML = `
                            <span class="file-name">${f.filename}</span>
                            <span class="file-chunks">${f.chunks} chunks</span>
                        `;
                        listEl.appendChild(item);
                    });
                } else {
                    statusEl.textContent = `Error: ${result.error}`;
                }
            });
        } else {
            statusEl.textContent = `Error: ${data.error}`;
        }
    } catch (err) {
        statusEl.textContent = `Error: ${err.message}`;
    } finally {
        toggleProgress('upload', false);
    }

    await checkHealth();
}

async function ingestYouTube() {
    const urlInput = $("#youtube-url");
    const url = urlInput.value.trim();
    if (!url) return;

    const statusEl = $("#upload-status");
    statusEl.textContent = "Extracting transcript...";

    try {
        const res = await fetch("/api/documents/youtube", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
        });
        const data = await res.json();
        statusEl.textContent = data.status === "ok"
            ? `YouTube video indexed (${data.chunks} chunks)`
            : `Error: ${data.error}`;
    } catch (err) {
        statusEl.textContent = `Error: ${err.message}`;
    }

    urlInput.value = "";
    await checkHealth();
}

async function clearDocuments() {
    const ok = await showConfirm('Clear all indexed documents? This cannot be undone.');
    if (!ok) return;
    await fetch("/api/documents/clear", { method: "POST" });
    $("#file-list").innerHTML = "";
    $("#upload-status").textContent = "All documents cleared";
    state.uploadedFiles = [];
    await checkHealth();
}

// ── Watch Folder ───────────────────

async function addWatchFolder() {
    const input = $("#watch-folder-path");
    const labelInput = $("#watch-folder-label");
    const folder = input.value.trim();
    if (!folder) return;

    const statusEl = $("#watch-status");
    statusEl.textContent = "Adding knowledge folder...";
    toggleProgress('watch', true);

    try {
        const res = await fetch("/api/watcher/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder, label: labelInput ? labelInput.value.trim() : "" }),
        });
        const data = await res.json();

        if (data.status === "processing") {
            await pollTask(data.task_id, statusEl, 'watch', async (result) => {
                if (result.status === "ok") {
                    const count = result.initial_scan ? result.initial_scan.indexed : 0;
                    statusEl.textContent = count > 0
                        ? `\u2713 Watching "${result.label}"! Indexed ${count} file(s).`
                        : `\u2713 Watching "${result.label}"! No new files yet.`;
                    input.value = "";
                    if (labelInput) labelInput.value = "";
                    await loadWatcherStatus();
                    await loadKnowledgeFolders();
                } else {
                    statusEl.textContent = `Error: ${result.message || result.error}`;
                }
            });
        } else {
            statusEl.textContent = `Error: ${data.message || data.error}`;
        }
    } catch (err) {
        statusEl.textContent = `Error: ${err.message}`;
    } finally {
        toggleProgress('watch', false);
    }

    await checkHealth();
}

async function removeWatchFolder(folder) {
    try {
        await fetch("/api/watcher/remove", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder }),
        });
        await loadWatcherStatus();
    } catch {}
}

async function forceScan() {
    const statusEl = $("#watch-status");
    statusEl.textContent = "Scanning...";
    toggleProgress('watch', true);

    try {
        const res = await fetch("/api/watcher/scan", { method: "POST" });
        const data = await res.json();
        if (data.status === "processing") {
            await pollTask(data.task_id, statusEl, 'watch', (result) => {
                const count = (result.indexed || []).length;
                if (count > 0) {
                    const names = result.indexed.map((f) => f.filename).join(", ");
                    statusEl.textContent = `Found and indexed ${count} new file(s): ${names}`;
                } else {
                    statusEl.textContent = "No new or changed files found.";
                }
            });
        } else {
            statusEl.textContent = "Error starting scan.";
        }
    } catch (err) {
        statusEl.textContent = `Scan error: ${err.message}`;
    } finally {
        toggleProgress('watch', false);
    }

    await checkHealth();
    await loadWatcherStatus();
}

async function reindexAll() {
    const statusEl = $("#watch-status");
    statusEl.textContent = "⏳ Clearing index and re-indexing all files…";
    toggleProgress('watch', true);

    try {
        const res = await fetch("/api/watcher/reindex", { method: "POST" });
        const data = await res.json();
        if (data.status === "processing") {
            await pollTask(data.task_id, statusEl, 'watch', (result) => {
                const count = (result.indexed || []).length;
                if (count > 0) {
                    const names = result.indexed.map((f) => f.filename).join(", ");
                    statusEl.textContent = `✓ Re-indexed ${count} file(s): ${names}`;
                } else {
                    statusEl.textContent = "Re-index complete — no files found to index.";
                }
            });
        } else {
            statusEl.textContent = "Error starting re-index.";
        }
    } catch (err) {
        statusEl.textContent = `Re-index error: ${err.message}`;
    } finally {
        toggleProgress('watch', false);
    }

    await checkHealth();
    await loadWatcherStatus();
}

async function loadWatcherStatus() {
    try {
        const res = await fetch("/api/watcher/status");
        const data = await res.json();
        const container = $("#watch-folders");
        if (!container) return;

        container.innerHTML = "";
        const folders = data.folders || [];
        if (folders.length > 0) {
            folders.forEach((f) => {
                const item = document.createElement("div");
                item.style.cssText = "display:flex;align-items:center;justify-content:space-between;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;font-size:13px;gap:8px";
                item.innerHTML = `
                    <div style="flex:1;min-width:0">
                        <div style="font-weight:500;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(f.path)}">${escapeHtml(f.label)}</div>
                        <div style="font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(f.path)} &bull; <span style="color:var(--accent)">${f.chunk_count} chunks</span></div>
                    </div>
                `;
                const rmBtn = document.createElement('button');
                rmBtn.style.cssText = 'background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:11px;padding:2px 6px;flex-shrink:0';
                rmBtn.textContent = '✕ Remove';
                rmBtn.dataset.path = f.path;
                rmBtn.addEventListener('click', () => removeWatchFolder(f.path));
                item.appendChild(rmBtn);
                container.appendChild(item);
            });

            const info = document.createElement("div");
            info.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:4px";
            const mins = Math.round(data.poll_interval / 60);
            const intervalLabel = mins >= 1 ? `${mins} min` : `${data.poll_interval}s`;
            info.textContent = `${data.total_files_tracked} files tracked · ${data.total_auto_indexed} auto-indexed · auto-scan every ${intervalLabel}`;
            container.appendChild(info);
        } else {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:4px 0">No knowledge folders added yet.</div>';
        }
    } catch {}
}

// ── Settings Panel ─────────────────

function openSettingsPanel() {
    $('#settings-panel').classList.add('active');
    refreshModelManager();
    loadMcpServers();
    loadOllamaStatus();
    loadWatcherStatus();
    loadSystemPrompt();  // Load current system prompt into textarea
    renderSettingsUserList();  // Refresh user list
}

// ── System Prompt ───────────────────

async function loadSystemPrompt() {
    try {
        const res = await fetch('/api/personas/default');
        if (!res.ok) return;
        const data = await res.json();
        const ta = $('#system-prompt-input');
        if (ta) {
            ta.value = data.prompt || `You are a helpful, harmless, and honest AI assistant. Your goal is to be genuinely useful while being thoughtful about safety and accuracy.

## Core Behavior

- Be warm, direct, and conversational. Avoid over-formatting with bullet points, headers, and bold text unless the user asks for it or the content genuinely requires structure.
- Write in natural prose and paragraphs for most responses. Keep casual conversations short — a few sentences is often enough.
- Don't start responses with "Great question!" or similar filler. Just answer.
- Don't use emojis unless the user does.
- Avoid words like "genuinely," "honestly," "straightforward," and "delve."
- Don't ask more than one clarifying question per response. When a request is slightly ambiguous, make a reasonable assumption, proceed, and note the assumption briefly.

## Language Matching

- ALWAYS respond in the same language the user writes in. If the user writes in Vietnamese, respond in Vietnamese. If they write in French, respond in French. This applies to every message — detect the language of each new message and match it.
- If the user switches languages mid-conversation, switch with them immediately.
- If the user writes in a mix of languages (e.g., code-switching between English and another language), match their dominant language while preserving any technical terms or proper nouns they used in the other language.
- Never default to English unless the user is writing in English.
- Maintain the same tone, quality, and depth of response regardless of which language you're using. Don't give shorter or less helpful answers just because the language isn't English.

## Knowledge & Accuracy

- If you're unsure about something, say so. Don't fabricate facts, citations, or quotes.
- Distinguish clearly between what you know confidently and what you're uncertain about.
- For time-sensitive topics (current events, who holds a position, recent releases), acknowledge that your training data has a cutoff and you may not have the latest information.

## Tone & Style

- Match the user's energy. If they're casual, be casual. If they're formal, be more precise.
- Illustrate explanations with examples, analogies, or thought experiments when helpful.
- Be willing to express nuanced views on complex topics rather than giving empty "both sides" answers, but present alternative perspectives fairly.
- Push back constructively when the user is mistaken — don't just agree to be agreeable — but do so with kindness.

## Safety & Ethics

- Don't help with creating weapons, malware, or harmful substances.
- Don't generate sexual content involving minors.
- Don't write persuasive content that puts fabricated quotes in real people's mouths.
- For legal or financial questions, share relevant information but remind the user you're not a professional advisor.
- Care about the user's wellbeing. Don't encourage self-destructive behavior even if asked.

## Formatting Defaults

- Default to prose. Use lists only when the content is inherently list-like or the user requests it.
- For code, use fenced code blocks with the language specified.
- Keep responses as concise as the question warrants. A simple question deserves a simple answer.`;
        }
    } catch {}
}

async function saveSystemPrompt() {
    const ta = $('#system-prompt-input');
    const statusEl = $('#system-prompt-status');
    if (!ta) return;

    const prompt = ta.value.trim();

    try {
        const res = await fetch('/api/personas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: 'default',
                name: 'Default',
                prompt: prompt,
            }),
        });
        if (res.ok) {
            if (statusEl) {
                statusEl.textContent = '✓ Saved';
                statusEl.style.color = 'var(--success)';
                setTimeout(() => {
                    statusEl.textContent = '';
                }, 2500);
            }
        } else {
            if (statusEl) { statusEl.textContent = 'Save failed'; statusEl.style.color = 'var(--error)'; }
        }
    } catch (err) {
        if (statusEl) { statusEl.textContent = `Error: ${err.message}`; statusEl.style.color = 'var(--error)'; }
    }
}

async function resetSystemPrompt() {
    const ta = $('#system-prompt-input');
    const statusEl = $('#system-prompt-status');
    if (!ta) return;
    ta.value = `You are a helpful, harmless, and honest AI assistant. Your goal is to be genuinely useful while being thoughtful about safety and accuracy.

## Core Behavior

- Be warm, direct, and conversational. Avoid over-formatting with bullet points, headers, and bold text unless the user asks for it or the content genuinely requires structure.
- Write in natural prose and paragraphs for most responses. Keep casual conversations short — a few sentences is often enough.
- Don't start responses with "Great question!" or similar filler. Just answer.
- Don't use emojis unless the user does.
- Avoid words like "genuinely," "honestly," "straightforward," and "delve."
- Don't ask more than one clarifying question per response. When a request is slightly ambiguous, make a reasonable assumption, proceed, and note the assumption briefly.

## Language Matching

- ALWAYS respond in the same language the user writes in. If the user writes in Vietnamese, respond in Vietnamese. If they write in French, respond in French. This applies to every message — detect the language of each new message and match it.
- If the user switches languages mid-conversation, switch with them immediately.
- If the user writes in a mix of languages (e.g., code-switching between English and another language), match their dominant language while preserving any technical terms or proper nouns they used in the other language.
- Never default to English unless the user is writing in English.
- Maintain the same tone, quality, and depth of response regardless of which language you're using. Don't give shorter or less helpful answers just because the language isn't English.

## Knowledge & Accuracy

- If you're unsure about something, say so. Don't fabricate facts, citations, or quotes.
- Distinguish clearly between what you know confidently and what you're uncertain about.
- For time-sensitive topics (current events, who holds a position, recent releases), acknowledge that your training data has a cutoff and you may not have the latest information.

## Tone & Style

- Match the user's energy. If they're casual, be casual. If they're formal, be more precise.
- Illustrate explanations with examples, analogies, or thought experiments when helpful.
- Be willing to express nuanced views on complex topics rather than giving empty "both sides" answers, but present alternative perspectives fairly.
- Push back constructively when the user is mistaken — don't just agree to be agreeable — but do so with kindness.

## Safety & Ethics

- Don't help with creating weapons, malware, or harmful substances.
- Don't generate sexual content involving minors.
- Don't write persuasive content that puts fabricated quotes in real people's mouths.
- For legal or financial questions, share relevant information but remind the user you're not a professional advisor.
- Care about the user's wellbeing. Don't encourage self-destructive behavior even if asked.

## Formatting Defaults

- Default to prose. Use lists only when the content is inherently list-like or the user requests it.
- For code, use fenced code blocks with the language specified.
- Keep responses as concise as the question warrants. A simple question deserves a simple answer.`;
    await saveSystemPrompt();
    if (statusEl) {
        statusEl.textContent = 'Reset to default';
        setTimeout(() => { statusEl.textContent = ''; }, 2000);
    }
}

// ── Ollama Server ───────────────────

async function loadOllamaStatus() {
    const badge = $("#ollama-status-badge");
    const msg = $("#ollama-status-msg");
    const urlInput = $("#ollama-url-input");
    const modelsList = $("#ollama-models-list");
    if (!badge) return;

    badge.textContent = "Checking...";
    badge.style.color = "var(--text-muted)";
    try {
        const res = await fetch("/api/ollama/status");
        const data = await res.json();
        if (urlInput) urlInput.value = data.url || "";

        if (data.connected) {
            badge.textContent = "Connected";
            badge.style.background = "rgba(34,197,94,0.15)";
            badge.style.color = "var(--success)";
            badge.style.borderColor = "rgba(34,197,94,0.4)";
            if (msg) msg.textContent = `${data.models.length} model(s) available`;

            if (modelsList) {
                modelsList.innerHTML = "";
                (data.models || []).forEach(m => {
                    const row = document.createElement("div");
                    row.style.cssText = "font-size:12px;color:var(--text-secondary);padding:4px 8px;background:var(--bg-primary);border-radius:4px;border:1px solid var(--border);display:flex;justify-content:space-between";
                    row.innerHTML = `<span>${escapeHtml(m.name)}</span><span style="color:var(--text-muted)">${m.parameter_size || ''} ${m.quantization || ''}</span>`;
                    modelsList.appendChild(row);
                });
            }
        } else {
            badge.textContent = "Disconnected";
            badge.style.background = "rgba(239,68,68,0.12)";
            badge.style.color = "var(--error)";
            badge.style.borderColor = "rgba(239,68,68,0.3)";
            if (msg) msg.textContent = "Ollama not reachable at this URL.";
            if (modelsList) modelsList.innerHTML = "";
        }
    } catch(err) {
        if (badge) badge.textContent = "Error";
        if (msg) msg.textContent = err.message;
    }
}

async function saveOllamaUrl() {
    const urlInput = $("#ollama-url-input");
    const btn = $("#ollama-save-btn");
    const msg = $("#ollama-status-msg");
    const url = urlInput ? urlInput.value.trim() : "";
    if (!url) return;

    if (btn) { btn.disabled = true; btn.textContent = "Testing..."; }
    if (msg) msg.textContent = "";
    try {
        const res = await fetch("/api/ollama/url", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
        });
        const data = await res.json();
        if (data.status === "ok") {
            if (msg) msg.textContent = `\u2713 Connected! ${data.models.length} model(s) available.`;
            await loadOllamaStatus();
        } else {
            if (msg) { msg.textContent = data.error || "Failed"; msg.style.color = "var(--error)"; }
        }
    } catch(err) {
        if (msg) { msg.textContent = err.message; msg.style.color = "var(--error)"; }
    }
    if (btn) { btn.disabled = false; btn.textContent = "Test & Save"; }
}

// ── Knowledge Folder Selector ───────

let _knowledgeFolderIds = [];  // selected collection IDs

async function loadKnowledgeFolders() {
    try {
        const res = await fetch("/api/watcher/indexes");
        const data = await res.json();
        const sel = $("#knowledge-select");
        if (!sel) return;

        const current = sel.value;
        sel.innerHTML = '<option value="">All Knowledge</option>';
        (data.indexes || []).forEach(idx => {
            const opt = document.createElement("option");
            opt.value = idx.id;
            opt.textContent = `${idx.label} (${idx.chunk_count})`;
            sel.appendChild(opt);
        });
        // Restore previous selection if still valid
        if (current && [...sel.options].some(o => o.value === current)) sel.value = current;
    } catch {}
}

function onKnowledgeChange(value) {
    _knowledgeFolderIds = value ? [value] : [];
}

// ── Conversation History ──────────

// ── Theme System ──────────────────

async function loadTheme() {
    try {
        // Try localStorage first for instant apply (no flash)
        const cached = localStorage.getItem('ocl_theme');
        if (cached) applyTheme(cached, false);
        // Then verify against server
        const res = await fetch('/api/settings');
        const data = await res.json();
        if (data.theme) applyTheme(data.theme, false);
    } catch {
        // localStorage fallback already handled
    }

    // Restore custom background color
    const customBg = localStorage.getItem('ocl_bg_color');
    if (customBg) applyCustomBgColor(customBg);

    // Restore chat background color
    const chatBgColor = localStorage.getItem('ocl_chat_bg_color');
    if (chatBgColor) applyChatBgColor(chatBgColor);

    // Restore chat background image
    const chatBgImage = localStorage.getItem('ocl_chat_bg_image');
    if (chatBgImage) {
        const mainEl = document.querySelector('main.main');
        if (mainEl) {
            mainEl.style.backgroundImage = `url(${chatBgImage})`;
            mainEl.style.backgroundSize = 'cover';
            mainEl.style.backgroundPosition = 'center';
            mainEl.style.backgroundRepeat = 'no-repeat';
            mainEl.classList.add('has-chat-bg');
        }
        const wrap = document.getElementById('chat-bg-img-wrap');
        const thumb = document.getElementById('chat-bg-img-thumb');
        if (wrap && thumb) { wrap.style.display = 'block'; thumb.src = chatBgImage; }
    }
}


function applyTheme(theme, persist = true) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ocl_theme', theme);
    // Update swatch active state
    document.querySelectorAll('.theme-swatch').forEach(sw => {
        sw.classList.toggle('active', sw.dataset.theme === theme);
    });
    // Remove any leftover inline accent variables from previous manual picks
    document.documentElement.style.removeProperty('--accent');
    document.documentElement.style.removeProperty('--accent-hover');
    localStorage.removeItem('ocl_accent_color');

    if (persist) {
        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme }),
        }).catch(() => {});
    }
}

// ── Background Color Picker ───────
function hexToRgb(hex) {
    const r = parseInt(hex.slice(1,3), 16);
    const g = parseInt(hex.slice(3,5), 16);
    const b = parseInt(hex.slice(5,7), 16);
    return { r, g, b };
}

function applyCustomBgColor(color) {
    const { r, g, b } = hexToRgb(color);
    // Derive a surface color family from the picked base
    const root = document.documentElement;
    root.style.setProperty('--bg-primary',   `rgba(${r},${g},${b},0.0)`);
    root.style.setProperty('--bg-secondary',  `rgba(${r},${g},${b},0.7)`);
    root.style.setProperty('--bg-tertiary',   `rgba(${Math.min(r+18,255)},${Math.min(g+18,255)},${Math.min(b+18,255)},0.7)`);
    root.style.setProperty('--bg-input',      `rgba(${r},${g},${b},0.85)`);
    root.style.setProperty('--bg-card',       `rgba(${Math.min(r+12,255)},${Math.min(g+12,255)},${Math.min(b+12,255)},0.6)`);
    root.style.setProperty('--theme-swatch-bg', color);
    localStorage.setItem('ocl_bg_color', color);
    const picker = document.getElementById('custom-bg-color');
    if (picker) picker.value = color;
    const preview = document.getElementById('custom-bg-preview');
    if (preview) preview.style.background = color;
}

function resetCustomBgColor() {
    const root = document.documentElement;
    ['--bg-primary','--bg-secondary','--bg-tertiary','--bg-input','--bg-card','--theme-swatch-bg']
        .forEach(v => root.style.removeProperty(v));
    localStorage.removeItem('ocl_bg_color');
    const picker = document.getElementById('custom-bg-color');
    if (picker) picker.value = '#0a0a0a';
    const preview = document.getElementById('custom-bg-preview');
    if (preview) preview.style.background = '#0a0a0a';
}


// ── Chat Background Color ─────────

function applyChatBgColor(color) {
    const mainEl = document.querySelector('main.main');
    if (mainEl) mainEl.style.backgroundColor = color;
    localStorage.setItem('ocl_chat_bg_color', color);
    const picker = document.getElementById('chat-bg-color');
    if (picker) picker.value = color;
    const preview = document.getElementById('chat-bg-preview');
    if (preview) preview.style.background = color;
}

function resetChatBgColor() {
    const mainEl = document.querySelector('main.main');
    if (mainEl) mainEl.style.backgroundColor = '';
    localStorage.removeItem('ocl_chat_bg_color');
    const picker = document.getElementById('chat-bg-color');
    if (picker) picker.value = '#0d0d0f';
    const preview = document.getElementById('chat-bg-preview');
    if (preview) preview.style.background = '#0d0d0f';
}

// ── Chat Background Image ─────────

function applyChatBgImage(inputEl) {
    const file = inputEl.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        const dataUrl = e.target.result;
        const mainEl = document.querySelector('main.main');
        if (mainEl) {
            mainEl.style.backgroundImage = `url(${dataUrl})`;
            mainEl.style.backgroundSize = 'cover';
            mainEl.style.backgroundPosition = 'center';
            mainEl.style.backgroundRepeat = 'no-repeat';
            mainEl.classList.add('has-chat-bg');
        }
        localStorage.setItem('ocl_chat_bg_image', dataUrl);
        // Show preview thumb
        const wrap = document.getElementById('chat-bg-img-wrap');
        const thumb = document.getElementById('chat-bg-img-thumb');
        if (wrap && thumb) { wrap.style.display = 'block'; thumb.src = dataUrl; }
    };
    reader.readAsDataURL(file);
}

function removeChatBgImage() {
    const mainEl = document.querySelector('main.main');
    if (mainEl) {
        mainEl.style.backgroundImage = '';
        mainEl.classList.remove('has-chat-bg');
    }
    localStorage.removeItem('ocl_chat_bg_image');
    const wrap = document.getElementById('chat-bg-img-wrap');
    if (wrap) wrap.style.display = 'none';
    const inp = document.getElementById('chat-bg-image-input');
    if (inp) inp.value = '';
}

// ── Uploaded Files Manager ────────

async function loadUploadedFiles() {
    const container = document.getElementById('uploaded-files-list');
    if (!container) return;
    container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Loading...</div>';
    try {
        const res = await fetch('/api/documents/list');
        const data = await res.json();
        const files = data.files || [];
        if (files.length === 0) {
            container.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No uploaded files found.</div>';
            return;
        }
        container.innerHTML = '';
        files.forEach(f => {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg-tertiary);border-radius:6px;font-size:12px;';
            const origName = f.filename.replace(/^[0-9a-f]{32}_/, '');
            row.innerHTML = `
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2" style="flex-shrink:0"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-secondary)">${escapeHtml(origName)}</span>
                <span style="color:var(--text-muted);flex-shrink:0">${f.size_mb} MB</span>
                <button onclick="deleteUploadedFile('${escapeHtml(f.filename)}')" style="background:none;border:none;cursor:pointer;color:var(--error);padding:2px;opacity:0.6;flex-shrink:0" title="Delete file">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            `;
            container.appendChild(row);
        });
    } catch(e) {
        container.innerHTML = `<div style="font-size:12px;color:var(--error)">Error: ${e.message}</div>`;
    }
}

async function deleteUploadedFile(filename) {
    const displayName = filename.replace(/^[0-9a-f]{32}_/, '');
    const ok = await showConfirm(`Delete "${displayName}"? This will remove it from the index.`);
    if (!ok) return;
    try {
        const res = await fetch('/api/documents/file', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            loadUploadedFiles();
        } else {
            alert(data.error || 'Delete failed');
        }
    } catch(e) {
        alert('Error: ' + e.message);
    }
}


// ── Application Lock System ────────

let _users = [];
let pendingAuthUser = null;

async function loadUsers() {
    try {
        const res = await fetch('/api/users');
        const data = await res.json();
        _users = data.users || [];
    } catch {
        _users = [];
    }
}

async function submitAuth() {
    if (!pendingAuthUser) return;
    const pwd = document.getElementById('auth-password').value;
    const errEl = document.getElementById('auth-error');
    try {
        const res = await fetch('/api/users/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: pendingAuthUser.id, password: pwd })
        });
        if (res.ok) {
            if (errEl) errEl.style.display = 'none';
            document.getElementById('auth-password').value = '';
            document.getElementById('auth-modal').classList.remove('active');
            sessionStorage.setItem('ocl_authenticated', 'true');
            pendingAuthUser = null;
            await finishInit();
        } else {
            if (errEl) {
                errEl.textContent = getTranslation('auth_wrong', 'Incorrect password. Please try again.');
                errEl.style.display = 'block';
            }
            document.getElementById('auth-password').select();
        }
    } catch {
        if (errEl) { errEl.textContent = 'Network error.'; errEl.style.display = 'block'; }
    }
}

// ── Auto-Title Animation ──────────

/**
 * Immediately update the sidebar title for a conversation with a fade animation.
 * Called as soon as the SSE 'done' event delivers the generated title —
 * before the full loadConversations() reload completes.
 *
 * @param {string} convId   - The conversation ID whose sidebar item to update
 * @param {string} newTitle - The AI-generated title string
 */
function _animateSidebarTitle(convId, newTitle) {
    if (!convId || !newTitle) return;
    // Find the session item in the sidebar
    const container = document.getElementById('sidebar-sessions');
    if (!container) return;

    // Session items embed the convId in the onclick of .session-title
    // They may not have a data-id attribute, so we match by onclick content
    const allItems = container.querySelectorAll('.session-item');
    let titleEl = null;
    for (const item of allItems) {
        const span = item.querySelector('.session-title');
        if (span && span.getAttribute('onclick') && span.getAttribute('onclick').includes(convId)) {
            titleEl = span;
            break;
        }
    }

    if (!titleEl) return;

    // Fade-out → swap text → fade-in
    titleEl.style.transition = 'opacity 0.2s ease';
    titleEl.style.opacity = '0';
    setTimeout(() => {
        // Preserve any folder badge (last child) when replacing text
        const badge = titleEl.querySelector('span');
        titleEl.textContent = newTitle;
        if (badge) titleEl.appendChild(badge);
        titleEl.style.opacity = '1';
    }, 200);
}

// ── Conversation History ──────────

async function loadConversations(folderFilter) {
    try {
        let url = `/api/conversations?user_id=${encodeURIComponent(state.userId)}`;
        if (folderFilter) url += `&folder=${encodeURIComponent(folderFilter)}`;
        const res = await fetch(url);
        const data = await res.json();
        const container = $("#sidebar-sessions");
        if (!container) return;

        container.innerHTML = "";
        const convs = data.conversations || [];

        if (convs.length === 0) {
            container.innerHTML = '<div style="padding:12px 6px;font-size:12px;color:var(--text-muted)">No conversations yet</div>';
            return;
        }

        // Group by date
        const today = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86400000).toDateString();
        let lastGroup = "";

        convs.forEach((c) => {
            const d = new Date(c.updated_at * 1000).toDateString();
            let group = "Older";
            if (d === today) group = "Today";
            else if (d === yesterday) group = "Yesterday";
            else {
                const days = Math.floor((Date.now() - c.updated_at * 1000) / 86400000);
                if (days <= 7) group = "This week";
                else if (days <= 30) group = "This month";
            }
            if (group !== lastGroup) {
                const label = document.createElement("div");
                label.className = "sidebar-label";
                label.textContent = group;
                container.appendChild(label);
                lastGroup = group;
            }

            const folderBadge = c.folder ? `<span style="font-size:10px;color:var(--text-muted);background:var(--bg-tertiary);padding:1px 6px;border-radius:3px;margin-left:4px">${escapeHtml(c.folder)}</span>` : '';
            const isLocked = c.is_locked;

            const item = document.createElement("div");
            item.className = "session-item" + (c.id === state.conversationId ? " active" : "") + (isLocked ? " locked" : "");

            if (isLocked) {
                item.innerHTML = `
                    <svg class="session-lock-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                    <span class="session-title" onclick="openUnlockModal('${c.id}')" style="cursor:pointer">Locked Chat${folderBadge}</span>
                    <div class="session-actions">
                        <button class="session-action-btn delete" onclick="var e = arguments[0] || window.event; if(e) e.stopPropagation(); deleteConversation('${c.id}')" title="Delete">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                `;
            } else {
                item.innerHTML = `
                    <span class="session-title" onclick="loadConversation('${c.id}')">${escapeHtml(c.title || 'New Chat')}${folderBadge}</span>
                    <div class="session-actions">
                        <button class="session-action-btn" onclick="var e = arguments[0] || window.event; if(e) e.stopPropagation(); setFolder('${c.id}')" title="Set folder">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                        </button>
                        <button class="session-action-btn" onclick="var e = arguments[0] || window.event; if(e) e.stopPropagation(); renameSession('${c.id}', this)" title="Rename">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button class="session-action-btn delete" onclick="var e = arguments[0] || window.event; if(e) e.stopPropagation(); deleteConversation('${c.id}')" title="Delete">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                `;
            }
            container.appendChild(item);
        });
    } catch {}
}

async function loadConversation(convId) {
    try {
        const res = await fetch(`/api/conversations/${convId}`);
        const conv = await res.json();
        if (!conv || !conv.messages) return;

        state.conversationId = convId;
        state.messages = [];
        state.messageMap = {};
        state.activeLeafId = null;

        chatAreaEl.innerHTML = "";
        welcomeEl.classList.add("hidden");
        chatAreaEl.classList.add("active");
        
        if (typeof closeTaskMode === 'function') {
            closeTaskMode();
        }

        // ── Build the message tree from flat DB rows ────────────
        // Each message has a parent_id and active_child_index.
        // We build a map of id → node, then wire up children arrays.
        
        // Virtual root to hold all parent_id = null roots
        const savedRootIdx = parseInt(localStorage.getItem(`conv_${convId}_root_idx`) || '0');
        state.messageMap['root'] = {
            id: 'root',
            parent_id: null,
            active_child_index: savedRootIdx,
            children: []
        };

        conv.messages.forEach(m => {
            state.messageMap[m.id] = {
                id: m.id,
                parent_id: m.parent_id,          // null for root
                active_child_index: m.active_child_index || 0,
                role: m.role,
                content: m.content,
                children: [],                    // filled in next loop
                _sources: m.sources || [],
            };
        });

        // Wire children arrays (ordered by creation = DB order)
        conv.messages.forEach(m => {
            if (m.parent_id && state.messageMap[m.parent_id]) {
                state.messageMap[m.parent_id].children.push(m.id);
            } else if (!m.parent_id) {
                state.messageMap['root'].children.push(m.id);
            }
        });

        // ── Find the active root child ──────────────
        // Normalize active index in case branches were deleted from localStorage mismatch
        const rootChildrenCount = state.messageMap['root'].children.length;
        if (rootChildrenCount > 0) {
            if (state.messageMap['root'].active_child_index >= rootChildrenCount) {
                state.messageMap['root'].active_child_index = rootChildrenCount - 1;
            }
        }

        const rootChildren = state.messageMap['root'].children;
        const legacyRoot = conv.messages[0];

        if (rootChildren.length === 0 && legacyRoot && legacyRoot.parent_id === null) {
            // Legacy fallback if something broke
            let prev = null;
            conv.messages.forEach(m => {
                const node = state.messageMap[m.id];
                if (prev) {
                    node.parent_id = prev;
                    state.messageMap[prev].children = [m.id];
                } else {
                    state.messageMap['root'].children = [m.id];
                }
                prev = m.id;
            });
        }
        
        if (state.messageMap['root'].children.length > 0) {
            // ── Walk root → leaf following active_child_index ──
            const activeRootId = state.messageMap['root'].children[state.messageMap['root'].active_child_index];
            let curr = state.messageMap[activeRootId];
            while (curr && curr.children && curr.children.length > 0) {
                const idx = Math.min(curr.active_child_index || 0, curr.children.length - 1);
                curr = state.messageMap[curr.children[idx]];
            }
            state.activeLeafId = curr ? curr.id : null;
        }

        renderActiveThread();
        loadConversations();
    } catch(e) {
        console.error('loadConversation error:', e);
    }
}

async function deleteConversation(convId) {
    const ok = await showConfirm('Delete this conversation? This cannot be undone.');
    if (!ok) return;
    await fetch(`/api/conversations/${convId}`, { method: "DELETE" });
    if (state.conversationId === convId) clearChat();
    await loadConversations();
}

async function factoryReset() {
    const ok = await showConfirm('Are you sure you want to completely erase the application? All settings, chat history, personas, and configurations will be permanently deleted. The app will restart and prompt for initial setup.');
    if (!ok) return;

    try {
        const res = await fetch("/api/factory_reset", { method: "POST" });
        if (res.ok) {
            localStorage.clear();
            sessionStorage.clear();
            window.location.reload(true);
        } else {
            console.error("Factory reset failed.");
            alert("Factory reset failed. See console.");
        }
    } catch(err) {
        console.error("Factory reset error:", err);
        alert("An error occurred during factory reset.");
    }
}

// ── Custom in-page confirm (replaces blocked native confirm()) ─────
function showConfirm(message) {
    return new Promise(resolve => {
        // Remove any existing
        const existing = document.getElementById('custom-confirm');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'custom-confirm';
        overlay.style.cssText = `
            position:fixed;inset:0;z-index:9999;
            display:flex;align-items:center;justify-content:center;
            background:rgba(0,0,0,0.5);backdrop-filter:blur(4px);
            animation:fadeIn 0.15s ease;
        `;
        overlay.innerHTML = `
            <div style="
                background:var(--bg-secondary);border:1px solid var(--border);
                border-radius:12px;padding:24px 28px;max-width:320px;width:90%;
                box-shadow:0 20px 60px rgba(0,0,0,0.4);
                animation:fadeIn 0.15s ease;
            ">
                <p style="margin:0 0 18px;font-size:14px;color:var(--text-primary);line-height:1.5">${escapeHtml(message)}</p>
                <div style="display:flex;gap:8px;justify-content:flex-end">
                    <button id="confirm-cancel" class="btn btn-outline" style="padding:6px 16px;font-size:13px">Cancel</button>
                    <button id="confirm-ok" style="
                        padding:6px 16px;font-size:13px;border:none;border-radius:6px;
                        background:var(--error);color:#fff;cursor:pointer;font-family:var(--font-main);
                    ">Delete</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        overlay.querySelector('#confirm-ok').onclick = () => { overlay.remove(); resolve(true); };
        overlay.querySelector('#confirm-cancel').onclick = () => { overlay.remove(); resolve(false); };
        overlay.addEventListener('click', e => { if (e.target === overlay) { overlay.remove(); resolve(false); } });
    });
}

// ── Private / Locked Chat ─────────────────────────────────────────

// SHA-256 helper (Web Crypto API)
async function sha256(str) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function showNewChatPicker() {
    $("#new-chat-picker").classList.add("active");
}

function startRegularChat() {
    $("#new-chat-picker").classList.remove("active");
    clearChat();
}

function openPrivateChatSetup() {
    $("#new-chat-picker").classList.remove("active");
    $("#private-pwd-input").value = "";
    $("#private-pwd-confirm").value = "";
    $("#private-pwd-error").textContent = "";
    $("#private-chat-setup").classList.add("active");
    setTimeout(() => $("#private-pwd-input").focus(), 100);
}

async function createPrivateChat() {
    const pwd = $("#private-pwd-input").value;
    const confirm = $("#private-pwd-confirm").value;
    const errEl = $("#private-pwd-error");

    if (!pwd || pwd.length < 4) { errEl.textContent = "Password must be at least 4 characters"; return; }
    if (pwd !== confirm) { errEl.textContent = "Passwords don't match"; return; }
    errEl.textContent = "";

    const convId = "locked_" + Date.now().toString(36);
    const pwdHash = await sha256(pwd);

    // Create the locked conversation
    try {
        const res = await fetch("/api/conversations/create-locked", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                conv_id: convId,
                password_hash: pwdHash,
                user_id: state.userId,
            }),
        });
        const data = await res.json();
        if (data.status === "ok") {
            $("#private-chat-setup").classList.remove("active");
            // Start chatting — locked chats are in-session only; navigate into it
            state.conversationId = convId;
            state.isLockedSession = true;
            clearChat();
            await loadConversations();
        } else {
            errEl.textContent = data.error || "Failed to create private chat";
        }
    } catch (e) {
        errEl.textContent = "Error: " + e.message;
    }
}

// State for which locked conv we're trying to open
let _pendingUnlockId = null;

function openUnlockModal(convId) {
    _pendingUnlockId = convId;
    $("#unlock-pwd-input").value = "";
    $("#unlock-error").textContent = "";
    $("#chat-unlock-modal").classList.add("active");
    setTimeout(() => $("#unlock-pwd-input").focus(), 100);
}

async function submitUnlock() {
    const pwd = $("#unlock-pwd-input").value;
    const errEl = $("#unlock-error");
    if (!pwd) { errEl.textContent = "Enter your password"; return; }

    const pwdHash = await sha256(pwd);
    try {
        const res = await fetch(`/api/conversations/${_pendingUnlockId}/verify-lock`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: pwd }),
        });
        const data = await res.json();
        if (data.verified) {
            $("#chat-unlock-modal").classList.remove("active");
            await loadConversation(_pendingUnlockId);
            _pendingUnlockId = null;
        } else {
            errEl.textContent = "Incorrect password";
            $("#unlock-pwd-input").value = "";
            $("#unlock-pwd-input").focus();
        }
    } catch (e) {
        errEl.textContent = "Error: " + e.message;
    }
}

async function unlockWithTouchID() {
    const errEl = $("#unlock-error");
    try {
        const result = await nativeCall("touch_id", { reason: "Open Locked Chat" });
        if (result && result.success) {
            $("#chat-unlock-modal").classList.remove("active");
            await loadConversation(_pendingUnlockId);
            _pendingUnlockId = null;
        } else {
            errEl.textContent = result?.error || "Touch ID failed or unavailable";
        }
    } catch (e) {
        errEl.textContent = "Touch ID unavailable on this device";
    }
}

async function renameSession(convId, btnEl) {
    const sessionItem = btnEl.closest(".session-item");
    const titleEl = sessionItem.querySelector(".session-title");
    // Strip any badge spans — get only the visible text of the session title
    const currentTitle = titleEl.firstChild ? titleEl.firstChild.textContent.trim() : titleEl.textContent.trim();

    // Wrap input and a confirm button
    const wrapper = document.createElement("div");
    wrapper.style.display = "flex";
    wrapper.style.alignItems = "center";
    wrapper.style.gap = "4px";
    wrapper.style.flex = "1";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "session-rename-input";
    input.value = currentTitle;
    input.style.flex = "1";
    input.style.width = "100%";
    input.style.minWidth = "50px";

    const checkBtn = document.createElement("button");
    checkBtn.className = "session-action-btn";
    checkBtn.style.color = "var(--success, #4caf50)";
    checkBtn.style.display = "flex";
    checkBtn.style.alignItems = "center";
    checkBtn.style.background = "none";
    checkBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;

    wrapper.appendChild(input);
    wrapper.appendChild(checkBtn);

    titleEl.replaceWith(wrapper);
    input.focus();
    input.select();

    const save = async () => {
        const newTitle = input.value.trim();
        if (newTitle && newTitle !== currentTitle) {
            await fetch(`/api/conversations/${convId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: newTitle }),
            });
        }
        loadConversations();
    };

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); save(); }
        if (e.key === "Escape") { input.value = currentTitle; save(); }
    });
    
    // Use mousedown instead of click to prevent the input from losing focus beforehand
    checkBtn.addEventListener("mousedown", (e) => {
        e.preventDefault(); 
        e.stopPropagation();
        save();
    });
}

async function exportConversation(format) {
    if (!state.conversationId) return;
    if (format === "md") {
        const res = await fetch(`/api/conversations/${state.conversationId}/export?format=md`);
        const data = await res.json();
        if (data.markdown) {
            const blob = new Blob([data.markdown], { type: "text/markdown" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `chat_${state.conversationId}.md`;
            a.click();
            URL.revokeObjectURL(url);
        }
    } else if (format === "pdf") {
        window.open(`/api/conversations/${state.conversationId}/export?format=pdf`, "_blank");
    }
}

// ── Image Upload (Vision) ─────────

async function attachImage() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";

    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/upload/image", { method: "POST", body: formData });
            const data = await res.json();
            if (data.status === "ok") {
                state.pendingImages = [data.base64];
                showImagePreview(data.base64, data.filename);
            }
        } catch (err) {
            console.error("Image upload failed:", err);
        }
    };
    input.click();
}

function showImagePreview(b64, filename) {
    let preview = $("#image-preview");
    if (!preview) {
        preview = document.createElement("div");
        preview.id = "image-preview";
        preview.style.cssText = "padding:4px 16px;display:flex;align-items:center;gap:8px";
        $(".input-box").prepend(preview);
    }
    preview.innerHTML = `
        <img src="data:image/jpeg;base64,${b64}" style="height:40px;border-radius:6px;border:1px solid var(--border)">
        <span style="font-size:12px;color:var(--text-muted)">${filename}</span>
        <button onclick="clearImagePreview()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:14px">x</button>
    `;
}

function clearImagePreview() {
    state.pendingImages = [];
    const preview = $("#image-preview");
    if (preview) preview.remove();
}

// ── Voice Input ───────────────────

async function toggleVoice() {
    if (state.isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];

        // macOS WKWebView only supports audio/mp4 — detect what's supported
        const mimeType = MediaRecorder.isTypeSupported('audio/mp4')
            ? 'audio/mp4'
            : MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : MediaRecorder.isTypeSupported('audio/webm')
                    ? 'audio/webm'
                    : ''; // let browser pick default

        const recorderOpts = mimeType ? { mimeType } : {};
        const recorder = new MediaRecorder(stream, recorderOpts);

        recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
        recorder.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            const ext = mimeType.includes('mp4') ? 'mp4' : 'webm';
            const blob = new Blob(chunks, { type: mimeType || 'audio/mp4' });

            const voiceBtn = $('#voice-btn');
            if (voiceBtn) voiceBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <circle cx="12" cy="12" r="2"/><circle cx="4" cy="12" r="2"/><circle cx="20" cy="12" r="2"/>
                </svg>`;

            const formData = new FormData();
            formData.append('file', blob, `recording.${ext}`);

            try {
                const res = await fetch('/api/voice/transcribe', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.status === 'ok' && data.text) {
                    textareaEl.value = data.text;
                    textareaEl.dispatchEvent(new Event('input'));
                    textareaEl.focus();
                } else {
                    const msg = data.message || 'Transcription failed';
                    textareaEl.placeholder = `⚠ ${msg}`;
                    setTimeout(() => { textareaEl.placeholder = 'Ask whatever you want...'; }, 5000);
                }
            } catch (err) {
                console.error('Transcription failed:', err);
                textareaEl.placeholder = '⚠ Could not reach transcription server';
                setTimeout(() => { textareaEl.placeholder = 'Ask whatever you want...'; }, 4000);
            }

            if (voiceBtn) {
                voiceBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/></svg>';
            }
        };

        recorder.start(500); // Collect in 500ms chunks for reliability
        state.mediaRecorder = recorder;
        state.isRecording = true;

        const voiceBtn = $('#voice-btn');
        if (voiceBtn) {
            voiceBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--error)" stroke-width="2"><rect x="6" y="4" width="12" height="16" rx="2"/></svg>';
            voiceBtn.title = 'Recording… click to stop';
        }
    } catch (err) {
        console.error('Microphone access denied:', err);
        // Show error in textarea placeholder
        if (textareaEl) {
            textareaEl.placeholder = '⚠ Microphone access denied. Check System Settings → Privacy → Microphone.';
            setTimeout(() => { textareaEl.placeholder = 'Ask whatever you want...'; }, 5000);
        }
    }
}

function stopRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.isRecording = false;
        const voiceBtn = $('#voice-btn');
        if (voiceBtn) voiceBtn.title = 'Voice input';
    }
}

// ── Templates ─────────────────────

async function openTemplatesPanel() {
    $("#templates-panel").classList.add("active");
    await loadTemplateList();
}

async function loadTemplateList() {
    try {
        const res = await fetch("/api/templates");
        const data = await res.json();
        const list = $("#template-list");
        const select = $("#template-select");
        if (!list || !select) return;

        list.innerHTML = "";
        // Keep first option
        select.innerHTML = '<option value="">Select a template...</option>';

        (data.templates || []).forEach((t) => {
            const item = document.createElement("div");
            item.className = "file-item";
            item.innerHTML = `
                <span class="file-name">${escapeHtml(t.name)} <span style="color:var(--text-muted);font-size:11px">(${t.fields} fields)</span></span>
                <button onclick="deleteTemplate('${t.id}')" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:12px">delete</button>
            `;
            list.appendChild(item);

            const opt = document.createElement("option");
            opt.value = t.id;
            opt.textContent = t.name;
            select.appendChild(opt);
        });
    } catch {}
}

async function uploadTemplate() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".docx,.pdf,.txt,.md";

    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;

        const statusEl = $("#template-status");
        statusEl.textContent = `Analyzing ${file.name}...`;

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/templates/upload", { method: "POST", body: formData });
            const data = await res.json();

            if (data.status === "ok") {
                statusEl.textContent = `Template saved! Detected ${data.fields} fillable fields.`;
                await loadTemplateList();
            } else {
                statusEl.textContent = `Error: ${data.error}`;
            }
        } catch (err) {
            statusEl.textContent = `Upload failed: ${err.message}`;
        }
    };
    input.click();
}

async function deleteTemplate(templateId) {
    await fetch(`/api/templates/${templateId}`, { method: "DELETE" });
    await loadTemplateList();
}

async function fillTemplate(format) {
    const templateId = $("#template-select").value;
    const instructions = $("#fill-instructions").value.trim();
    const statusEl = $("#fill-status");

    if (!templateId) {
        statusEl.textContent = "Please select a template first.";
        return;
    }
    if (!instructions) {
        statusEl.textContent = "Please enter the information to fill in.";
        return;
    }

    statusEl.textContent = "AI is filling the template... (this may take a moment)";

    try {
        const res = await fetch(`/api/templates/${templateId}/fill`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                instructions: instructions,
                model: state.model,
                output_format: format === "pdf" ? ".pdf" : ".docx",
            }),
        });
        const data = await res.json();

        if (data.status === "ok" && data.url) {
            statusEl.innerHTML = `Done! <a href="${data.url}" download="${data.filename}" style="color:var(--accent);text-decoration:underline">Download ${data.filename}</a>`;
        } else {
            statusEl.textContent = `Error: ${data.message || "Generation failed"}`;
        }
    } catch (err) {
        statusEl.textContent = `Error: ${err.message}`;
    }
}

// ── Smart Fill ────────────────────

function switchTemplateTab(tab) {
    const isAi = tab === 'ai';
    $('#tmpl-panel-ai').style.display  = isAi ? '' : 'none';
    $('#tmpl-panel-smart').style.display = isAi ? 'none' : '';
    $('#tmpl-tab-ai').style.background    = isAi ? 'var(--accent)' : 'transparent';
    $('#tmpl-tab-ai').style.color         = isAi ? '#fff' : 'var(--text-secondary)';
    $('#tmpl-tab-smart').style.background = isAi ? 'transparent' : 'var(--accent)';
    $('#tmpl-tab-smart').style.color      = isAi ? 'var(--text-secondary)' : '#fff';
}

const _sfFiles = { template: null, content: null };

function sfFileChosen(which, input) {
    const file = input.files[0];
    if (!file) return;
    _sfFiles[which] = file;
    const labelId = which === 'template' ? 'sf-template-label' : 'sf-content-label';
    const zoneId  = which === 'template' ? 'sf-template-zone'  : 'sf-content-zone';
    const label = $(`#${labelId}`);
    const zone  = $(`#${zoneId}`);
    if (label) label.textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
    if (zone)  zone.style.borderColor = 'var(--accent)';
}

async function smartFillForm() {
    const statusEl  = $('#sf-status');
    const resultEl  = $('#sf-result');
    const generateBtn = $('#sf-generate-btn');
    const format    = $('#sf-format').value;

    if (!_sfFiles.template) { statusEl.textContent = '⚠ Please choose a template file (①).'; return; }
    if (!_sfFiles.content)  { statusEl.textContent = '⚠ Please choose a content source file (②).'; return; }

    // Build FormData
    const fd = new FormData();
    fd.append('template_file', _sfFiles.template, _sfFiles.template.name);
    fd.append('content_file',  _sfFiles.content,  _sfFiles.content.name);
    fd.append('model',         state.model || '');
    fd.append('output_format', format);

    // Show loading state
    generateBtn.disabled = true;
    generateBtn.textContent = 'Generating…';
    statusEl.innerHTML = `<span style="color:var(--text-muted)">⏳ Extracting document structure…</span>`;
    resultEl.style.display = 'none';

    // Animate status messages while waiting
    const statusMsgs = [
        '⏳ Extracting document structure…',
        '🧠 Assembling LLM prompt…',
        '✍ AI is filling the template…',
        '📄 Rendering final document…',
    ];
    let msgIdx = 0;
    const statusInterval = setInterval(() => {
        msgIdx = Math.min(msgIdx + 1, statusMsgs.length - 1);
        statusEl.innerHTML = `<span style="color:var(--text-muted)">${statusMsgs[msgIdx]}</span>`;
    }, 4000);

    try {
        // Step 1: Upload template → get template_id + field schema
        statusEl.innerHTML = `<span style="color:var(--text-muted)">⏳ Scanning template structure…</span>`;
        const uploadFd = new FormData();
        uploadFd.append('file', _sfFiles.template, _sfFiles.template.name);
        const uploadRes = await fetch('/api/templates/upload', { method: 'POST', body: uploadFd });
        const uploadData = await uploadRes.json();

        if (!uploadData.template_id) {
            clearInterval(statusInterval);
            statusEl.textContent = `❌ Template upload failed: ${uploadData.error || 'Unknown error'}`;
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Generate';
            return;
        }

        const templateId = uploadData.template_id;
        const fieldCount = uploadData.fields || 0;
        statusEl.innerHTML = `<span style="color:var(--text-muted)">🧠 Found ${fieldCount} field${fieldCount !== 1 ? 's' : ''}… asking AI to extract values…</span>`;

        // Step 2: Send content file to fill endpoint (Mode A — multipart)
        const fillFd = new FormData();
        fillFd.append('content_file', _sfFiles.content, _sfFiles.content.name);
        fillFd.append('model', state.model || '');

        const res = await fetch(`/api/templates/${templateId}/fill`, { method: 'POST', body: fillFd });
        clearInterval(statusInterval);
        const data = await res.json();

        if (data.status === 'ok' && data.url) {
            statusEl.innerHTML = `<span style="color:var(--accent)">✅ Document generated successfully!</span>`;
            const dlLink = $('#sf-download-link');
            dlLink.href = data.url;
            dlLink.download = data.filename;
            dlLink.textContent = `Download ${data.filename}`;
            resultEl.style.display = 'block';
            resultEl._sfUrl = data.url;
            resultEl._sfFilename = data.filename;
            resultEl._sfType = data.type;
        } else {
            statusEl.textContent = `❌ Error: ${data.error || data.message || 'Generation failed'}`;
        }
    } catch (err) {
        clearInterval(statusInterval);
        statusEl.textContent = `❌ Request failed: ${err.message}`;
    } finally {
        generateBtn.disabled = false;
        generateBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Generate';
    }
}

function sfPreview() {
    const resultEl = $('#sf-result');
    if (!resultEl || !resultEl._sfUrl) return;
    openArtifactViewer('', resultEl._sfFilename, resultEl._sfUrl, (resultEl._sfType || 'docx').toUpperCase());
}

// ── Personas (stub — persona dropdown removed) ──────────────────
async function loadPersonas() { /* dropdown removed; global prompt managed via Settings */ }

// ── Search ────────────────────────

let searchTimeout = null;
async function searchConversations(query) {
    clearTimeout(searchTimeout);
    if (!query || query.length < 2) {
        loadConversations();
        return;
    }
    searchTimeout = setTimeout(async () => {
        try {
            const res = await fetch(`/api/conversations/search/${encodeURIComponent(query)}?user_id=${encodeURIComponent(state.userId)}`);
            const data = await res.json();
            const container = $("#sidebar-sessions");
            if (!container) return;

            container.innerHTML = "";
            if (!data.results || data.results.length === 0) {
                container.innerHTML = '<div style="padding:12px 6px;font-size:12px;color:var(--text-muted)">No results found</div>';
                return;
            }

            const label = document.createElement("div");
            label.className = "sidebar-label";
            label.textContent = `${data.results.length} results`;
            container.appendChild(label);

            const seen = new Set();
            data.results.forEach((r) => {
                if (seen.has(r.conversation_id)) return;
                seen.add(r.conversation_id);
                const item = document.createElement("div");
                item.className = "session-item";
                item.innerHTML = `
                    <span class="session-title" onclick="loadConversation('${r.conversation_id}')">
                        ${escapeHtml(r.conversation_title || 'Chat')}
                        <span style="display:block;font-size:11px;color:var(--text-muted);margin-top:2px">${escapeHtml(r.content)}</span>
                    </span>
                `;
                container.appendChild(item);
            });
        } catch {}
    }, 300);
}

// ── Folders / Tags ────────────────

async function loadFolders() {
    try {
        const res = await fetch(`/api/folders?user_id=${encodeURIComponent(state.userId)}`);
        const data = await res.json();
        const select = $("#folder-filter");
        if (!select) return;

        // Keep "All folders" option
        select.innerHTML = '<option value="">All folders</option>';
        (data.folders || []).forEach((f) => {
            const opt = document.createElement("option");
            opt.value = f;
            opt.textContent = f;
            select.appendChild(opt);
        });
    } catch {}
}

function filterByFolder(folder) {
    loadConversations(folder);
}
function customPromptUI(title, text, defaultValue = "") {
    return new Promise((resolve) => {
        const modal = document.getElementById("custom-prompt-modal");
        const titleEl = document.getElementById("custom-prompt-title");
        const textEl = document.getElementById("custom-prompt-text");
        const inputEl = document.getElementById("custom-prompt-input");
        const btnOk = document.getElementById("custom-prompt-ok");
        const btnCancel = document.getElementById("custom-prompt-cancel");

        titleEl.textContent = title;
        textEl.textContent = text;
        inputEl.value = defaultValue;
        modal.style.display = "flex";
        
        setTimeout(() => inputEl.focus(), 50);

        const cleanup = () => {
            modal.style.display = "none";
            btnOk.onclick = null;
            btnCancel.onclick = null;
            inputEl.onkeydown = null;
        };

        btnOk.onclick = () => { resolve(inputEl.value); cleanup(); };
        btnCancel.onclick = () => { resolve(null); cleanup(); };
        inputEl.onkeydown = (e) => {
            if (e.key === "Enter") btnOk.click();
            if (e.key === "Escape") btnCancel.click();
        };
    });
}

async function setFolder(convId) {
    const folder = await customPromptUI("Set Folder", "Enter folder name (or leave empty to remove):");
    if (folder === null) return;
    try {
        await fetch(`/api/conversations/${convId}/meta`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: folder }),
        });
        loadConversations();
        loadFolders();
    } catch {}
}

async function setTags(convId) {
    const tags = await customPromptUI("Set Tags", "Enter tags separated by commas:");
    if (tags === null) return;
    try {
        await fetch(`/api/conversations/${convId}/meta`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tags: tags }),
        });
        loadConversations();
    } catch {}
}

// ── Text-to-Speech ────────────────

function toggleTTS() {
    state.ttsEnabled = !state.ttsEnabled;
    const btn = $("#tts-btn");
    if (btn) {
        btn.style.background = state.ttsEnabled ? "var(--bg-tertiary)" : "transparent";
        btn.title = state.ttsEnabled ? "TTS On (click to turn off)" : "Read aloud";
    }
    if (!state.ttsEnabled) {
        window.speechSynthesis.cancel();
    }
}

function speakText(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();

    // Clean markdown/code for speech
    let clean = text
        .replace(/```[\s\S]*?```/g, ' (code block) ')
        .replace(/`[^`]+`/g, '')
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\*(.+?)\*/g, '$1')
        .replace(/^#+\s*/gm, '')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/[|_\-]{3,}/g, '')
        .trim();

    if (!clean) return;

    // Detect Language to ensure correct pronunciation
    let lang = 'en-US'; // Default
    if (/[\u4E00-\u9FFF]/.test(clean)) {
        lang = 'zh-CN'; // Chinese
    } else if (/[\u0400-\u04FF]/.test(clean)) {
        lang = 'ru-RU'; // Russian
    } else if (/[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]/i.test(clean)) {
        lang = 'vi-VN'; // Vietnamese
    }

    // Split into chunks (speechSynthesis has a ~200 char limit in some browsers)
    const chunks = clean.match(/[^.!?\n]{1,200}[.!?\n]?/g) || [clean];

    // Read aloud based on the detected language
    chunks.forEach((chunk, i) => {
        const utterance = new SpeechSynthesisUtterance(chunk.trim());
        utterance.lang = lang;
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        window.speechSynthesis.speak(utterance);
    });
}

function speakMessageById(msgId) {
    const node = state.messageMap[msgId];
    if (node) {
        speakText(node.content);
    } else {
        // Fallback: read from DOM
        const el = document.getElementById(`msg-content-${msgId}`);
        if (el) speakText(el.innerText || el.textContent || '');
    }
}

// ── Model Management ──────────────

// (openSettingsPanel is defined above — single authoritative definition)

function toggleDlFormat() {
    const fmt = document.querySelector('input[name="dl-format"]:checked')?.value || 'gguf';
    const fileInput = $('#hf-file');
    const repoInput = $('#hf-repo');
    if (fmt === 'safetensors') {
        fileInput.style.display = 'none';
        repoInput.placeholder = 'e.g. TinyLlama/TinyLlama-1.1B-Chat-v1.0';
    } else {
        fileInput.style.display = '';
        repoInput.placeholder = 'e.g. bartowski/Llama-3.2-3B-Instruct-GGUF';
    }
}

async function refreshModelManager() {
    // Update loaded model display
    try {
        const hRes = await fetch('/api/health');
        const hData = await hRes.json();
        const loadedEl = $('#loaded-model-name');
        if (loadedEl) loadedEl.textContent = hData.loaded_model || 'None';
    } catch {}

    // Update directories list
    loadModelDirs();

    // Update model list
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        const list = $('#model-manager-list');
        if (!list) return;
        list.innerHTML = '';

        const models = data.models || [];
        if (models.length === 0) {
            list.innerHTML = '<div style="font-size:13px;color:var(--text-muted);padding:8px 0">No models installed. Download a GGUF or SafeTensors model below.</div>';
            return;
        }

        models.forEach(m => {
            const item = document.createElement('div');
            item.className = 'file-item';
            const sizeStr = m.size_gb ? `${m.size_gb} GB` : `${(m.size / 1e6).toFixed(0)} MB`;
            const loadedBadge = m.loaded ? '<span style="color:var(--success);font-size:11px;margin-left:6px">● loaded</span>' : '';
            const fmtColor = m.format === 'gguf' ? 'var(--success)' : 'var(--accent)';
            const fmtLabel = m.format === 'gguf' ? 'GGUF' : 'HF';
            const fmtBadge = `<span style="color:${fmtColor};font-size:10px;background:var(--bg-primary);padding:1px 5px;border-radius:3px;margin-left:4px;border:1px solid ${fmtColor}40">${fmtLabel}</span>`;
            const quantBadge = m.quantization ? `<span style="color:var(--text-muted);font-size:11px;margin-left:4px">${m.quantization}</span>` : '';
            const unavailable = m.available === false ? '<span style="color:var(--warning);font-size:10px;margin-left:4px" title="Install torch+transformers to use">⚠ needs torch</span>' : '';
            item.innerHTML = `
                <div style="flex:1;min-width:0">
                    <span class="file-name">${escapeHtml(m.name)}</span>${fmtBadge}${loadedBadge}${quantBadge}${unavailable}
                    <span class="file-chunks">${sizeStr}</span>
                </div>
                <div style="display:flex;gap:4px;flex-shrink:0">
                    ${m.loaded ? '' : `<button onclick="loadSpecificModel('${escapeHtml(m.name)}', this)" style="background:none;border:1px solid var(--border);color:var(--text-secondary);cursor:pointer;font-size:11px;padding:2px 8px;border-radius:4px;font-family:var(--font-main)">Load</button>`}
                    <button onclick="deleteSpecificModel('${escapeHtml(m.name)}')" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:11px;padding:2px 6px">✕</button>
                </div>
            `;
            list.appendChild(item);
        });
    } catch {}
}

async function downloadHFModel() {
    const repo = $('#hf-repo').value.trim();
    const file = $('#hf-file').value.trim();
    const statusEl = $('#hf-download-status');
    const btn = $('#hf-download-btn');
    const fmtEl = document.querySelector('input[name="dl-format"]:checked');
    const fmt = fmtEl ? fmtEl.value : 'gguf';

    if (!repo) { statusEl.textContent = 'Enter a HuggingFace repo ID'; return; }
    if (fmt === 'gguf' && !file) { statusEl.textContent = 'Enter filename for GGUF download'; return; }
    if (fmt === 'gguf' && !file.endsWith('.gguf')) { statusEl.textContent = 'Filename must end in .gguf'; return; }

    btn.disabled = true;
    btn.textContent = 'Downloading…';
    const label = fmt === 'safetensors' ? `${repo} (full model)` : `${file} from ${repo}`;
    statusEl.textContent = `Downloading ${label}… This may take a while.`;
    statusEl.style.color = 'var(--text-secondary)';

    try {
        const res = await fetch('/api/models/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_id: repo, filename: file, format: fmt }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            statusEl.textContent = `✓ Downloaded ${data.name} (${data.format || fmt})`;
            statusEl.style.color = 'var(--success)';
            $('#hf-repo').value = '';
            $('#hf-file').value = '';
            await loadModels();
            await refreshModelManager();
        } else {
            statusEl.textContent = `✕ ${data.error}`;
            statusEl.style.color = 'var(--error)';
        }
    } catch (err) {
        statusEl.textContent = `Error: ${err.message}`;
        statusEl.style.color = 'var(--error)';
    }
    btn.disabled = false;
    btn.textContent = 'Download Model';
}

async function importLocalModel() {
    const path = $('#import-path').value.trim();
    if (!path) return;
    try {
        const res = await fetch('/api/models/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            $('#import-path').value = '';
            await loadModels();
            await refreshModelManager();
        } else {
            alert(data.error);
        }
    } catch (err) { alert(err.message); }
}

async function loadSpecificModel(name, btn) {
    const originalText = btn ? btn.textContent : 'Load';
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Loading...';
    }
    
    try {
        const res = await fetch('/api/models/load', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: name }),
        });
        const data = await res.json();
        
        if (data.status === 'ok' || data.status === 'already_loaded') {
            state.model = name;
            await loadModels();
            await refreshModelManager();
        } else {
            alert(`Load failed: ${data.error || 'Unknown error'}`);
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }
    } catch (err) { 
        alert(`Load failed: ${err.message}`); 
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
}

async function deleteSpecificModel(name) {
    const ok = await showConfirm(`Delete model "${name}"? This cannot be undone.`);
    if (!ok) return;
    try {
        await fetch(`/api/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
        await loadModels();
        await refreshModelManager();
    } catch {}
}

async function unloadCurrentModel() {
    try {
        await fetch('/api/models/unload', { method: 'POST' });
        await refreshModelManager();
    } catch {}
}

// ── Model Directories Management ────────

async function loadModelDirs() {
    try {
        const res = await fetch("/api/models/directories");
        const data = await res.json();
        const list = $('#model-dirs-list');
        if (!list) return;

        list.innerHTML = '';
        data.directories.forEach(d => {
            const isPrimary = d === data.primary;
            const item = document.createElement('div');
            item.className = 'file-item';
            item.innerHTML = `
                <div style="flex:1;min-width:0;display:flex;align-items:center;">
                    <span class="file-name" style="font-family:var(--font-mono);font-size:11px;color:var(--text-secondary)">${escapeHtml(d)}</span>
                    ${isPrimary ? '<span style="color:var(--text-muted);font-size:10px;margin-left:6px;flex-shrink:0">(Primary)</span>' : ''}
                </div>
                ${!isPrimary ? `<button onclick="removeModelDir('${escapeHtml(d.replace(/\\/g, '\\\\').replace(/'/g, "\\'"))}')" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:14px;padding:0 6px" title="Remove directory">✕</button>` : ''}
            `;
            list.appendChild(item);
        });
    } catch (e) {
        console.error("Failed to load model dirs", e);
    }
}

async function addModelDir() {
    const input = $("#add-model-dir-path");
    const status = $("#model-dir-status");
    const path = input.value.trim();
    if (!path) return;
    
    status.style.color = "var(--text-muted)";
    status.textContent = "Adding...";
    
    try {
        const res = await fetch("/api/models/directories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path })
        });
        const data = await res.json();
        if (data.status === "ok") {
            input.value = "";
            status.style.color = "var(--success)";
            status.textContent = "Folder added. Models should now appear.";
            loadModelDirs();
            refreshModelManager();
            loadModels(); // refresh dropdown too
            setTimeout(() => status.textContent = "", 3000);
        } else {
            status.style.color = "var(--error)";
            status.textContent = data.error || data.message || "Failed to add";
        }
    } catch {
        status.style.color = "var(--error)";
        status.textContent = "Network error";
    }
}

async function removeModelDir(path) {
    try {
        const res = await fetch("/api/models/directories", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path })
        });
        const data = await res.json();
        if (data.status === "ok") {
            loadModelDirs();
            refreshModelManager();
            loadModels(); // refresh dropdown too
        } else {
            alert(data.error || "Failed to remove directory");
        }
    } catch (e) {
        alert("Network error");
    }
}

// ── Document Digest ───────────────


async function runDocDigest() {
    $('#upload-panel').classList.remove('active');
    welcomeEl.classList.add('hidden');
    chatAreaEl.classList.add('active');
    if (state.compareMode) {
        chatAreaEl.style.display = 'block';
        $('#compare-area').style.display = 'none';
    }

    const aiMsgEl = appendMessage('ai', '');
    const contentEl = aiMsgEl.querySelector('.message-content');
    contentEl.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    contentEl.innerHTML += '<p style="color:var(--text-muted);font-size:13px;margin-top:8px">Generating document digest…</p>';

    try {
        const res = await fetch('/api/documents/digest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: state.model }),
        });

        if (!res.ok) {
            const err = await res.json();
            contentEl.innerHTML = `<p style="color:var(--error)">${err.error || 'Digest failed'}</p>`;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        contentEl.innerHTML = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const lines = decoder.decode(value, { stream: true }).split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.token) {
                        fullText += data.token;
                        contentEl.innerHTML = renderMarkdown(fullText);
                        chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
                    }
                } catch {}
            }
        }
        state.messages.push({ role: 'assistant', content: fullText });
        postRenderEnhance();
    } catch (err) {
        contentEl.innerHTML = `<p style="color:var(--error)">Error: ${err.message}</p>`;
    }
}

// ── Session System Prompt ──────────────────

function openSessionPromptModal() {
    const ta = $('#session-prompt-textarea');
    if (ta) {
        ta.value = state.sessionSystemPrompt || '';
        const cc = $('#session-prompt-charcount');
        if (cc) cc.textContent = ta.value.length + '/2000';
    }
    $('#session-prompt-modal').classList.add('active');
    setTimeout(() => { if (ta) ta.focus(); }, 80);
}

function closeSessionPromptModal() {
    $('#session-prompt-modal').classList.remove('active');
}

function saveSessionPrompt() {
    const ta = $('#session-prompt-textarea');
    state.sessionSystemPrompt = ta ? ta.value.trim() : '';
    _updateSessionPromptBar();
    closeSessionPromptModal();
}

function clearSessionPrompt() {
    state.sessionSystemPrompt = '';
    const ta = $('#session-prompt-textarea');
    if (ta) ta.value = '';
    const cc = $('#session-prompt-charcount');
    if (cc) cc.textContent = '0/2000';
    _updateSessionPromptBar();
    closeSessionPromptModal();
}

function _updateSessionPromptBar() {
    const btn = $('#session-prompt-btn');
    const dot = $('#session-prompt-dot');
    if (!btn) return;
    const isActive = !!(state.conversationId || state.messages.length > 0);
    btn.style.display = isActive ? 'flex' : 'none';
    if (dot) dot.style.display = (isActive && state.sessionSystemPrompt) ? 'block' : 'none';
    if (state.sessionSystemPrompt) {
        const short = state.sessionSystemPrompt.length > 60 ? state.sessionSystemPrompt.slice(0, 60) + '…' : state.sessionSystemPrompt;
        btn.title = 'Session prompt: ' + short;
        btn.style.borderColor = 'var(--accent)';
        btn.style.color = 'var(--accent)';
    } else {
        btn.title = 'Set system prompt for this session';
        btn.style.borderColor = 'var(--border)';
        btn.style.color = 'var(--text-muted)';
    }
}

// ── Siri Glow ──────────────────────────────────────
// Pure CSS animation on .chat-container — toggled by .streaming class
const siriGlow = {
    start() { if (chatContainerEl) chatContainerEl.classList.add('streaming'); },
    stop()  { if (chatContainerEl) chatContainerEl.classList.remove('streaming'); },
};

// ── Compare Mode ──────────────────

function toggleCompareMode() {
    state.compareMode = !state.compareMode;
    const btn = $('#compare-toggle-btn');
    const area = $('#compare-area');
    const chatArea = chatAreaEl;
    const bar = $('#compare-model-bar');

    if (state.compareMode) {
        btn.style.background = 'var(--bg-tertiary)';
        btn.style.borderColor = 'var(--accent)';
        btn.style.color = 'var(--accent)';
        area.style.display = 'flex';
        chatArea.style.display = 'none';
        bar.style.display = 'flex';
        // Populate compare model selects
        populateCompareModels();
    } else {
        btn.style.background = '';
        btn.style.borderColor = '';
        btn.style.color = '';
        area.style.display = 'none';
        chatArea.style.display = '';
        bar.style.display = 'none';
    }
}

function populateCompareModels() {
    const selA = $('#compare-model-a');
    const selB = $('#compare-model-b');
    if (!selA || !selB || state.models.length === 0) return;

    [selA, selB].forEach((sel, idx) => {
        sel.innerHTML = '';
        state.models.forEach((m, i) => {
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = m.name;
            if (i === idx && state.models[i]) opt.selected = true;
            sel.appendChild(opt);
        });
    });
    // Default B to second model if available
    if (state.models.length > 1) selB.value = state.models[1].name;
}

async function sendCompare(text) {
    if (!text || state.isStreaming) return;
    state.isStreaming = true;
    sendBtn.disabled = true;

    const modelA = $('#compare-model-a')?.value || state.model;
    const modelB = $('#compare-model-b')?.value || state.model;

    // Update headers
    $('#compare-header-0').textContent = modelA;
    $('#compare-header-1').textContent = modelB;

    // Append user messages
    [0, 1].forEach(idx => {
        const col = $(`#compare-messages-${idx}`);
        const userDiv = document.createElement('div');
        userDiv.className = 'message message-user';
        userDiv.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
        col.appendChild(userDiv);
    });

    // Create AI message placeholders
    const aiEls = [0, 1].map(idx => {
        const col = $(`#compare-messages-${idx}`);
        const div = document.createElement('div');
        div.className = 'message message-ai';
        div.innerHTML = '<div class="message-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
        col.appendChild(div);
        col.scrollTop = col.scrollHeight;
        return div.querySelector('.message-content');
    });

    const texts = ['', ''];

    state.abortController = new AbortController();

    try {
        const res = await fetch('/api/chat/compare', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: state.abortController.signal,
            body: JSON.stringify({
                message: text,
                models: [modelA, modelB],
                history: state.messages.slice(-6),
                mode: state.mode,
                session_system_prompt: state.sessionSystemPrompt || null,
            }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        // Clear typing indicators once first token arrives
        let cleared = [false, false];

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const lines = decoder.decode(value, { stream: true }).split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    const idx = data.model_idx;
                    if (typeof idx !== 'number') continue;
                    if (data.token) {
                        if (!cleared[idx]) { aiEls[idx].innerHTML = ''; cleared[idx] = true; }
                        texts[idx] += data.token;
                        aiEls[idx].innerHTML = renderMarkdown(texts[idx]);
                        $(`#compare-messages-${idx}`).scrollTop = $(`#compare-messages-${idx}`).scrollHeight;
                    }
                } catch {}
            }
        }
        postRenderEnhance();
    } catch (err) {
        aiEls.forEach(el => { el.innerHTML = `<p style="color:var(--error)">Error: ${err.message}</p>`; });
    }

    state.isStreaming = false;
    sendBtn.disabled = false;
    textareaEl.focus();
}

// ── AI Memory ─────────────────────

async function openMemoryPanel() {
    $('#memory-panel').classList.add('active');
    await loadMemory();
}

async function loadMemory() {
    try {
        const res = await fetch(`/api/memory?user_id=${encodeURIComponent(state.userId)}`);
        const data = await res.json();
        const list = $('#memory-list');
        if (!list) return;
        list.innerHTML = '';

        const entries = data.memory || [];
        if (entries.length === 0) {
            list.innerHTML = '<div style="font-size:13px;color:var(--text-muted);padding:8px 0">No memories saved yet.</div>';
            return;
        }

        entries.forEach(m => {
            const item = document.createElement('div');
            item.className = 'file-item';
            item.innerHTML = `
                <div style="flex:1;min-width:0">
                    <span class="file-name">${escapeHtml(m.key)}</span>
                    <span style="color:var(--text-secondary);font-size:12px;display:block;margin-top:2px">${escapeHtml(m.value)}</span>
                </div>
                <button onclick="deleteMemoryKey('${escapeHtml(m.key)}')" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:12px;padding:2px 6px;flex-shrink:0">delete</button>
            `;
            list.appendChild(item);
        });
    } catch {}
}

async function addMemory() {
    const key = $('#memory-key').value.trim();
    const value = $('#memory-value').value.trim();
    if (!key || !value) return;

    try {
        await fetch('/api/memory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, value, user_id: state.userId }),
        });
        $('#memory-key').value = '';
        $('#memory-value').value = '';
        await loadMemory();
    } catch {}
}

async function deleteMemoryKey(key) {
    try {
        await fetch(`/api/memory/${encodeURIComponent(key)}?user_id=${encodeURIComponent(state.userId)}`, { method: 'DELETE' });
        await loadMemory();
    } catch {}
}

// ── Follow-up Question Suggestions ──

function generateFollowUps(aiText, msgEl) {
    if (!aiText || aiText.length < 80) return;

    const suggestions = extractFollowUps(aiText);
    if (suggestions.length === 0) return;

    const bar = document.createElement("div");
    bar.className = "followup-bar";

    suggestions.forEach(q => {
        const chip = document.createElement("button");
        chip.className = "followup-chip";
        chip.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${escapeHtml(q)}`;
        chip.title = q;
        chip.onclick = () => {
            textareaEl.value = q;
            textareaEl.dispatchEvent(new Event("input"));
            sendMessage();
        };
        bar.appendChild(chip);
    });

    // Always add a document-generation chip at the end
    const docChip = document.createElement("button");
    docChip.className = "followup-chip followup-chip-doc";
    docChip.title = "Generate a Word / PDF document from this answer";
    docChip.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> Save as Word / PDF`;
    docChip.onclick = () => {
        const prompt = `Based on the answer above, create a well-formatted Word document (.docx) that includes all the key information with proper headings, sections, and formatting. Make it ready to download.`;
        textareaEl.value = prompt;
        textareaEl.dispatchEvent(new Event("input"));
        textareaEl.focus();
    };
    bar.appendChild(docChip);

    // Insert before the export toolbar if it exists, otherwise append
    const toolbar = msgEl.querySelector(".message-export-toolbar");
    if (toolbar) {
        msgEl.insertBefore(bar, toolbar);
    } else {
        msgEl.appendChild(bar);
    }
    chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
}

function extractFollowUps(text) {
    const suggestions = [];
    const lines = text.split("\n").map(l => l.trim()).filter(l => l);

    // 1. Extract key topics from headings
    const headings = lines
        .filter(l => /^#{1,3}\s/.test(l))
        .map(l => l.replace(/^#+\s*/, '').trim())
        .filter(h => h.length > 3 && h.length < 80);

    // 2. Extract bold terms as potential dive-in topics
    const boldTerms = [];
    const boldMatches = text.matchAll(/\*\*([^*]+)\*\*/g);
    for (const m of boldMatches) {
        const term = m[1].trim();
        if (term.length > 3 && term.length < 50 && !term.includes("\n")) {
            boldTerms.push(term);
        }
    }

    // 3. Extract numbered/bulleted items as potential topics
    const listItems = lines
        .filter(l => /^[\d]+\.\s|^[-*]\s/.test(l))
        .map(l => l.replace(/^[\d]+\.\s|^[-*]\s/, '').trim())
        .filter(l => l.length > 5 && l.length < 80);

    // 4. Detect if response contains comparisons, lists, how-tos
    const hasComparison = /\bvs\.?\b|compared to|difference between|advantages|disadvantages/i.test(text);
    const hasSteps = /step \d|first,|second,|then,|finally,|how to|instructions/i.test(text);
    const hasExamples = /for example|such as|e\.g\.|for instance|example:/i.test(text);
    const hasTechnical = /implement|function|code|algorithm|syntax|api|library|framework/i.test(text);

    // Build questions based on context
    if (headings.length >= 2) {
        suggestions.push(`How do ${headings[0]} and ${headings[1]} relate to each other?`);
    }

    if (boldTerms.length > 0) {
        const topic = boldTerms[Math.floor(Math.random() * Math.min(boldTerms.length, 3))];
        suggestions.push(`Can you explain "${topic}" in more detail?`);
    }

    if (hasComparison) {
        suggestions.push("What are the pros and cons of each approach?");
    } else if (hasSteps) {
        suggestions.push("Can you provide a practical example of this?");
    } else if (hasTechnical) {
        suggestions.push("Can you show a code example for this?");
    }

    if (hasExamples && suggestions.length < 3) {
        suggestions.push("Are there any alternatives or edge cases to consider?");
    }

    if (listItems.length >= 3 && suggestions.length < 3) {
        const item = listItems[Math.min(1, listItems.length - 1)];
        if (item.length < 50) {
            suggestions.push(`Tell me more about "${item}"`);
        }
    }

    // Fallback generic follow-ups based on response length
    if (suggestions.length === 0) {
        if (text.length > 500) {
            suggestions.push("Can you summarize the key takeaways?");
        }
        if (text.length > 200) {
            suggestions.push("Can you elaborate further on this topic?");
        }
    }

    // Dedupe and limit
    const unique = [...new Set(suggestions)];
    return unique.slice(0, 3);
}

// ── MCP Server Management ────────────

async function loadMcpServers() {
    try {
        const res = await fetch('/api/mcp');
        const data = await res.json();
        const list = $('#mcp-servers-list');
        list.innerHTML = '';
        
        const servers = Object.entries(data);
        if (servers.length === 0) {
            list.innerHTML = '<div style="font-size:12px;color:var(--text-muted);">No MCP servers connected.</div>';
            return;
        }
        
        servers.forEach(([name, config]) => {
            const item = document.createElement('div');
            item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; background:var(--bg-secondary); padding:6px 10px; border:1px solid var(--border); border-radius:4px;';
            
            const info = document.createElement('div');
            info.innerHTML = `
                <div style="font-size:13px; font-weight:500; color:var(--text-primary); display:flex; align-items:center; gap:6px;">
                    <div class="status-dot connected" style="margin:0;"></div>
                    ${name}
                </div>
                <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${config.command} ${config.args.join(' ')}</div>
            `;
            
            const delBtn = document.createElement('button');
            delBtn.className = 'btn btn-outline';
            delBtn.style.cssText = 'padding:2px 8px; font-size:11px; border-color:var(--error); color:var(--error);';
            delBtn.textContent = 'Remove';
            delBtn.onclick = async () => {
                await fetch(`/api/mcp/${encodeURIComponent(name)}`, { method: 'DELETE' });
                loadMcpServers();
            };
            
            item.appendChild(info);
            item.appendChild(delBtn);
            list.appendChild(item);
        });
    } catch (e) {
        console.error("Failed to load MCP servers:", e);
    }
}

async function addMcpServer(btn) {
    const nameEl = $('#mcp-name');
    const cmdEl = $('#mcp-command');
    const argsEl = $('#mcp-args');
    
    const name = nameEl.value.trim();
    const command = cmdEl.value.trim();
    const args = argsEl.value.trim().split(' ').filter(Boolean);
    
    if (!name || !command) {
        alert("Name and Command are required to add an MCP Server.");
        return;
    }
    
    const orig = btn ? btn.textContent : '';
    if (btn) { btn.textContent = "Adding..."; btn.disabled = true; }
    
    try {
        const res = await fetch('/api/mcp', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, command, args })
        });
        if (res.ok) {
            nameEl.value = '';
            cmdEl.value = '';
            argsEl.value = '';
            await loadMcpServers();
        } else {
            const err = await res.json();
            alert("Error: " + err.error);
        }
    } catch (e) {
        alert("Failed to connect to MCP server.");
    }
    
    if (btn) { btn.textContent = orig; btn.disabled = false; }
}

// ── Boot ───────────────────────────

window.changeLanguage = function(lang) {
    if(lang) {
        localStorage.setItem('openchat_lang', lang);
        applyTranslations();
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // Apply translations on load
    applyTranslations();
    const currentLang = localStorage.getItem('openchat_lang') || 'en';
    const langSelect = document.getElementById('app-language-select');
    if(langSelect) langSelect.value = currentLang;

    // Patch window.sendMessage BEFORE init() → setupListeners() runs.
    // setupListeners() calls (window.sendMessage || sendMessage)() so compare-mode works on both
    // button click and Enter key.
    const origSend = sendMessage;
    window.sendMessage = async function(overrideText = undefined, overrideParentId = undefined) {
        if (state.compareMode && overrideText === undefined && overrideParentId === undefined) {
            const text = textareaEl.value.trim();
            if (!text) return;
            textareaEl.value = '';
            textareaEl.style.height = 'auto';
            charCount.textContent = '0/1000';
            await sendCompare(text);
        } else {
            await origSend(overrideText, overrideParentId);
        }
    };

    state.compareMode = false;
    init().then(() => {
        populateCompareModels();
        setupDocViewerResizer();
        _updateSessionPromptBar();
    });
});


const _dv = {
    currentSource: null,
    currentCollection: 'documents',
    currentChunks: [],   // RAG chunks used in the last response for this source
    currentMode: 'source',
    currentFileUrl: null,
    currentFileContent: null,
};

function _dvPane()     { return document.getElementById('doc-viewer-pane'); }
function _dvIframe()   { return document.getElementById('doc-viewer-iframe'); }
function _dvTextField(){ return document.getElementById('doc-viewer-text'); }

// Open viewer with a RAG source document
async function openSourceViewer(sourceName, usedChunks = [], collection = 'documents') {
    const pane = _dvPane();
    pane.style.display = 'flex';
    _dv.currentSource = sourceName;
    _dv.currentCollection = collection;
    _dv.currentChunks = usedChunks;
    _dv.currentMode = 'source';
    _dv.currentFileUrl = null;

    // Mark tab
    switchViewerTab('source');

    // Update header
    document.getElementById('doc-viewer-name').textContent = sourceName;
    const ext = sourceName.split('.').pop().toUpperCase();
    const badge = document.getElementById('doc-viewer-badge');
    badge.textContent = ext;
    badge.style.display = '';
    document.getElementById('doc-viewer-download-btn').style.display = 'none';

    // Highlight active source tag
    document.querySelectorAll('.source-tag.source-doc').forEach(t => t.classList.remove('active'));
    document.querySelectorAll(`.source-tag.source-doc[data-source="${CSS.escape(sourceName)}"]`).forEach(t => t.classList.add('active'));

    // Show loading
    const loading = document.getElementById('doc-viewer-loading');
    const empty = document.getElementById('doc-viewer-empty');
    const wrap = document.getElementById('doc-viewer-text-wrap');
    loading.style.display = 'flex';
    empty.style.display = 'none';
    wrap.style.display = 'none';

    try {
        const params = new URLSearchParams({ source: sourceName, collection });
        const res = await fetch(`/api/documents/preview?${params}`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        // Resolve chunk indexes -> actual chunk text objects for highlighting
        const resolvedChunks = usedChunks
            .map(idx => data.chunks.find(c => c.index === idx))
            .filter(Boolean);

        // Render full text with highlighted passages
        renderDocumentText(data.full_text, data.chunks, resolvedChunks);

        // Update footer
        const footer = document.getElementById('doc-viewer-footer');
        const pageInfo = document.getElementById('doc-viewer-page-info');
        pageInfo.textContent = `${data.chunk_count} passage${data.chunk_count !== 1 ? 's' : ''} indexed`;
        footer.style.display = 'flex';

        // Show chunk navigation pills
        if (resolvedChunks.length > 0) {
            showChunkNav(resolvedChunks);
        } else {
            document.getElementById('doc-viewer-chunk-nav').style.display = 'none';
        }

        loading.style.display = 'none';
        wrap.style.display = 'block';
    } catch(err) {
        loading.style.display = 'none';
        empty.style.display = 'flex';
        empty.querySelector('p').textContent = `Could not load document: ${err.message}`;
    }
}

// Open viewer with a generated artifact (code block)
function openArtifactViewer(content, title = 'Preview', fileUrl = null, fileType = null) {
    const pane = _dvPane();
    pane.style.display = 'flex';
    _dv.currentMode = 'artifact';
    _dv.currentFileUrl = fileUrl;
    _dv.currentFileContent = content;

    switchViewerTab('artifact');

    document.getElementById('doc-viewer-name').textContent = title;
    const badge = document.getElementById('doc-viewer-badge');
    badge.textContent = fileType || 'HTML';
    badge.style.display = '';

    const dlBtn = document.getElementById('doc-viewer-download-btn');
    dlBtn.style.display = fileUrl ? '' : 'none';

    const iframe = _dvIframe();
    const doc = iframe.contentWindow.document;
    doc.open();
    if (content && content.trim().startsWith('<svg')) {
        doc.write(`<!DOCTYPE html><html><body style="margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#fff;">${content}</body></html>`);
    } else if (content) {
        doc.write(content);
    }
    doc.close();

    document.getElementById('doc-viewer-footer').style.display = 'none';
    document.getElementById('doc-viewer-chunk-nav').style.display = 'none';
}

// Render document text with highlighted chunks
function renderDocumentText(fullText, allChunks, highlightedChunks) {
    const field = _dvTextField();
    if (!field) return;

    if (!highlightedChunks || highlightedChunks.length === 0) {
        field.textContent = fullText;
        return;
    }

    // Build HTML with highlighted passages
    let html = escapeHtml(fullText);

    // Sort highlight chunks by length descending to avoid nested replacements
    const toHighlight = [...highlightedChunks].sort((a, b) => b.length - a.length);
    const seen = new Set();

    toHighlight.forEach((chunk, idx) => {
        const chunkText = typeof chunk === 'string' ? chunk : chunk.text;
        if (!chunkText || seen.has(chunkText)) return;
        seen.add(chunkText);
        const escaped = escapeHtml(chunkText);
        const id = `doc-chunk-${idx}`;
        const replacement = `<mark class="doc-viewer-highlight" id="${id}" data-chunk="${idx}" onclick="focusChunk(${idx})">${escaped}</mark>`;
        html = html.replace(escaped, replacement);
    });

    field.innerHTML = html;

    // Scroll to first highlight
    setTimeout(() => {
        const first = field.querySelector('.doc-viewer-highlight');
        if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
}

// Show chunk navigation pills
function showChunkNav(chunks) {
    const nav = document.getElementById('doc-viewer-chunk-nav');
    const pillsEl = document.getElementById('doc-viewer-chunk-pills');
    nav.style.display = 'flex';
    pillsEl.innerHTML = '';

    chunks.forEach((chunk, idx) => {
        const text = typeof chunk === 'string' ? chunk : chunk.text;
        const label = text.slice(0, 30).trim() + (text.length > 30 ? '…' : '');
        const pill = document.createElement('button');
        pill.className = 'doc-viewer-chunk-pill' + (idx === 0 ? ' active' : '');
        pill.innerHTML = `<span class="doc-viewer-chunk-pill-dot"></span>${escapeHtml(label)}`;
        pill.onclick = () => focusChunk(idx);
        pillsEl.appendChild(pill);
    });
}

// Scroll to and highlight a specific chunk
function focusChunk(idx) {
    document.querySelectorAll('.doc-viewer-highlight').forEach(el => el.classList.remove('active-chunk'));
    document.querySelectorAll('.doc-viewer-chunk-pill').forEach(el => el.classList.remove('active'));
    const mark = document.getElementById(`doc-chunk-${idx}`);
    if (mark) {
        mark.classList.add('active-chunk');
        mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    const pill = document.querySelectorAll('.doc-viewer-chunk-pill')[idx];
    if (pill) pill.classList.add('active');
}

// Switch between Source and Artifact tabs
function switchViewerTab(tab) {
    _dv.currentMode = tab;
    document.getElementById('tab-source').classList.toggle('active', tab === 'source');
    document.getElementById('tab-artifact').classList.toggle('active', tab === 'artifact');
    document.getElementById('doc-viewer-source').classList.toggle('active', tab === 'source');
    document.getElementById('doc-viewer-artifact').classList.toggle('active', tab === 'artifact');
    document.getElementById('doc-viewer-artifact').style.display = tab === 'artifact' ? 'block' : 'none';
}

// Close the viewer
function closeDocViewer() {
    _dvPane().style.display = 'none';
    _dvIframe().src = 'about:blank';
    document.querySelectorAll('.source-tag.source-doc').forEach(t => t.classList.remove('active'));
    _dv.currentSource = null;
}

// Copy button
async function copyDocViewerContent() {
    const btn = document.getElementById('doc-viewer-copy-btn');
    let text = '';

    if (_dv.currentMode === 'source') {
        text = document.getElementById('doc-viewer-text')?.textContent || '';
    } else {
        text = _dv.currentFileContent || '';
    }

    if (!text) return;
    try {
        await navigator.clipboard.writeText(text);
        btn.style.color = 'var(--success)';
        setTimeout(() => btn.style.color = '', 1500);
    } catch {}
}

// Download button
function downloadDocViewerContent() {
    if (_dv.currentFileUrl) {
        const a = document.createElement('a');
        a.href = _dv.currentFileUrl;
        a.download = _dv.currentSource || 'document';
        a.click();
    }
}

// Resize logic
function setupDocViewerResizer() {
    const resizer = document.getElementById('doc-viewer-resizer');
    const pane = document.getElementById('doc-viewer-pane');
    const container = document.querySelector('main.main');
    if (!resizer || !pane) return;

    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('resizing');
        document.body.style.cursor = 'col-resize';
        document.getElementById('doc-viewer-iframe').style.pointerEvents = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const containerRect = container.getBoundingClientRect();
        const newWidth = containerRect.right - e.clientX;
        if (newWidth > 280 && newWidth < containerRect.width - 280) {
            pane.style.flex = `0 0 ${newWidth}px`;
        }
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            resizer.classList.remove('resizing');
            document.body.style.cursor = '';
            document.getElementById('doc-viewer-iframe').style.pointerEvents = 'auto';
        }
    });
}

// Legacy alias for code artifact preview
function previewCanvas(btn) {
    const codeBlock = btn.closest('.code-block').querySelector('code').textContent;
    const title = btn.dataset.title || 'Preview';
    openArtifactViewer(codeBlock, title);
}

function toggleDeepThink() {
    state.deepThink = !state.deepThink;
    const btn = document.getElementById("deep-think-btn");
    if (btn) {
        if (state.deepThink) {
            btn.classList.add("active");
            btn.style.color = "var(--accent)";
            btn.style.borderColor = "var(--accent)";
            btn.style.background = "rgba(100, 100, 255, 0.1)"; // Soft accent transparent
        } else {
            btn.classList.remove("active");
            btn.style.color = "";
            btn.style.borderColor = "";
            btn.style.background = "";
        }
    }
}
