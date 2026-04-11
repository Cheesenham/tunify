import os
import json
import time
import threading
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, 'mpl_storage')
os.makedirs(STORAGE_DIR, exist_ok=True)

# Supabase Settings
SUPABASE_URL = "https://rwmifnnqlbljomwayjzm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ3bWlmbm5xbGJsam9td2F5anptIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4NzI4NDUsImV4cCI6MjA5MTQ0ODg0NX0.HSbt457Z7XdBTFWMTKfjwq8k1jtw6U8SZxN33LISeCw"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Helpers ---
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except: return False

@app.route('/api/status')
def status():
    return jsonify({"success": True, "msg": "MPL Supabase Extraction Worker Online", "ffmpeg": check_ffmpeg()})

# --- Extraction logic with Supabase Upload ---
@app.route('/api/maker/extract', methods=['POST'])
def extract_v3():
    data = request.json
    url = data.get('url')
    mode = data.get('mode', 'music') # music or video
    uid = data.get('uid', 'public')
    
    if not url: return jsonify({"success": False, "msg": "URL이 누락되었습니다."})

    def run_extract():
        try:
            timestamp = int(time.time())
            ext = 'mp3' if mode == 'music' else 'mp4'
            filename = f"mpl_{uid}_{timestamp}.{ext}"
            out_path = os.path.join(STORAGE_DIR, filename)
            
            # 1. Download with yt-dlp
            has_ffmpeg = check_ffmpeg()
            cmd = ['yt-dlp']
            if mode == 'music':
                cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
            else:
                if has_ffmpeg:
                    cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best']
                else:
                    cmd += ['-f', 'best[ext=mp4]']
            
            cmd += ['-o', out_path, url]
            subprocess.run(cmd, check=True)

            # 2. Upload to Supabase Storage (Bucket: media)
            print(f"⬆️ [Supabase] 업로드 시작: {filename}")
            with open(out_path, 'rb') as f:
                # 버킷 이름은 'media'로 가정 (사전에 생성 필요)
                res = supabase.storage.from_('media').upload(
                    path=f"{uid}/{filename}",
                    file=f,
                    file_options={"content-type": f"audio/mpeg" if mode == 'music' else "video/mp4"}
                )
            
            # 3. Get Public URL
            public_url = supabase.storage.from_('media').get_public_url(f"{uid}/{filename}")
            print(f"✅ [Supabase] 업로드 완료: {public_url}")

            # 4. Optional: Save metadata to Postgre DB
            try:
                supabase.table('media_files').insert({
                    "uid": uid,
                    "filename": filename,
                    "url": public_url,
                    "type": mode,
                    "created_at": "now()"
                }).execute()
            except Exception as e:
                print(f"⚠️ [DB] 기록 실패 (테이블 확인 필요): {e}")

            # 5. Cleanup local file
            if os.path.exists(out_path):
                os.remove(out_path)
                print(f"🗑️ [Cleanup] 로컬 파일 삭제 완료: {filename}")

        except Exception as e:
            print(f"❌ [Error] Extraction/Upload Failed: {str(e)}")

    threading.Thread(target=run_extract, daemon=True).start()
    return jsonify({"success": True, "msg": "추출 및 클라우드 업로드 시작됨. 잠시 후 Supabase에서 확인하세요."})

# --- 자동 휴지통 비우기 (7일 경과 파일 삭제) ---
def cleanup_trash_task():
    while True:
        try:
            for uid in os.listdir(STORAGE_DIR):
                trash_path = os.path.join(STORAGE_DIR, uid, '.trash')
                if os.path.exists(trash_path):
                    now = time.time()
                    for f in os.listdir(trash_path):
                        fp = os.path.join(trash_path, f)
                        # 파일 생성/수정 시간이 7일(604800초) 이상 지났으면 삭제
                        if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > 604800:
                            os.remove(fp)
                            print(f"🗑️ [자동 삭제] 휴지통에서 7일 경과된 파일 삭제: {f}")
        except Exception as e:
            print(f"⚠️ [휴지통 정리 에러] {e}")
        time.sleep(86400) # 하루에 한 번 체크

threading.Thread(target=cleanup_trash_task, daemon=True).start()

# --- 라우팅: 기본 정적 파일 ---
@app.route('/')
def serve_index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

@app.route('/maker')
def serve_maker():
    return send_from_directory(PUBLIC_DIR, 'maker.html')

@app.route('/player')
def serve_player():
    return send_from_directory(PUBLIC_DIR, 'player.html')

@app.route('/<path:path>')
def serve_public(path):
    if os.path.exists(os.path.join(PUBLIC_DIR, path)):
        return send_from_directory(PUBLIC_DIR, path)
    return f"404: {path} 를 찾을 수 없습니다.", 404

# --- API: 유저 및 계정 시스템 ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id', '').strip()
    pw = data.get('pw', '').strip()
    if not uid: return jsonify({"success": False, "msg": "아이디를 입력하세요."})
        
    users = load_users()
    if uid not in users: return jsonify({"success": False, "msg": "존재하지 않는 계정입니다."})
    if users[uid].get('pw') != pw: return jsonify({"success": False, "msg": "비밀번호가 일치하지 않습니다."})
        
    os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
    return jsonify({"success": True, "id": uid, "role": users[uid].get('role', 'user')})

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
def admin_users():
    users = load_users()
    data = request.json if request.is_json else {}
    if request.method == 'GET':
        return jsonify({"success": True, "users": users})
    elif request.method == 'POST':
        uid = data.get('id')
        if not uid: return jsonify({"success": False})
        users[uid] = {"pw": data.get('pw', '1234'), "role": "user"}
        save_users(users)
        os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
        return jsonify({"success": True})
    elif request.method == 'DELETE':
        uid = data.get('id')
        if uid in users and uid != 'admin':
            del users[uid]
            save_users(users)
        return jsonify({"success": True})

# --- API: 파일 관리 기능 ---
@app.route('/api/files', methods=['GET'])
def get_files():
    uid = request.args.get('id', '').strip()
    user_dir = os.path.join(STORAGE_DIR, uid)
    if not os.path.exists(user_dir): return jsonify({"success": True, "files": []})
    files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f)) and f.endswith(('.mpl', '.mplp'))]
    return jsonify({"success": True, "files": sorted(files)})

@app.route('/api/delete_file', methods=['POST'])
def soft_delete_file():
    data = request.json
    uid = data.get('id', '').strip()
    filename = data.get('filename', '').strip()
    target = os.path.join(STORAGE_DIR, uid, filename)
    trash = os.path.join(STORAGE_DIR, uid, '.trash')
    os.makedirs(trash, exist_ok=True)
    if os.path.exists(target):
        os.rename(target, os.path.join(trash, filename))
        return jsonify({"success": True, "msg": "휴지통으로 이동되었습니다. (7일 후 영구삭제)"})
    return jsonify({"success": False, "msg": "파일을 찾을 수 없습니다."})

@app.route('/api/rename', methods=['POST'])
def rename_file():
    data = request.json
    uid, old_name, new_name = data.get('id'), data.get('oldName'), data.get('newName')
    if not new_name.endswith(('.mpl', '.mplp')): new_name += '.mpl'
    old_path = os.path.join(STORAGE_DIR, uid, old_name)
    new_path = os.path.join(STORAGE_DIR, uid, new_name)
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
    return jsonify({"success": True})

@app.route('/api/storage/<uid>/<filename>')
def serve_user_file(uid, filename):
    return send_from_directory(os.path.join(STORAGE_DIR, uid), filename)

# --- API: 미디어 제작 및 엑스트랙터 ---
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except: return False

@app.route('/api/system/check_ffmpeg')
def api_check_ffmpeg():
    installed = check_ffmpeg()
    return jsonify({"success": True, "installed": installed, "msg": "FFmpeg 감지됨" if installed else "FFmpeg 미설치 (고화질 제한)"})

@app.route('/api/maker/search', methods=['POST'])
def maker_search():
    data = request.json
    platform, query = data.get('platform'), data.get('query')
    prefix = 'scsearch5:' if platform == 'soundcloud' else 'ytsearch5:'
    opts = {'extract_flat': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(f"{prefix}{query}", download=False)
            results = []
            for e in res.get('entries', []):
                thumb = e.get('thumbnails', [{}])[-1].get('url', '') if e.get('thumbnails') else ''
                results.append({"title": e.get('title'), "url": e.get('url'), "thumbnail": thumb})
            return jsonify({"success": True, "results": results})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/api/maker/extract', methods=['POST'])
def maker_extract():
    data = request.json
    url, is_video = data.get('url'), data.get('type') == 'video'
    has_ffmpeg = check_ffmpeg()
    
    if is_video:
        fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/18' if has_ffmpeg else '18'
    else: fmt = '140/m4a/ba/b'
    
    opts = {
        'format': fmt,
        'outtmpl': os.path.join(STORAGE_DIR, 'maker_temp_%(id)s.%(ext)s'),
        'writethumbnail': True,
        'quiet': True,
        'merge_output_format': 'mp4' if is_video and has_ffmpeg else None,
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = os.path.basename(ydl.prepare_filename(info))
            if is_video and has_ffmpeg and not fname.endswith('.mp4'):
                fname = os.path.splitext(fname)[0] + '.mp4'
            
            base_name = os.path.splitext(fname)[0]
            thumb_file = ""
            for ext in ['.jpg', '.webp', '.png', '.jpeg']:
                if os.path.exists(os.path.join(STORAGE_DIR, base_name + ext)):
                    thumb_file = base_name + ext; break
            
            return jsonify({
                "success": True, "file": fname, "thumb": thumb_file,
                "title": info.get('title'), "artist": info.get('uploader'), "ext": 'mp4' if is_video and has_ffmpeg else info.get('ext')
            })
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/api/maker/save_cloud', methods=['POST'])
def maker_save_cloud():
    import zipfile
    data = request.json
    uid, meta, lrc, tmp_f, tmp_t = data.get('id'), data.get('meta'), data.get('lyrics', ''), data.get('tmpFile'), data.get('tmpThumb')
    
    user_dir = os.path.join(STORAGE_DIR, uid)
    os.makedirs(user_dir, exist_ok=True)
    target_path = os.path.join(user_dir, f"{meta['title']}.mpl")
    
    try:
        with zipfile.ZipFile(target_path, 'w') as z:
            z.write(os.path.join(STORAGE_DIR, tmp_f), f"media.{meta['ext']}")
            if tmp_t: z.write(os.path.join(STORAGE_DIR, tmp_t), "thumb.jpg")
            z.writestr("lyrics.lrc", lrc)
            z.writestr("metadata.json", json.dumps(meta, ensure_ascii=False))
        return jsonify({"success": True})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/api/maker/lyrics', methods=['POST'])
def search_lyrics():
    data = request.json
    title, artist = data.get('query', '').strip(), data.get('artist', '').strip()
    try:
        q = f"{artist} {title}" if artist else title
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(q)}"
        res = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MPL/1.0"}), timeout=5).read())
        for item in res:
            if item.get('syncedLyrics'): 
                return jsonify({"success": True, "lrc": item['syncedLyrics'], "source": "LRCLIB"})
    except: pass
    return jsonify({"success": False, "error": "가사를 찾지 못했습니다."})

# --- API: 플레이리스트 관리 ---
PLAYLISTS_DIR = 'playlists'
def get_pl_path(uid, name):
    d = os.path.join(STORAGE_DIR, uid, PLAYLISTS_DIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name.replace('/', '_').replace('\\', '_') + '.json')

@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    uid = request.args.get('id')
    d = os.path.join(STORAGE_DIR, uid, PLAYLISTS_DIR)
    os.makedirs(d, exist_ok=True)
    pls = []
    for f in sorted(os.listdir(d)):
        if f.endswith('.json'):
            with open(os.path.join(d, f), 'r', encoding='utf-8') as fp: pls.append(json.load(fp))
    return jsonify({"success": True, "playlists": pls})

@app.route('/api/playlist', methods=['POST', 'PUT', 'DELETE'])
def manage_playlist():
    data = request.json
    uid, name = data.get('id'), data.get('name')
    path = get_pl_path(uid, name)
    
    if request.method == 'POST':
        if os.path.exists(path): return jsonify({"success": False, "error": "이미 존재함"})
        with open(path, 'w', encoding='utf-8') as f: json.dump({"name": name, "tracks": []}, f, ensure_ascii=False)
    elif request.method == 'PUT':
        if not os.path.exists(path): return jsonify({"success": False, "error": "없음"})
        with open(path, 'w', encoding='utf-8') as f: json.dump({"name": name, "tracks": data.get('tracks', [])}, f, ensure_ascii=False)
    elif request.method == 'DELETE':
        if os.path.exists(path): os.remove(path)
    return jsonify({"success": True})

# --- API: 원격 관리 및 업데이트 ---
@app.route('/api/remote/shell', methods=['POST'])
def remote_shell():
    cmd = request.json.get('cmd')
    try: return jsonify({"success": True, "output": os.popen(cmd).read()})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/api/system/emergency_update', methods=['POST'])
def emergency_update_v2():
    # 이 엔드포인트는 Cloudflare 터널(3000포트)을 통해 코드를 즉시 주입합니다.
    # ota_manager.py가 감시 중이므로, 파일 쓰기 후 종료하면 자동 재부팅됩니다.
    data = request.json
    try:
        if 'serverPy' in data:
            with open(os.path.join(BASE_DIR, 'server.py'), 'w', encoding='utf-8') as f:
                f.write(data['serverPy'])
        if 'indexHtml' in data:
            with open(os.path.join(PUBLIC_DIR, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(data['indexHtml'])
        
        # 3초 뒤 종료하여 ota_manager가 재시작하게 함
        def reboot():
            time.sleep(2)
            print("🔄 [시스템] 업데이트 반영을 위해 서버를 재부팅합니다...")
            os._exit(0)
        
        threading.Thread(target=reboot).start()
        return jsonify({"success": True, "msg": "업데이트 수신 완료. 재부팅 중..."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/system/update_file', methods=['POST'])
def system_update():
    data = request.json
    target = os.path.join(PUBLIC_DIR, data.get('filename'))
    with open(target, 'w', encoding='utf-8') as f: f.write(data.get('content'))
    return jsonify({"success": True})

@app.route('/api/status')
def status():
    return jsonify({"success": True, "msg": "MPL Cloud Server (Python Native) Online"})

if __name__ == '__main__':
    print("🚀 MPL Python Native Backend 가동 (Port: 3000)")
    app.run(host='0.0.0.0', port=3000)
