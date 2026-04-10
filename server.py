import os
import json
import time
import shutil
import glob
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp
import urllib.request
import urllib.parse

app = Flask(__name__, static_folder='public')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
STORAGE_DIR = os.path.join(BASE_DIR, 'mpl_storage')

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(PUBLIC_DIR, exist_ok=True)

USERS_DB = os.path.join(STORAGE_DIR, 'users.json')

def load_users():
    if not os.path.exists(USERS_DB):
        # Default admin account
        with open(USERS_DB, 'w', encoding='utf-8') as f:
            json.dump({"admin": {"pw": "admin123", "role": "admin"}}, f)
    with open(USERS_DB, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {"admin": {"pw": "admin123", "role": "admin"}}

def save_users(users):
    with open(USERS_DB, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
def admin_users():
    users = load_users()
    data = request.json if request.is_json else {}
    if request.method == 'GET':
        return jsonify({"success": True, "users": users})
    elif request.method == 'POST':
        uid = data.get('id')
        if not uid: return jsonify({"success": False})
        users[uid] = {"pw": data.get('pw', '0000'), "role": "user"}
        save_users(users)
        os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
        return jsonify({"success": True})
    elif request.method == 'DELETE':
        uid = data.get('id')
        if uid in users and uid != 'admin':
            del users[uid]
            save_users(users)
        return jsonify({"success": True})

@app.route('/api/delete_file', methods=['POST'])
def soft_delete_file():
    # 7일 후 완전 삭제를 위한 임시 휴지통 스케줄 (가안)
    data = request.json
    uid = data.get('id', '').strip()
    filename = data.get('filename', '').strip()
    target = os.path.join(STORAGE_DIR, uid, filename)
    trash = os.path.join(STORAGE_DIR, uid, '.trash')
    os.makedirs(trash, exist_ok=True)
    if os.path.exists(target):
        os.rename(target, os.path.join(trash, filename))
    return jsonify({"success": True, "msg": "휴지통으로 이동되었습니다. (7일 후 영구삭제)"})


# 1. 파일 제공 라우트 (절대 경로 보강)
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
    return f"404: {path} 를 찾을 수 없습니다. (현재 경로: {PUBLIC_DIR})", 404

@app.errorhandler(404)
def page_not_found(e):
    # 디버깅을 위해 현재 public 폴더 내의 파일 목록을 출력
    files = os.listdir(PUBLIC_DIR) if os.path.exists(PUBLIC_DIR) else "공개 폴더 없음"
    return f"파일을 찾을 수 없습니다. 현재 사용 가능한 파일들: {files}", 404

@app.route('/api/maker/temp/<path:filename>')
def serve_temp(filename):
    return send_from_directory(STORAGE_DIR, filename)

@app.route('/mpl_storage/<path:path>')
def serve_storage(path):
    return send_from_directory(STORAGE_DIR, path)

# 2. 유저 및 상태 API
@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"success": True, "msg": "MPL Cloud Server (Python Native) is online"})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id', '').strip()
    pw = data.get('pw', '').strip()
    if not uid:
        return jsonify({"success": False, "msg": "아이디를 입력하세요."})
        
    users = load_users()
    if uid not in users:
        return jsonify({"success": False, "msg": "존재하지 않는 계정입니다."})
    
    if users[uid].get('pw') != pw:
        return jsonify({"success": False, "msg": "비밀번호가 일치하지 않습니다."})
        
    os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
    return jsonify({"success": True, "id": uid, "role": users[uid].get('role', 'user')})

@app.route('/api/files', methods=['GET'])
def get_files():
    uid = request.args.get('id', '').strip()
    user_dir = os.path.join(STORAGE_DIR, uid)
    if not os.path.exists(user_dir):
        return jsonify({"success": True, "files": []})
    
    files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f)) and f.endswith(('.mpl', '.mplp'))]
    return jsonify({"success": True, "files": files})

@app.route('/api/rename', methods=['POST'])
def rename_file():
    data = request.json
    uid = data.get('id', '').strip()
    old_name = data.get('oldName', '').strip()
    new_name = data.get('newName', '').strip()
    
    if not new_name.endswith(('.mpl', '.mplp')):
        new_name += '.mpl'
        
    old_path = os.path.join(STORAGE_DIR, uid, old_name)
    new_path = os.path.join(STORAGE_DIR, uid, new_name)
    
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
    return jsonify({"success": True})

@app.route('/api/download/<uid>/<filename>', methods=['GET'])
def download_file(uid, filename):
    return send_from_directory(os.path.join(STORAGE_DIR, uid), filename)

# 3. 제작 및 미디어 추출 API
@app.route('/api/maker/search', methods=['POST'])
def maker_search():
    data = request.json
    platform = data.get('platform')
    query = data.get('query')
    
    prefix = 'scsearch5:' if platform == 'soundcloud' else 'ytsearch5:'
    opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(f"{prefix}{query}", download=False)
            entries = []
            for e in res.get('entries', []):
                thumb = e.get('thumbnails', [{}])[-1].get('url', '') if e.get('thumbnails') else ''
                entries.append({"title": e.get('title', 'Unknown'), "url": e.get('url'), "thumbnail": thumb})
            return jsonify({"success": True, "results": entries})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

import subprocess

# FFmpeg 존재 여부 체크
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

@app.route('/api/system/check_ffmpeg', methods=['GET'])
def api_check_ffmpeg():
    installed = check_ffmpeg()
    return jsonify({
        "success": True, 
        "installed": installed, 
        "msg": "FFmpeg가 설치되어 있습니다." if installed else "FFmpeg가 없습니다. 고화질 영상 추출이 제한될 수 있습니다."
    })

@app.route('/api/maker/extract', methods=['POST'])
def maker_extract():
    data = request.json
    url = data.get('url')
    is_video = data.get('type') == 'video'
    
    # FFmpeg가 있으면 고화질(mp4 합본), 없으면 단일파일(18)
    has_ffmpeg = check_ffmpeg()
    if is_video:
        fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/18' if has_ffmpeg else '18/best[ext=mp4]'
    else:
        fmt = '140/m4a/ba/b'
    
    opts = {
        'format': fmt,
        'outtmpl': os.path.join(STORAGE_DIR, 'maker_temp_%(id)s.%(ext)s'),
        'writethumbnail': True,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4' if is_video and has_ffmpeg else None,
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = os.path.basename(ydl.prepare_filename(info))
            # Merge 시 확장자가 mp4로 고정될 수 있음
            if is_video and has_ffmpeg and not fname.endswith('.mp4'):
                old_fname = fname
                fname = os.path.splitext(fname)[0] + '.mp4'
            
            base_name, _ = os.path.splitext(fname)
            
            thumb_file = ""
            for ext in ['.jpg', '.webp', '.png', '.jpeg']:
                t_path = os.path.join(STORAGE_DIR, base_name + ext)
                if os.path.exists(t_path):
                    thumb_file = base_name + ext
                    break
                    
            return jsonify({
                "success": True, 
                "file": fname, 
                "thumb": thumb_file,
                "title": info.get('title'), 
                "artist": info.get('uploader'), 
                "ext": 'mp4' if is_video and has_ffmpeg else info.get('ext')
            })
    except Exception as e:
        error_msg = str(e)
        if "ffmpeg" in error_msg.lower():
            error_msg = "FFmpeg가 설치되지 않아 영상 병합에 실패했습니다. (pkg install ffmpeg 수행 필요)"
        return jsonify({"success": False, "error": error_msg})


# 8. 서버 사이드 패키징 및 클라우드 즉시 저장 API
@app.route('/api/maker/save_cloud', methods=['POST'])
def maker_save_cloud():
    data = request.json
    uid = data.get('id')
    meta = data.get('meta') # {title, artist, ext, type}
    lrc = data.get('lyrics', '')
    tmp_file = data.get('tmpFile')
    tmp_thumb = data.get('tmpThumb')

    if not uid or not meta:
        return jsonify({"success": False, "error": "Missing data"})

    user_dir = os.path.join(STORAGE_DIR, uid)
    os.makedirs(user_dir, exist_ok=True)

    import zipfile
    target_name = f"{meta['title']}.mpl"
    target_path = os.path.join(user_dir, target_name)

    try:
        with zipfile.ZipFile(target_path, 'w') as z:
            # 미디어 파일 넣기
            z.write(os.path.join(STORAGE_DIR, tmp_file), f"media.{meta['ext']}")
            # 썸네일 넣기
            if tmp_thumb:
                z.write(os.path.join(STORAGE_DIR, tmp_thumb), "thumb.jpg")
            # 가사 및 메타데이터
            z.writestr("lyrics.lrc", lrc)
            z.writestr("metadata.json", json.dumps(meta))
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/maker/lyrics', methods=['POST'])
def maker_lyrics():
    data = request.json
    title = data.get('query', '').strip()
    artist = data.get('artist', '').strip()

    if not title:
        return jsonify({"success": False, "error": "검색어를 입력하세요."})

    # === 소스 1: LRCLIB API (가장 안정적) ===
    try:
        search_q = f"{artist} {title}" if artist else title
        lrclib_url = f"https://lrclib.net/api/search?q={urllib.parse.quote(search_q)}"
        req = urllib.request.Request(lrclib_url, headers={
            "User-Agent": "MPL Pro Cloud/1.0"
        })
        res = urllib.request.urlopen(req, timeout=8)
        results = json.loads(res.read().decode())

        # 싱크 가사가 있는 첫 번째 결과 찾기
        for item in results:
            synced = item.get('syncedLyrics')
            if synced and synced.strip():
                return jsonify({
                    "success": True,
                    "lrc": synced,
                    "source": "LRCLIB",
                    "match": f"{item.get('artistName', '')} - {item.get('trackName', '')}"
                })

        # 싱크 가사 없으면 일반 가사라도 반환
        for item in results:
            plain = item.get('plainLyrics')
            if plain and plain.strip():
                return jsonify({
                    "success": True,
                    "lrc": plain,
                    "source": "LRCLIB (plain)",
                    "match": f"{item.get('artistName', '')} - {item.get('trackName', '')}"
                })
    except Exception as e:
        print(f"[LRCLIB 실패] {e}")

    # === 소스 2: syncedlyrics 라이브러리 (폴백) ===
    try:
        import syncedlyrics
        search_q = f"{artist} {title}" if artist else title
        lrc = syncedlyrics.search(search_q)
        if lrc:
            return jsonify({"success": True, "lrc": lrc, "source": "syncedlyrics"})
    except Exception as e:
        print(f"[syncedlyrics 실패] {e}")

    return jsonify({"success": False, "error": "가사를 찾을 수 없습니다. 다른 검색어를 시도해 주세요."})

# 4. 파일 업로드 API
@app.route('/api/upload', methods=['POST'])
def upload_file():
    target_dir = request.form.get('id', '').strip()
    if not target_dir:
        return jsonify({"success": False, "error": "No User ID"})
        
    full_dir = os.path.join(STORAGE_DIR, target_dir)
    os.makedirs(full_dir, exist_ok=True)
    
    file = request.files.get('mplFile')
    if not file or file.filename == '':
        return jsonify({"success": False, "error": "No file uploaded"})
        
    safe_name = file.filename
    file.save(os.path.join(full_dir, safe_name))
    return jsonify({"success": True})

# 5. 동기화 및 폴더 API
@app.route('/api/sync', methods=['POST'])
def sync_storage():
    data = request.json
    # 단순화를 위해 전체 폴더 목록만 리턴
    tree = {}
    if os.path.exists(STORAGE_DIR):
        for root, _, files in os.walk(STORAGE_DIR):
            rel = os.path.relpath(root, STORAGE_DIR)
            if rel == '.':
                rel = ''
            tree[rel] = [f for f in files if f.endswith('.mpl')]
    return jsonify({"success": True, "tree": tree})

# 6. 원격 명령 실행 (실험적 기능)
@app.route('/api/remote/shell', methods=['POST'])
def remote_shell():
    data = request.json
    cmd = data.get('cmd')
    try:
        if not cmd: return jsonify({"success": False, "error": "No command"})
        result = os.popen(cmd).read()
        return jsonify({"success": True, "output": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# 7. 시스템 파일 직접 강제 주입 API (문지기 우회용)
@app.route('/api/system/update_file', methods=['POST'])
def system_update_file():
    data = request.json
    filename = data.get('filename')
    content = data.get('content')
    if not filename or content is None:
        return jsonify({"success": False, "error": "Invalid Data"})
    
    try:
        target_path = os.path.join(PUBLIC_DIR, filename)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True, "file": filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ===== 플레이리스트 API =====
PLAYLISTS_DIR_NAME = 'playlists'

def get_playlist_dir(uid):
    d = os.path.join(STORAGE_DIR, uid, PLAYLISTS_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d

@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    uid = request.args.get('id', '').strip()
    if not uid:
        return jsonify({"success": False, "error": "No user ID"})
    pl_dir = get_playlist_dir(uid)
    playlists = []
    for f in sorted(os.listdir(pl_dir)):
        if f.endswith('.json'):
            try:
                with open(os.path.join(pl_dir, f), 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    playlists.append(data)
            except:
                pass
    return jsonify({"success": True, "playlists": playlists})

@app.route('/api/playlist', methods=['POST'])
def create_playlist():
    data = request.json
    uid = data.get('id', '').strip()
    name = data.get('name', '').strip()
    if not uid or not name:
        return jsonify({"success": False, "error": "Missing id or name"})
    pl_dir = get_playlist_dir(uid)
    safe_name = name.replace('/', '_').replace('\\', '_')
    pl_path = os.path.join(pl_dir, f"{safe_name}.json")
    if os.path.exists(pl_path):
        return jsonify({"success": False, "error": "이미 존재하는 플레이리스트입니다."})
    pl_data = {"name": name, "tracks": []}
    with open(pl_path, 'w', encoding='utf-8') as fp:
        json.dump(pl_data, fp, ensure_ascii=False)
    return jsonify({"success": True, "playlist": pl_data})

@app.route('/api/playlist', methods=['PUT'])
def update_playlist():
    data = request.json
    uid = data.get('id', '').strip()
    name = data.get('name', '').strip()
    tracks = data.get('tracks')
    if not uid or not name:
        return jsonify({"success": False, "error": "Missing id or name"})
    pl_dir = get_playlist_dir(uid)
    safe_name = name.replace('/', '_').replace('\\', '_')
    pl_path = os.path.join(pl_dir, f"{safe_name}.json")
    if not os.path.exists(pl_path):
        return jsonify({"success": False, "error": "플레이리스트를 찾을 수 없습니다."})
    with open(pl_path, 'r', encoding='utf-8') as fp:
        pl_data = json.load(fp)
    if tracks is not None:
        pl_data['tracks'] = tracks
    with open(pl_path, 'w', encoding='utf-8') as fp:
        json.dump(pl_data, fp, ensure_ascii=False)
    return jsonify({"success": True, "playlist": pl_data})

@app.route('/api/playlist', methods=['DELETE'])
def delete_playlist():
    data = request.json
    uid = data.get('id', '').strip()
    name = data.get('name', '').strip()
    if not uid or not name:
        return jsonify({"success": False, "error": "Missing id or name"})
    pl_dir = get_playlist_dir(uid)
    safe_name = name.replace('/', '_').replace('\\', '_')
    pl_path = os.path.join(pl_dir, f"{safe_name}.json")
    if os.path.exists(pl_path):
        os.remove(pl_path)
    return jsonify({"success": True})


if __name__ == '__main__':
    print("🚀 파이썬 네이티브 백엔드 구동 (포트: 3000)")
    app.run(host='0.0.0.0', port=3000)
