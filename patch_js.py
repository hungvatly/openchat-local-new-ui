import re

with open("static/js/app.js", "r") as f:
    code = f.read()

# 1. Update state
code = code.replace("    messages: [],", "    messages: [],\n    messageMap: {}, // id -> message node\n    activeLeafId: null,")

# 2. Update clearChat
code = code.replace("    state.messages = [];\n    state.conversationId = null;\n", "    state.messages = [];\n    state.messageMap = {};\n    state.activeLeafId = null;\n    state.conversationId = null;\n")

# 3. Update loadConversation
old_load = """        conv.messages.forEach((m) => {
            appendMessage(m.role === "user" ? "user" : "ai", m.content);
            state.messages.push({ role: m.role, content: m.content });
        });

        chatAreaEl.scrollTop = chatAreaEl.scrollHeight;"""

new_load = """        state.messageMap = {};
        conv.messages.forEach(m => {
            state.messageMap[m.id] = { ...m, children: [] };
        });
        Object.values(state.messageMap).forEach(m => {
            if (m.parent_id && state.messageMap[m.parent_id]) {
                state.messageMap[m.parent_id].children.push(m.id);
            }
        });
        // Pick leaf
        if (conv.messages.length > 0) {
            state.activeLeafId = conv.messages[conv.messages.length - 1].id;
            renderActiveThread();
        } else {
            state.activeLeafId = null;
        }"""
code = code.replace(old_load, new_load)

with open("static/js/app.js", "w") as f:
    f.write(code)
