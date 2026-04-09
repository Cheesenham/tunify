import urllib.request
import json
import os
import sys

def deploy(target_ip):
    print(f"🚀 MPL OTA 긴급 비상 배포 시스템 가동 (대상: {target_ip}:4000)")
    
    try:
        # 파일 읽기
        with open("server.py", "r", encoding="utf-8") as f:
            server_code = f.read()
        
        with open("public/index.html", "r", encoding="utf-8") as f:
            html_code = f.read()
        
        with open("public/maker.html", "r", encoding="utf-8") as f:
            maker_code = f.read()
            
        with open("public/player.html", "r", encoding="utf-8") as f:
            player_code = f.read()
            
        payload = {
            "serverPy": server_code,
            "indexHtml": html_code,
            "makerHtml": maker_code,
            "playerHtml": player_code
        }
        
        data = json.dumps(payload).encode("utf-8")
        
        # 포트 4000 (시스템 감시자 비상포트) 로 전송
        target_url = f"http://{target_ip}:4000/emergency-update"
        
        print("📡 비상 채널로 코드 전송 중...")
        req = urllib.request.Request(target_url, data=data, headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get('success'):
                print("✅ 비상 배포 대성공! 휴대폰 서버가 스스로 심폐소생 되어 부활합니다.")
            else:
                print("❌ 서버 측 반영 실패: " + str(res_data))
                
    except Exception as e:
        print(f"❌ 예외: 전송 불가. 감시망(포트 4000)을 찾을 수 없거나 IP가 틀렸습니다. 상세오류: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ip = sys.argv[1]
    else:
        ip = input("업데이트할 휴대폰 IP 주소를 입력하세요 (예: 192.168.0.x): ").strip()
    deploy(ip)
