import os
import json
import yt_dlp
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data)
        
        query = data.get('query')
        source = data.get('source', 'yt')
        
        if not query:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "msg": "No query"}).encode())
            return

        try:
            search_query = f"ytsearch5:{query}" if source == 'yt' else f"scsearch5:{query}"
            ydl_opts = {'quiet': True, 'skip_download': True, 'extract_flat': True}
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(search_query, download=False)
                entries = results.get('entries', [])
                output = []
                for entry in entries:
                    output.append({
                        "id": entry.get('id'),
                        "url": entry.get('url') or entry.get('webpage_url'),
                        "title": entry.get('title'),
                        "thumbnail": entry.get('thumbnail'),
                        "uploader": entry.get('uploader')
                    })
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "results": output}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "msg": str(e)}).encode())
