import http.server
import json
import os
import subprocess
import threading
import time
import re

server_proc = None
tunnel_proc = None
tunnel_url = "Not Started"

# --- [1] 메인 서버(server.py) 관리 ---
def maintain_server():
    global server_proc
    while True:
        print("🛡️ [시스템 감시자] 파이썬 네이티브 메인 서버(server.py) 가동 중...")
        # server.py가 종료되면(예: 업데이트 시 os._exit(0)) 다시 시작함
        server_proc = subprocess.Popen(["python", "server.py"])
        server_proc.wait()
        print(f"💀 [시스템 감시자] 메인 서버 사망. 3초 뒤 자동 부활합니다...")
        time.sleep(3)

# --- [2] 클라우드플레어 터널(cloudflared) 관리 ---
def maintain_tunnel():
    global tunnel_proc, tunnel_url
    while True:
        print("🌐 [터널 감시자] Cloudflare 터널 기동 중...")
        # --url http://localhost:3000 으로 포트 3000을 외부로 노출
        tunnel_proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", "http://localhost:3000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # 로그에서 URL 추출 (https://*.trycloudflare.com 형식)
        for line in iter(tunnel_proc.stdout.readline, ""):
            if not line: break
            print(f"☁️ [Cloudflare] {line.strip()}")
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                tunnel_url = match.group(0)
                print(f"\n✨ [접속 주소 확인됨] {tunnel_url}")
                print(f"💡 MPL Manager의 Device IP에 위 주소를 입력하세요.\n")
                # 주소를 파일로 저장하여 다른 프로그램에서 참고 가능하게 함
                os.makedirs('db', exist_ok=True)
                with open('db/tunnel_url.txt', 'w') as f:
                    f.write(tunnel_url)
        
        tunnel_proc.wait()
        print("⚠️ [터널 감시자] 터널이 끊겼습니다. 5초 뒤 재연결을 시도합니다...")
        time.sleep(5)

# --- [3] 비상 OTA 핸들러 (포트 4000) ---
class OTAHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == '/emergency-update':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))
            
            # 파일 쓰기
            if 'serverPy' in data:
                with open('server.py', 'w', encoding='utf-8') as f:
                    f.write(data['serverPy'])
            if 'indexHtml' in data:
                os.makedirs('public', exist_ok=True)
                with open(os.path.join('public', 'index.html'), 'w', encoding='utf-8') as f:
                    f.write(data['indexHtml'])
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
            print("🔌 [시스템 감시자] 긴급 OTA 패치 완료! 서버를 재부팅합니다.")
            if server_proc:
                server_proc.kill()

if __name__ == '__main__':
    # 1. 메인 서버 감시 스레드
    threading.Thread(target=maintain_server, daemon=True).start()
    
    # 2. 터널 감시 스레드 (Termux에 cloudflared가 설치되어 있어야 함)
    threading.Thread(target=maintain_tunnel, daemon=True).start()
    
    # 3. 비상망 핸들러 (4000포트)
    print("📶 [비상망 가동] 포트 4000 오픈 완료. Cloudflare 터널링 대기 중...")
    httpd = http.server.HTTPServer(('0.0.0.0', 4000), OTAHandler)
    httpd.serve_forever()
