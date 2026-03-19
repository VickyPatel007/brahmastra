import urllib.request
import urllib.error
import json
import time
import threading
import random

EC2_IP = "13.202.18.214"
BASE_URL = f"http://{EC2_IP}:8080"

print("🔥 Brahmastra Real-Time Traffic Simulator (DDOS MODE) 🔥")
print(f"Targeting: {BASE_URL}")
print("Spoofing IPs so your real IP doesn't get blocked.")
print("Watch your dashboard now! Press Ctrl+C to stop.\n")

def get_random_ip():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

def send_request(url, method="GET", data=None):
    try:
        req = urllib.request.Request(url, method=method)
        # 🛡️ Spoof the IP so the server doesn't ban Vivek's actual Mac IP!
        spoofed_ip = get_random_ip()
        req.add_header("X-Forwarded-For", spoofed_ip)
        req.add_header("X-Real-IP", spoofed_ip)
        
        if data:
            json_data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, data=json_data, timeout=2)
        else:
            urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass

def simulate_normal_traffic():
    """Simulates healthy users checking the server."""
    while True:
        send_request(f"{BASE_URL}/")
        send_request(f"{BASE_URL}/health")
        send_request(f"{BASE_URL}/api/stats")
        time.sleep(random.uniform(0.5, 2.0))

def simulate_brute_force():
    """Simulates a hacker trying to guess passwords."""
    while True:
        send_request(f"{BASE_URL}/api/auth/login", method="POST", data={
            "email": f"hacker{random.randint(1,10)}@evil.com",
            "password": "wrongpassword"
        })
        time.sleep(1.0)
        
def simulate_honeypot_hits():
    """Simulates bots scanning for vulnerabilities."""
    honeypot_paths = [
        "/phpmyadmin", "/.env", "/wp-admin", "/admin", "/config.php", "/api/v1/users", "/db_backup.sql"
    ]
    while True:
        path = random.choice(honeypot_paths)
        send_request(f"{BASE_URL}{path}")
        time.sleep(random.uniform(2, 5))

# Start the simulation threads
threads = []
for _ in range(4):
    threads.append(threading.Thread(target=simulate_normal_traffic, daemon=True))

for _ in range(3):
    threads.append(threading.Thread(target=simulate_brute_force, daemon=True))

threads.append(threading.Thread(target=simulate_honeypot_hits, daemon=True))

for t in threads:
    t.start()


try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Simulation Stopped.")
