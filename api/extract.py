import os
import json
import requests
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        GH_TOKEN = os.environ.get('GH_TOKEN')
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data)
        
        gh_url = f"https://api.github.com/repos/Cheesenham/tunify/dispatches"
        headers = {
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "event_type": "extract_request",
            "client_payload": data
        }
        
        res = requests.post(gh_url, headers=headers, json=payload)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"success": True, "msg": "GitHub Cloud Worker Triggered"}).encode())
