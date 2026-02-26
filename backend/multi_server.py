"""
Brahmastra Multi-Server Monitoring
====================================
Central hub that collects metrics from multiple remote servers.
Each server runs a lightweight agent that reports to this backend.

Architecture:
  [Server A] --(POST /api/servers/heartbeat)--> [Brahmastra Central]
  [Server B] --(POST /api/servers/heartbeat)--> [Brahmastra Central]
  [Server C] --(POST /api/servers/heartbeat)--> [Brahmastra Central]
                                                       |
                                              [Dashboard shows all]
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("Brahmastra-MultiServer")


class ServerNode:
    """Represents a monitored server."""

    def __init__(self, server_id: str, name: str, ip: str, role: str = "worker"):
        self.server_id = server_id
        self.name = name
        self.ip = ip
        self.role = role  # "primary", "worker", "database", "cache"
        self.status = "online"
        self.registered_at = datetime.now().isoformat()
        self.last_heartbeat = datetime.now()
        self.metrics_history = []
        self.max_history = 100
        self.current_metrics = {}
        self.alerts = []

    def update_metrics(self, metrics: dict):
        self.current_metrics = {
            "cpu": metrics.get("cpu", 0),
            "memory": metrics.get("memory", 0),
            "disk": metrics.get("disk", 0),
            "network_in": metrics.get("network_in", 0),
            "network_out": metrics.get("network_out", 0),
            "uptime": metrics.get("uptime", 0),
            "processes": metrics.get("processes", 0),
            "timestamp": datetime.now().isoformat(),
        }
        self.metrics_history.append(self.current_metrics)
        if len(self.metrics_history) > self.max_history:
            self.metrics_history = self.metrics_history[-self.max_history:]
        self.last_heartbeat = datetime.now()
        self.status = "online"

    def is_stale(self, timeout_seconds: int = 60) -> bool:
        return (datetime.now() - self.last_heartbeat).total_seconds() > timeout_seconds

    def to_dict(self) -> dict:
        return {
            "server_id": self.server_id,
            "name": self.name,
            "ip": self.ip,
            "role": self.role,
            "status": "offline" if self.is_stale() else self.status,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "current_metrics": self.current_metrics,
            "uptime_seconds": (datetime.now() - datetime.fromisoformat(self.registered_at)).total_seconds(),
        }


class MultiServerMonitor:
    """Manages multiple server nodes."""

    def __init__(self):
        self.servers: Dict[str, ServerNode] = {}
        self._add_local_server()
        logger.info("🌐 Multi-Server Monitor initialized")

    def _add_local_server(self):
        """Add the local (primary) server automatically."""
        import socket
        hostname = socket.gethostname()
        self.servers["local"] = ServerNode(
            server_id="local",
            name=f"Primary ({hostname})",
            ip="127.0.0.1",
            role="primary",
        )

    def register_server(self, server_id: str, name: str, ip: str, role: str = "worker") -> dict:
        if server_id in self.servers:
            self.servers[server_id].name = name
            self.servers[server_id].ip = ip
            self.servers[server_id].role = role
            self.servers[server_id].status = "online"
            self.servers[server_id].last_heartbeat = datetime.now()
            logger.info(f"🔄 Server re-registered: {name} ({server_id})")
        else:
            self.servers[server_id] = ServerNode(server_id, name, ip, role)
            logger.info(f"✅ Server registered: {name} ({server_id}) - {ip}")
        return self.servers[server_id].to_dict()

    def heartbeat(self, server_id: str, metrics: dict) -> dict:
        if server_id not in self.servers:
            return {"error": "Server not registered", "server_id": server_id}
        self.servers[server_id].update_metrics(metrics)
        return {"status": "ok", "server_id": server_id}

    def update_local_metrics(self, cpu: float, memory: float, disk: float):
        """Update the local primary server metrics."""
        if "local" in self.servers:
            self.servers["local"].update_metrics({
                "cpu": cpu, "memory": memory, "disk": disk,
            })

    def remove_server(self, server_id: str) -> bool:
        if server_id == "local":
            return False
        if server_id in self.servers:
            del self.servers[server_id]
            logger.info(f"🗑️ Server removed: {server_id}")
            return True
        return False

    def get_all_servers(self) -> List[dict]:
        # Update stale server statuses
        for s in self.servers.values():
            if s.is_stale() and s.server_id != "local":
                s.status = "offline"
        return [s.to_dict() for s in self.servers.values()]

    def get_server(self, server_id: str) -> Optional[dict]:
        if server_id in self.servers:
            return self.servers[server_id].to_dict()
        return None

    def get_server_metrics_history(self, server_id: str) -> List[dict]:
        if server_id in self.servers:
            return self.servers[server_id].metrics_history
        return []

    def get_fleet_summary(self) -> dict:
        servers = self.get_all_servers()
        online = sum(1 for s in servers if s["status"] == "online")
        offline = sum(1 for s in servers if s["status"] == "offline")

        avg_cpu = 0
        avg_memory = 0
        active_servers = [s for s in servers if s["status"] == "online" and s["current_metrics"]]
        if active_servers:
            avg_cpu = sum(s["current_metrics"].get("cpu", 0) for s in active_servers) / len(active_servers)
            avg_memory = sum(s["current_metrics"].get("memory", 0) for s in active_servers) / len(active_servers)

        return {
            "total_servers": len(servers),
            "online": online,
            "offline": offline,
            "avg_cpu": round(avg_cpu, 1),
            "avg_memory": round(avg_memory, 1),
            "servers": servers,
        }

    def generate_agent_script(self, central_url: str, server_name: str, api_key: str = "") -> str:
        """Generate a lightweight Python agent script for remote servers."""
        return f'''#!/usr/bin/env python3
"""Brahmastra Agent — Lightweight metrics reporter for remote servers."""
import time, psutil, socket, requests, uuid

CENTRAL_URL = "{central_url}"
SERVER_NAME = "{server_name}"
SERVER_ID = str(uuid.uuid4())[:8]
INTERVAL = 10  # seconds

def register():
    r = requests.post(f"{{CENTRAL_URL}}/api/servers/register", json={{
        "server_id": SERVER_ID, "name": SERVER_NAME,
        "ip": socket.gethostbyname(socket.gethostname()), "role": "worker"
    }})
    print(f"Registered: {{r.json()}}")

def send_heartbeat():
    metrics = {{
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "processes": len(psutil.pids()),
        "uptime": time.time() - psutil.boot_time(),
    }}
    r = requests.post(f"{{CENTRAL_URL}}/api/servers/heartbeat",
        json={{"server_id": SERVER_ID, "metrics": metrics}})
    return r.json()

if __name__ == "__main__":
    register()
    print(f"Agent started for {{SERVER_NAME}} (ID: {{SERVER_ID}})")
    while True:
        try:
            result = send_heartbeat()
            print(f"[{{SERVER_NAME}}] CPU={{psutil.cpu_percent()}}% MEM={{psutil.virtual_memory().percent}}%")
        except Exception as e:
            print(f"Error: {{e}}")
        time.sleep(INTERVAL)
'''


# ── Singleton ─────────────────────────────────────────────────
server_monitor = MultiServerMonitor()
