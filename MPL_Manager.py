import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import urllib.request
import threading
import os
import time

class MPLManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MPL Pro Unity - Multi-Device Orchestrator")
        self.root.geometry("700x600")
        self.root.configure(bg="#1a1a1a")

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TLabel", foreground="white", background="#1a1a1a", font=("Segoe UI", 10))
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"))
        
        # Header
        header = tk.Label(root, text="MPL PRO CLOUD MANAGEMENT", bg="#1a1a1a", fg="#4361ee", font=("Segoe UI", 16, "bold"))
        header.pack(pady=20)

        # IP Input
        ip_frame = tk.Frame(root, bg="#1a1a1a")
        ip_frame.pack(pady=5)
        tk.Label(ip_frame, text="Device IP:", bg="#1a1a1a", fg="white").pack(side=tk.LEFT, padx=5)
        self.ip_entry = tk.Entry(ip_frame, width=20, font=("Consolas", 11))
        self.ip_entry.insert(0, "192.168.200.109")
        self.ip_entry.pack(side=tk.LEFT)

        # Action Buttons
        btn_frame = tk.Frame(root, bg="#1a1a1a")
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Perfect Sync (All Files)", command=self.sync_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Check Status", command=self.check_status).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Check FFmpeg", command=self.check_ffmpeg_remote).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Pkill Python/Node", command=self.pkill_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Repair DB (Admin Fix)", command=self.repair_db).pack(side=tk.LEFT, padx=5)

        # Console
        tk.Label(root, text="Log Console:", bg="#1a1a1a", fg="#888").pack(anchor="w", padx=30)
        self.log_area = scrolledtext.ScrolledText(root, width=80, height=12, bg="#000", fg="#0f0", font=("Consolas", 10))
        self.log_area.pack(padx=20, pady=5)


        # Remote Shell
        shell_frame = tk.Frame(root, bg="#1a1a1a")
        shell_frame.pack(pady=10, fill=tk.X, padx=20)
        tk.Label(shell_frame, text="Shell Cmd:", bg="#1a1a1a", fg="white").pack(side=tk.LEFT, padx=5)
        self.cmd_entry = tk.Entry(shell_frame, bg="#333", fg="white", font=("Consolas", 11))
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.cmd_entry.bind("<Return>", lambda e: self.exec_remote())
        ttk.Button(shell_frame, text="Exec", command=self.exec_remote).pack(side=tk.LEFT)

        self.log("System Ready. Enter IP and click Sync All.")

    def log(self, msg):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_area.see(tk.END)

    def get_ip(self):
        return self.ip_entry.get().strip()

    def sync_all(self):
        threading.Thread(target=self._sync_all_task).start()

    def _sync_all_task(self):
        ip = self.get_ip()
        self.log(f"Starting Perfect Sync to {ip}...")
        
        files = {
            "server.py": "server.py",
            "ota_manager.py": "ota_manager.py",
            "public/index.html": "index.html",
            "public/maker.html": "maker.html",
            "public/player.html": "player.html"
        }

        # 1. Update Core Components (Try Port 4000 First, then Port 3000 for Cloudflare)
        self.log("Step 1: Updating System Cores...")
        cores_synced = False
        try:
            with open("server.py", "r", encoding="utf-8") as f: s_code = f.read()
            with open("public/index.html", "r", encoding="utf-8") as f: i_code = f.read()
            payload = {"serverPy": s_code, "indexHtml": i_code}
            data = json.dumps(payload).encode("utf-8")
            
            # Method A: Direct OTA (Port 4000)
            try:
                self.log("Trying Port 4000 (Local OTA)...")
                req = urllib.request.Request(f"http://{ip}:4000/emergency-update", data=data, headers={"Content-Type":"application/json"})
                urllib.request.urlopen(req, timeout=3)
                self.log("✅ Cores Transmitted via 4000.")
                cores_synced = True
            except:
                self.log("Port 4000 failed/closed. Trying Port 3000 (Cloudflare/API)...")
            
            # Method B: API OTA (Port 3000) - Works through Tunnels
            if not cores_synced:
                base_url = ip if ip.startswith('http') else f"http://{ip}:3000"
                req = urllib.request.Request(f"{base_url}/api/system/emergency_update", data=data, headers={"Content-Type":"application/json"})
                urllib.request.urlopen(req, timeout=10)
                self.log("✅ Cores Transmitted via 3000 (Tunnel).")
                cores_synced = True
                
        except Exception as e:
            self.log(f"⚠️ Core Sync Error: {e}")

        # 2. Update Assets (via Port 3000 API)
        time.sleep(4)
        self.log("Step 2: Force Syncing UI Assets (3000)...")
        for local_p, remote_n in files.items():
            if local_p == "server.py" or local_p == "ota_manager.py": continue
            try:
                with open(local_p, "r", encoding="utf-8") as f: content = f.read()
                payload = {"filename": remote_n, "content": content}
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(f"http://{ip}:3000/api/system/update_file", data=data, headers={"Content-Type":"application/json"})
                urllib.request.urlopen(req, timeout=5)
                self.log(f"✅ {remote_n} synced.")
            except Exception as e:
                self.log(f"❌ {remote_n} failed: {e}")
        
        self.log("🎉 Perfect Sync Complete!")

    def check_status(self):
        def task():
            ip = self.get_ip()
            try:
                res = urllib.request.urlopen(f"http://{ip}:3000/api/status", timeout=3)
                data = json.loads(res.read().decode())
                self.log(f"🟢 Server Online: {data.get('msg')}")
            except:
                self.log("🔴 Server Offline. Try Sync All or Pkill.")
        threading.Thread(target=task).start()

    def check_ffmpeg_remote(self):
        def task():
            ip = self.get_ip()
            try:
                res = urllib.request.urlopen(f"http://{ip}:3000/api/system/check_ffmpeg", timeout=5)
                d = json.loads(res.read().decode())
                self.log(f"🎬 FFmpeg Status: {d.get('msg')}")
                if not d.get('installed'):
                    self.log("💡 Fix: Type 'pkg install ffmpeg' in Shell Cmd and click Exec.")
            except Exception as e:
                self.log(f"❌ FFmpeg check failed: {e}")
        threading.Thread(target=task).start()

    def pkill_all(self):
        def task():
            ip = self.get_ip()
            self.log("Sending Nuke command to all python/node processes...")
            try:
                payload = {"cmd": "pkill -9 python; pkill -9 node"}
                data = json.dumps(payload).encode("utf-8")
                urllib.request.urlopen(urllib.request.Request(f"http://{ip}:3000/api/remote/shell", data=data, headers={"Content-Type":"application/json"}), timeout=5)
                self.log("💣 Nuked. Waiting for Auto-Restart...")
            except Exception as e:
                self.log(f"❌ Nuke failed: {e}")
        threading.Thread(target=task).start()

    def exec_remote(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd: return
        self.cmd_entry.delete(0, tk.END)
        self.log(f"Run: {cmd}")
        def task():
            ip = self.get_ip()
            try:
                payload = {"cmd": cmd}
                data = json.dumps(payload).encode("utf-8")
                res = urllib.request.urlopen(urllib.request.Request(f"http://{ip}:3000/api/remote/shell", data=data, headers={"Content-Type":"application/json"}), timeout=10)
                d = json.loads(res.read().decode())
                if d.get("success"): self.log(f"Output: {d.get('output')}")
                else: self.log(f"Error: {d.get('error')}")
            except Exception as e:
                self.log(f"📡 Remote Shell Error: {e}")
        threading.Thread(target=task).start()

    def repair_db(self):
        def task():
            ip = self.get_ip()
            self.log("Repairing Remote Database (users.json)...")
            try:
                users_data = {
                    "admin": {"pw": "1234", "role": "admin"},
                    "testuser": {"pw": "1234", "role": "user"}
                }
                content = json.dumps(users_data, indent=2)
                cmd = f"mkdir -p db && echo '{content}' > db/users.json"
                payload = {"cmd": cmd}
                data = json.dumps(payload).encode("utf-8")
                res = urllib.request.urlopen(urllib.request.Request(f"http://{ip}:3000/api/remote/shell", data=data, headers={"Content-Type":"application/json"}), timeout=10)
                self.log("✅ Remote DB Repaired. Try login with admin/1234.")
            except Exception as e:
                self.log(f"❌ Repair failed: {e}")
        threading.Thread(target=task).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = MPLManagerGUI(root)
    root.mainloop()
