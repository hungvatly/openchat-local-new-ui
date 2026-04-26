import re

with open("static/js/app.js", "r") as f:
    code = f.read()

# Replace clearChat with correct one (I did it already partially)
# Now add renderActiveThread and missing branching functions in global scope

new_funcs = """
function renderActiveThread() {
    chatAreaEl.innerHTML = "";
    state.messages = []; // Linear context for LLM history limit
    
    if (!state.activeLeafId) return;
    
    let path = [];
    let curr = state.activeLeafId;
    while (curr && state.messageMap[curr]) {
        path.unshift(state.messageMap[curr]);
        curr = state.messageMap[curr].parent_id;
    }
    
    path.forEach(m => {
        _appendNodeToUI(m);
        state.messages.push({ role: m.role, content: m.content });
    });
    
    chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
    postRenderEnhance();
}

function switchBranch(messageId, childIdx) {
    const node = state.messageMap[messageId];
    if (!node || node.children.length <= childIdx) return;
    
    // Find the leaf of this new branch
    let curr = state.messageMap[node.children[childIdx]];
    while (curr.children && curr.children.length > 0) {
        // Just pick the last modified child (or first)
        curr = state.messageMap[curr.children[curr.children.length - 1]];
    }
    state.activeLeafId = curr.id;
    renderActiveThread();
}

function beginEditMessage(id) {
    const el = document.getElementById("msg-content-" + id);
    if (!el) return;
    const node = state.messageMap[id];
    el.innerHTML = `
        <textarea class="message-edit-box" id="msg-edit-ta-${id}">${escapeHtml(node.content)}</textarea>
        <div class="message-edit-actions">
            <button class="btn btn-outline" style="padding:4px 10px;font-size:12px" onclick="renderActiveThread()">Cancel</button>
            <button class="btn" style="padding:4px 10px;font-size:12px" onclick="submitEditMessage(${id})">Save & Submit</button>
        </div>
    `;
}

function submitEditMessage(id) {
    const node = state.messageMap[id];
    const ta = document.getElementById("msg-edit-ta-" + id);
    if (!ta) return;
    const newText = ta.value.trim();
    if (newText === node.content) {
        renderActiveThread(); // no change
        return;
    }
    // Branch off from its parent
    sendMessage(newText, node.parent_id);
}

function regenerateMessage(id) {
    const node = state.messageMap[id];
    // node is the AI message. Branch off of its parent (the user message)
    if (node.parent_id) {
        const userNode = state.messageMap[node.parent_id];
        sendMessage(userNode.content, userNode.parent_id);
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
            <button class="export-btn" onclick="beginEditMessage(${m.id})" title="Edit message">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                Edit
            </button>
        `;
    } else {
        toolbarHtml += `
            <button class="export-btn" onclick="regenerateMessage(${m.id})" title="Regenerate answer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
                Regenerate
            </button>
        `;
    }
    
    toolbarHtml += `
        <button class="export-btn" onclick="copyResponse(this)" title="Copy text">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            Copy
        </button>
    </div>`;
    
    // Branch Navigation logic
    let navHtml = "";
    if (m.parent_id && state.messageMap[m.parent_id]) {
        const parent = state.messageMap[m.parent_id];
        if (parent.children.length > 1) {
            const idx = parent.children.indexOf(m.id);
            const total = parent.children.length;
            navHtml = `
            <div class="branch-nav">
                <button class="branch-nav-btn" ${idx === 0 ? "disabled style='opacity:0.3'" : ""} onclick="switchBranch(${m.parent_id}, ${idx - 1})">‹</button>
                <span>${idx + 1} / ${total}</span>
                <button class="branch-nav-btn" ${idx === total - 1 ? "disabled style='opacity:0.3'" : ""} onclick="switchBranch(${m.parent_id}, ${idx + 1})">›</button>
            </div>`;
        }
    }
    
    div.innerHTML = contentHtml + navHtml + toolbarHtml;
    chatAreaEl.appendChild(div);
    return div;
}
"""

old_appendMessage = """function appendMessage(role, text) {
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
}"""

# Actually, the user message logic in sendMessage calls appendMessage("user", text) and ("ai", "")
# It's better to leave appendMessage for streaming/temporary rendering, and just use _appendNodeToUI for the tree rendering.
# Let's keep appendMessage but update the loading-status

code = code.replace(old_appendMessage, old_appendMessage + "\n" + new_funcs)

# Update the parse code where we added data.user_message_id and data.message_id
# If stream doesn't crash, it will append correctly.
# But wait, in the streaming loop where does it use `data` variable?
# It was defined earlier `const data = JSON.parse(...)`.

with open("static/js/app.js", "w") as f:
    f.write(code)
