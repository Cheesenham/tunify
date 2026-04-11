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
        self.root.title("MPL Pro Unity - Cloud Orchestrator")
        self.root.geometry("700x600")
        self.root.configure(bg="#1a1a1a")

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TLabel", foreground="white", background="#1a1a1a", font=("Segoe UI", 10))
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"))
        
        # Header
        header = tk.Label(root, text="MPL PRO BACKEND MANAGEMENT", bg="#1a1a1a", fg="#4361ee", font=("Segoe UI", 16, "bold"))
        header.pack(pady=20)

        # IP/URL Input
        ip_frame = tk.Frame(root, bg="#1a1a1a")
        ip_frame.pack(pady=5)
        tk.Label(ip_frame, text="Backend URL:", bg="#1a1a1a", fg="white").pack(side=tk.LEFT, padx=5)
        self.ip_entry = tk.Entry(ip_frame, width=40, font=("Consolas", 11), bg="#333", fg="white")
        self.ip_entry.insert(0, "https://reaches-pick-grow-open.trycloudflare.com")
        self.ip_entry.pack(side=tk.LEFT)

        # Action Buttons
        btn_frame = tk.Frame(root, bg="#1a1a1a")
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Sync Server Code", command=self.sync_server).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Repair Remote DB", command=self.repair_db).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Pkill Processes", command=self.pkill_all).pack(side=tk.LEFT, padx=5)

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
        
        # Tool Buttons
        tool_frame = tk.Frame(root, bg="#1a1a1a")
        tool_frame.pack(pady=5)
        ttk.Button(tool_frame, text="Check Status", command=self.check_status).pack(side=tk.LEFT, padx=5)
        ttk.Button(tool_frame, text="Check FFmpeg", command=self.check_ffmpeg_remote).pack(side=tk.LEFT, padx=5)

        self.log("System Ready. Connect to Termux backend.")

    def log(self, msg):
        self.root.after(0, self._log_safe, msg)

    def _log_safe(self, msg):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_area.see(tk.END)

    def get_url(self):
        url = self.ip_entry.get().strip()
        if not url: return ""
        if '1211' in url: url = "https://reaches-pick-grow-open.trycloudflare.com"
        if not url.startswith('http'): url = f"http://{url}:3000"
        return url

    def sync_server(self):
        threading.Thread(target=self._sync_task).start()

    def _sync_task(self):
        url = self.get_url()
        self.log(f"Syncing server.py to {url}...")
        try:
            with open("server.py", "r", encoding="utf-8") as f: code = f.read()
            payload = {"serverPy": code}
            data = json.dumps(payload).encode("utf-8")
            
            # Use the unified port 3000 (Cloudflare compatible)
            req = urllib.request.Request(f"{url}/api/system/emergency_update", data=data, headers={"Content-Type":"application/json"})
            urllib.request.urlopen(req, timeout=10)
            self.log("✅ Server code transmitted via Tunnel.")
            self.log("🎉 Sync Complete! Server is restarting.")
        except Exception as e:
            self.log(f"⚠️ Sync Error: {e}")

    def check_status(self):
        def task():
            url = self.get_url()
            try:
                res = urllib.request.urlopen(f"{url}/api/status", timeout=5)
                data = json.loads(res.read().decode())
                self.log(f"🟢 Server Online: {data.get('msg')}")
            except:
                self.log("🔴 Server Offline.")
        threading.Thread(target=task).start()

    def check_ffmpeg_remote(self):
        def task():
            url = self.get_url()
            try:
                res = urllib.request.urlopen(f"{url}/api/system/check_ffmpeg", timeout=5)
                d = json.loads(res.read().decode())
                self.log(f"🎬 FFmpeg Status: {d.get('msg')}")
            except Exception as e:
                self.log(f"❌ FFmpeg check failed: {e}")
        threading.Thread(target=task).start()

    def pkill_all(self):
        def task():
            url = self.get_url()
            self.log("Sending Nuke command to remote processes...")
            try:
                payload = {"cmd": "pkill -9 python"}
                data = json.dumps(payload).encode("utf-8")
                urllib.request.urlopen(urllib.request.Request(f"{url}/api/remote/shell", data=data, headers={"Content-Type":"application/json"}), timeout=5)
                self.log("💣 Nuked. Waiting for Auto-Restart...")
            except Exception as e:
                self.log(f"❌ Nuke failed: {e}")
        threading.Thread(target=task).start()

    def repair_db(self):
        def task():
            url = self.get_url()
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
                urllib.request.urlopen(urllib.request.Request(f"{url}/api/remote/shell", data=data, headers={"Content-Type":"application/json"}), timeout=10)
                self.log("✅ Remote DB Repaired. Try login with admin/1234.")
            except Exception as e:
                self.log(f"❌ Repair failed: {e}")
        threading.Thread(target=task).start()

    def exec_remote(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd: return
        self.cmd_entry.delete(0, tk.END)
        self.log(f"Run: {cmd}")
        def task():
            url = self.get_url()
            try:
                payload = {"cmd": cmd}
                data = json.dumps(payload).encode("utf-8")
                res = urllib.request.urlopen(urllib.request.Request(f"{url}/api/remote/shell", data=data, headers={"Content-Type":"application/json"}), timeout=10)
                d = json.loads(res.read().decode())
                if d.get("success"): self.log(f"Output: {d.get('output')}")
                else: self.log(f"Error: {d.get('error')}")
            except Exception as e:
                self.log(f"📡 Remote Shell Error: {e}")
        threading.Thread(target=task).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = MPLManagerGUI(root)
    root.mainloop()
