import json
import urllib.request
import os

def run():
    print("🚀 [ASSET UPDATER] 폰의 public 폴더를 강제로 동기화합니다.")
    ip = input("휴대폰 IP 주소를 입력하세요 (기본: 192.168.200.109): ").strip()
    if not ip: ip = "192.168.200.109"
    
    # 동기화할 파일들
    files_to_sync = [
        "public/index.html",
        "public/maker.html",
        "public/player.html"
    ]
    
    url = f"http://{ip}:3000/api/system/update_file"
    
    for relative_path in files_to_sync:
        print(f"📡 {relative_path} 전송 중...", end=" ")
        try:
            with open(relative_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            payload = {
                "filename": os.path.basename(relative_path),
                "content": content
            }
            data = json.dumps(payload).encode("utf-8")
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as res:
                d = json.loads(res.read().decode('utf-8'))
                if d.get('success'):
                    print("✅ 완료")
                else:
                    print(f"❌ 실패: {d.get('error')}")
        except Exception as e:
            print(f"❌ 에러: {e}")

if __name__ == '__main__':
    run()
