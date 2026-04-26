import re

with open('OpenChatLocal.swift', 'r') as f:
    code = f.read()

# Add dragWindow handler
handler_code = """
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "nativeApp",
              let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }
        
        if action == "dragWindow" {
            DispatchQueue.main.async {
                if let event = NSApp.currentEvent {
                    self.mainWindow?.performDrag(with: event)
                }
            }
            return
        }
"""

if 'action == "dragWindow"' not in code:
    code = code.replace('''    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "nativeApp",
              let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }''', handler_code)
    
    with open('OpenChatLocal.swift', 'w') as f:
        f.write(code)
    print("Patched swift")
else:
    print("Already patched")
