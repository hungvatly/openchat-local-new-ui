import os
import time
import base64
import subprocess
import threading
from typing import Optional

SCREENCAST_PATH = "/tmp/openchat_screen.jpg"

class ScreenContext:
    def __init__(self):
        self.is_running = False
        self._thread = None

    def start(self, interval_seconds=30):
        if self.is_running: return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, args=(interval_seconds,), daemon=True)
        self._thread.start()
        print("[*] Screen Context Daemon started.")

    def stop(self):
        self.is_running = False

    def _run_loop(self, interval: int):
        while self.is_running:
            self.capture_now()
            time.sleep(interval)

    def capture_now(self) -> Optional[str]:
        """Captures the screen to disk and returns a base64 string."""
        try:
            # -x: don't play sound, -t: format
            subprocess.run(["screencapture", "-x", "-t", "jpg", SCREENCAST_PATH], check=True)
            if os.path.exists(SCREENCAST_PATH):
                with open(SCREENCAST_PATH, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"[!] Failed to capture screen: {e}")
        return None

    def get_latest_capture_b64(self) -> Optional[str]:
        """Reads the latest screen capture from disk."""
        if os.path.exists(SCREENCAST_PATH):
            try:
                with open(SCREENCAST_PATH, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
        return None

screen_context = ScreenContext()
