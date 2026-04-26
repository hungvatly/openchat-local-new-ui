import socket
import threading
from typing import Optional

try:
    from zeroconf import ServiceInfo, Zeroconf
except ImportError:
    Zeroconf = None

class NetworkDiscovery:
    def __init__(self, port: int = 8000, name: str = "OpenChat Local"):
        self.port = port
        self.name = name
        self.zeroconf: Optional[Zeroconf] = None
        self.info: Optional[ServiceInfo] = None

    def _get_local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def start_broadcasting(self):
        if not Zeroconf:
            print("[LAN] python-zeroconf not installed. Skipping network broadcast.")
            return

        ip = self._get_local_ip()
        desc = {'path': '/'}

        # Ensure the IP address is parsed correctly for the addresses field
        ip_bytes = socket.inet_aton(ip)

        self.info = ServiceInfo(
            "_http._tcp.local.",
            f"{self.name}._http._tcp.local.",
            addresses=[ip_bytes],
            port=self.port,
            properties=desc,
            server="openchat.local.",
        )

        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(self.info)
        print(f"[*] Broadcasting OpenChat Local on LAN at {ip}:{self.port}")

    def stop_broadcasting(self):
        if self.zeroconf and self.info:
            self.zeroconf.unregister_service(self.info)
            self.zeroconf.close()
            self.zeroconf = None

network_discovery = NetworkDiscovery()
