import re

with open("static/js/app.js", "r") as f:
    code = f.read()

# Make sendMessage accept parentId and text override
send_msg_start = "async function sendMessage() {"
send_msg_new = """async function sendMessage(overrideText = null, overrideParentId = null) {
    const text = overrideText !== null ? overrideText : textareaEl.value.trim();
    if (!text || state.isStreaming) return;

    const parentId = overrideParentId !== null ? overrideParentId : state.activeLeafId;"""

code = code.replace("async function sendMessage() {\n    const text = textareaEl.value.trim();\n    if (!text || state.isStreaming) return;", send_msg_new)

# In sendMessage, update the fetch body
code = code.replace("history: state.messages.slice(-10),", "history: state.messages.slice(-10),\n                parent_id: parentId,")

# In sendMessage, update loading indicator
code = code.replace("""    const contentEl = aiMsgEl.querySelector(".message-content");
    contentEl.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';""", """    const contentEl = aiMsgEl.querySelector(".message-content");
    contentEl.innerHTML = '<div class="loading-status"><div class="loading-spinner"></div> Model is thinking...</div>';""")

# In sendMessage, handle IDs returned
code = code.replace("""        if (fileInfo) {
            const dlDiv = document.createElement("div");""", """        
        // Save the new nodes to the tree
        if (data && data.user_message_id && data.message_id) {
            const uId = data.user_message_id;
            const aId = data.message_id;
            
            if (!state.messageMap[uId]) {
                state.messageMap[uId] = { id: uId, parent_id: parentId, role: "user", content: text, children: [] };
                if (parentId && state.messageMap[parentId]) state.messageMap[parentId].children.push(uId);
            }
            if (!state.messageMap[aId]) {
                state.messageMap[aId] = { id: aId, parent_id: uId, role: "assistant", content: fullText, children: [] };
                state.messageMap[uId].children.push(aId);
            }
            state.activeLeafId = aId;
            renderActiveThread(); // Re-render to show toolbars properly mapped
            return;
        }

        if (fileInfo) {
            const dlDiv = document.createElement("div");""")


with open("static/js/app.js", "w") as f:
    f.write(code)
