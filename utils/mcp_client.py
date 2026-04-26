import os
import json
import asyncio
import subprocess
from typing import Dict, Any, List

MCP_SERVERS_FILE = "data/mcp_servers.json"

class MCPManager:
    def __init__(self):
        self.servers: Dict[str, Any] = self._load_servers()
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.available_tools: List[Dict[str, Any]] = []

    def _load_servers(self) -> Dict[str, Any]:
        if os.path.exists(MCP_SERVERS_FILE):
            try:
                with open(MCP_SERVERS_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_servers(self):
        os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
        with open(MCP_SERVERS_FILE, 'w') as f:
            json.dump(self.servers, f, indent=4)

    def add_server(self, name: str, command: str, args: List[str]):
        self.servers[name] = {"command": command, "args": args}
        self.save_servers()

    def remove_server(self, name: str):
        if name in self.servers:
            del self.servers[name]
            self.save_servers()
            self.stop_server(name)

    async def start_all(self):
        for name, config in self.servers.items():
            await self.start_server(name, config["command"], config["args"])

    async def start_server(self, name: str, command: str, args: List[str]):
        allowed_binaries = {"npx", "node", "npm", "python", "python3"}
        cmd_base = os.path.basename(command)
        if cmd_base not in allowed_binaries:
            val_err = f"Command '{cmd_base}' is not allowed for security reasons. Allowed: {', '.join(allowed_binaries)}"
            print(f"[!] {val_err}")
            raise ValueError(val_err)

        try:
            # Spawn the MCP server via stdio
            proc = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.active_processes[name] = proc
            
            # Send MCP initialize JSON-RPC
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "1.0",
                    "clientInfo": {"name": "OpenChatLocal", "version": "1.0"}
                }
            }
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()
            
            # Wait for initialize response (in a real async loop we'd use streams)
            # For this Phase 1 placeholder, we just log that it started.
            print(f"[*] Started MCP Server '{name}' successfully.")
            
        except Exception as e:
            print(f"[!] Failed to start MCP Server '{name}': {e}")

    def stop_server(self, name: str):
        if name in self.active_processes:
            proc = self.active_processes.pop(name)
            proc.terminate()

    def stop_all(self):
        for name in list(self.active_processes.keys()):
            self.stop_server(name)

mcp_manager = MCPManager()
