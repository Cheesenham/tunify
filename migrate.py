import json
import urllib.request
import os

def run():
    print("🚀 [FULL PATCH START] 모든 시스템 파일을 한 번에 이주시키는 통합 패치 실행 중...")
    
    # 1. 모든 필수 파일 읽기
    try:
        with open("server.py", "r", encoding="utf-8") as f: server_py = f.read()
        with open("ota_manager.py", "r", encoding="utf-8") as f: ota_py = f.read()
        with open("public/index.html", "r", encoding="utf-8") as f: index_h = f.read()
        with open("public/maker.html", "r", encoding="utf-8") as f: maker_h = f.read()
        with open("public/player.html", "r", encoding="utf-8") as f: player_h = f.read()
    except Exception as e:
        print(f"❌ 파일 읽기 실패: {e}")
        return

    # 2. 타겟 IP 입력
    ip = input("업데이트할 휴대폰 IP 주소를 입력하세요 (예: 192.168.0.x): ").strip()
    if not ip: ip = "192.168.200.109"
    url = f"http://{ip}:4000/emergency-update"

    # 3. 5종 세트 파일 저장 자바스크립트 생성 (구형 ota_manager가 실행하도록)
    js_bomb = f"""
const fs = require('fs');
const {{ spawn, execSync }} = require('child_process');

if (!fs.existsSync('public')) fs.mkdirSync('public');

const files = {{
    'server.py': '{server_py.encode('utf-8').hex()}',
    'ota_manager.py': '{ota_py.encode('utf-8').hex()}',
    'public/index.html': '{index_h.encode('utf-8').hex()}',
    'public/maker.html': '{maker_h.encode('utf-8').hex()}',
    'public/player.html': '{player_h.encode('utf-8').hex()}'
}};

for (const [name, hex] of Object.entries(files)) {{
    fs.writeFileSync(name, Buffer.from(hex, 'hex').toString('utf-8'));
    console.log(`✅ ${{name}} 저장 완료`);
}}

try {{
    console.log("⏳ pip 설치 시도 중...");
    execSync('pip install flask flask-cors yt-dlp syncedlyrics', {{ stdio: 'inherit' }});
}} catch(e) {{}}

console.log("🚀 구형 노출 감시자 종료 및 파이썬 서버로 즉시 환생합니다.");
const pyCmd = "sleep 2 && python ota_manager.py";
const py = spawn('sh', ['-c', pyCmd], {{ detached: true, stdio: 'ignore' }});
py.unref();

setTimeout(() => {{
    try {{ process.kill(process.ppid, 'SIGKILL'); }} catch(e) {{}}
    process.exit(0);
}}, 500);
"""

    payload = { "serverJs": js_bomb, "indexHtml": index_h }
    data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=10)
        print("✅ 통합 패치 전송 대성공!! 이제 폰에서 /player /maker 모두 접속 가능합니다.")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

if __name__ == '__main__':
    run()
