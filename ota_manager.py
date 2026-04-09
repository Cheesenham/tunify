import http.server
import json
import os
import subprocess
import threading
import time

server_proc = None

def maintain_server():
    global server_proc
    while True:
        print("🛡️ [시스템 감시자] 파이썬 네이티브 메인 서버(server.py) 가동 중...")
        server_proc = subprocess.Popen(["python", "server.py"])
        server_proc.wait()
        print(f"💀 [시스템 감시자] 메인 서버 사망. 3초 뒤 자동 부활합니다...")
        time.sleep(3)

class OTAHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == '/emergency-update':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))
            
            if 'serverPy' in data:
                with open('server.py', 'w', encoding='utf-8') as f:
                    f.write(data['serverPy'])
            if 'indexHtml' in data:
                with open(os.path.join('public', 'index.html'), 'w', encoding='utf-8') as f:
                    f.write(data['indexHtml'])
            if 'makerHtml' in data:
                with open(os.path.join('public', 'maker.html'), 'w', encoding='utf-8') as f:
                    f.write(data['makerHtml'])
            if 'playerHtml' in data:
                with open(os.path.join('public', 'player.html'), 'w', encoding='utf-8') as f:
                    f.write(data['playerHtml'])
                    
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
            print("🔌 [시스템 감시자] 긴급 OTA 패치 완료! 기존 프로세스를 킬하고 재부팅합니다.")
            if server_proc:
                server_proc.kill()

if __name__ == '__main__':
    t = threading.Thread(target=maintain_server, daemon=True)
    t.start()
    
    print("📶 [비상망 가동] 파이썬 무적 통신병 대기중. 포트 4000 오픈 완료.")
    httpd = http.server.HTTPServer(('0.0.0.0', 4000), OTAHandler)
    httpd.serve_forever()
