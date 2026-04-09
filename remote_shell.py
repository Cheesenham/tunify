import json
import urllib.request
import sys

def run():
    print("🎮 [MPL Remote Terminal] 휴대폰을 조종합니다.")
    ip = input("휴대폰 IP 주소를 입력하세요 (기본: 192.168.200.109): ").strip()
    if not ip: ip = "192.168.200.109"
    
    url = f"http://{ip}:3000/api/remote/shell"
    
    print("\n--- 조종 모드 시작 (종료하려면 'exit' 입력) ---")
    while True:
        cmd = input(f"MPL@{ip} ~$ ").strip()
        if not cmd: continue
        if cmd.lower() == 'exit': break
        
        payload = {"cmd": cmd}
        data = json.dumps(payload).encode("utf-8")
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                d = json.loads(res.read().decode('utf-8'))
                if d.get('success'):
                    print(d.get('output'))
                else:
                    print(f"❌ 실행 실패: {d.get('error')}")
        except Exception as e:
            print(f"📡 통신 실패: {e}")

if __name__ == '__main__':
    run()
