import os
import json
import time
import threading
import subprocess
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, 'mpl_storage')
os.makedirs(STORAGE_DIR, exist_ok=True)

# yt-dlp 경로 자동 탐색
import shutil
YTDLP = shutil.which('yt-dlp') or '/home/lee/.local/bin/yt-dlp'

# 작업 큐 (job_id → {title, progress, status, thumbnail})
jobs = {}

def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

# --- 상태 확인 ---
@app.after_request
def skip_ngrok_warning(response):
    response.headers['ngrok-skip-browser-warning'] = 'true'
    return response

@app.route('/api/status')
def status():
    return jsonify({"success": True, "msg": "MPL Pi Server Online", "ffmpeg": check_ffmpeg()})

# --- 검색 ---
@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query', '').strip()
    platform = data.get('platform', 'yt')

    if not query:
        return jsonify({"success": False, "msg": "검색어가 없습니다."})
    try:
        if query.startswith('http'):
            search_query = query
        elif platform == 'sc':
            search_query = f"scsearch8:{query}"
        else:
            search_query = f"ytsearch8:{query}"

        cmd = [YTDLP, '--dump-single-json', '--flat-playlist', '--no-warnings', search_query]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        res = json.loads(result.stdout)

        entries = res.get('entries', [res])
        output = []
        for e in entries:
            if not e:
                continue
            output.append({
                "id": e.get('id'),
                "url": e.get('url') or e.get('webpage_url'),
                "title": e.get('title', 'Unknown'),
                "thumbnail": e.get('thumbnail') or (e.get('thumbnails') or [{}])[-1].get('url', ''),
                "uploader": e.get('uploader') or e.get('channel', ''),
                "is_playlist": e.get('_type') == 'playlist'
            })
        return jsonify({"success": True, "results": output})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# --- 가사 검색 ---
@app.route('/api/lyrics/search', methods=['POST'])
def lyrics_search():
    data = request.json
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"success": False, "msg": "검색어가 없습니다."})
    try:
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MPL/1.0"})
        res = json.loads(urllib.request.urlopen(req, timeout=8).read())
        for item in res:
            synced = item.get('syncedLyrics')
            if synced:
                lyrics = []
                for line in synced.splitlines():
                    line = line.strip()
                    if not line or not line.startswith('['):
                        continue
                    try:
                        bracket_end = line.index(']')
                        time_str = line[1:bracket_end]
                        text = line[bracket_end + 1:].strip()
                        if ':' in time_str:
                            parts = time_str.split(':')
                            seconds = float(parts[0]) * 60 + float(parts[1])
                            lyrics.append({"time": round(seconds, 2), "text": text})
                    except:
                        continue
                return jsonify({"success": True, "lyrics": lyrics})
        return jsonify({"success": False, "msg": "싱크 가사를 찾지 못했습니다."})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# --- 추출 + 로컬 저장 ---
_pl_sem = threading.Semaphore(128)

def _run_single(url, job_id, mode, uid, artist, selected_lyrics, use_sem=False):
    ctx = _pl_sem if use_sem else __import__('contextlib').nullcontext()
    with ctx:
        try:
            timestamp = int(time.time())
            ext = 'mp3' if mode == 'music' else 'mp4'
            user_dir = os.path.join(STORAGE_DIR, uid)
            os.makedirs(user_dir, exist_ok=True)
            tmp_path = os.path.join(user_dir, f"mpl_{timestamp}.{ext}")

            jobs[job_id].update({"progress": 10, "status": "정보 가져오는 중..."})
            meta_cmd = [YTDLP, '--dump-single-json', '--no-playlist', '--no-warnings', url]
            meta_res = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=30)
            metadata = json.loads(meta_res.stdout)
            title = metadata.get('title', 'Unknown')
            thumbnail = metadata.get('thumbnail', '') or (metadata.get('thumbnails') or [{}])[-1].get('url', '')
            uploader = metadata.get('uploader') or metadata.get('channel', '')
            jobs[job_id].update({"title": title, "thumbnail": thumbnail, "progress": 20, "status": "다운로드 중..."})

            dl_cmd = [YTDLP, '--no-warnings', '--no-playlist', '-o', tmp_path]
            if mode == 'music':
                dl_cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
                if check_ffmpeg():
                    dl_cmd += ['--embed-thumbnail', '--add-metadata']
            else:
                if check_ffmpeg():
                    dl_cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]']
                else:
                    dl_cmd += ['-f', 'best[ext=mp4]']
            dl_cmd.append(url)
            subprocess.run(dl_cmd, check=True, timeout=300)
            jobs[job_id].update({"progress": 80, "status": "저장 중..."})

            filename = os.path.basename(tmp_path)
            lrc_filename = None
            lyrics_data = selected_lyrics or []
            if lyrics_data:
                lrc_filename = f"mpl_{timestamp}.json"
                with open(os.path.join(user_dir, lrc_filename), 'w', encoding='utf-8') as f:
                    json.dump({"title": title, "artist": artist or uploader, "synced_lyrics": lyrics_data}, f, ensure_ascii=False)

            db_path = os.path.join(STORAGE_DIR, 'db.json')
            db = []
            if os.path.exists(db_path):
                with open(db_path, 'r', encoding='utf-8') as f:
                    db = json.load(f)
            db.append({"id": timestamp, "uid": uid, "filename": title, "file": filename,
                        "lrc_file": lrc_filename, "thumbnail": thumbnail,
                        "artist": artist or uploader, "type": mode, "created_at": timestamp})
            with open(db_path, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)

            jobs[job_id].update({"progress": 100, "status": "완료 ✓"})
            print(f"✅ 완료: {title}")
        except Exception as e:
            jobs[job_id].update({"progress": 0, "status": f"실패: {str(e)[:60]}", "error": str(e)})
            print(f"❌ 추출 실패: {e}")

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.json
    url = data.get('url')
    mode = data.get('mode', 'music')
    uid = data.get('uid', 'admin')
    artist = data.get('artist', '')
    selected_lyrics = data.get('selected_lyrics')

    if not url:
        return jsonify({"success": False, "msg": "URL이 없습니다."})

    # 플레이리스트 감지
    try:
        detect_res = subprocess.run(
            [YTDLP, '--flat-playlist', '--dump-single-json', '--no-warnings', url],
            capture_output=True, text=True, timeout=20
        )
        meta = json.loads(detect_res.stdout)
        entries = [e for e in meta.get('entries', []) if e]
    except:
        meta = {}
        entries = []

    if entries:
        job_ids = []
        for i, entry in enumerate(entries):
            entry_url = entry.get('url') or entry.get('webpage_url') or ''
            if not entry_url.startswith('http'):
                continue
            jid = str(int(time.time() * 1000) + i)
            jobs[jid] = {"title": entry.get('title', f'Track {i+1}'), "progress": 0,
                         "status": "대기 중", "thumbnail": entry.get('thumbnail', '') or '', "error": None}
            threading.Thread(target=_run_single, args=(entry_url, jid, mode, uid, artist, None, True), daemon=True).start()
            job_ids.append(jid)
        return jsonify({"success": True, "job_ids": job_ids, "count": len(job_ids),
                        "msg": f"플레이리스트 {len(job_ids)}곡 추출 시작"})

    # 단일 트랙
    job_id = str(int(time.time() * 1000))
    jobs[job_id] = {"title": url, "progress": 0, "status": "대기 중", "thumbnail": "", "error": None}
    threading.Thread(target=_run_single, args=(url, job_id, mode, uid, artist, selected_lyrics), daemon=True).start()
    return jsonify({"success": True, "job_id": job_id, "msg": "추출 시작됨."})


# --- 작업 큐 조회 ---
@app.route('/api/jobs')
def get_jobs():
    return jsonify({"success": True, "jobs": jobs})

# --- 파일 목록 ---
@app.route('/api/files')
def get_files():
    db_path = os.path.join(STORAGE_DIR, 'db.json')
    if not os.path.exists(db_path):
        return jsonify({"success": True, "files": []})
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    for item in db:
        item['path'] = f"/api/media/{item['uid']}/{item['file']}"
        item['lrc_path'] = f"/api/media/{item['uid']}/{item['lrc_file']}" if item.get('lrc_file') else None
    return jsonify({"success": True, "files": sorted(db, key=lambda x: -x['created_at'])})

# --- 파일 서빙 ---
@app.route('/api/media/<uid>/<filename>')
def serve_file(uid, filename):
    return send_from_directory(os.path.join(STORAGE_DIR, uid), filename)

# --- 가사 싱크 저장 ---
@app.route('/api/edit', methods=['POST'])
def edit_lyrics():
    data = request.json
    record_id = data.get('id')
    title = data.get('title', '')
    artist = data.get('artist', '')
    lyrics = data.get('lyrics', [])

    db_path = os.path.join(STORAGE_DIR, 'db.json')
    if not os.path.exists(db_path):
        return jsonify({"success": False, "msg": "DB 없음"})

    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)

    for item in db:
        if item['id'] == record_id:
            uid = item['uid']
            if not item.get('lrc_file'):
                item['lrc_file'] = f"mpl_{record_id}.json"
            lrc_path = os.path.join(STORAGE_DIR, uid, item['lrc_file'])
            with open(lrc_path, 'w', encoding='utf-8') as f:
                json.dump({"title": title, "artist": artist, "synced_lyrics": lyrics}, f, ensure_ascii=False)
            break

    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True})

# --- 플레이리스트 ---
@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    uid = request.args.get('uid', 'admin')
    pl_path = os.path.join(STORAGE_DIR, uid, 'playlists.json')
    if not os.path.exists(pl_path):
        return jsonify({"success": True, "playlists": []})
    with open(pl_path, 'r', encoding='utf-8') as f:
        return jsonify({"success": True, "playlists": json.load(f)})

@app.route('/api/playlists', methods=['POST'])
def create_playlist():
    data = request.json
    uid = data.get('uid', 'admin')
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"success": False})
    pl_path = os.path.join(STORAGE_DIR, uid, 'playlists.json')
    os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
    playlists = []
    if os.path.exists(pl_path):
        with open(pl_path, 'r', encoding='utf-8') as f:
            playlists = json.load(f)
    playlists.append({"id": int(time.time()), "name": name, "items": []})
    with open(pl_path, 'w', encoding='utf-8') as f:
        json.dump(playlists, f, ensure_ascii=False)
    return jsonify({"success": True})

@app.route('/api/playlists/add', methods=['POST'])
def add_to_playlist():
    data = request.json
    uid = data.get('uid', 'admin')
    pl_id = data.get('playlist_id')
    file_id = data.get('file_id')
    pl_path = os.path.join(STORAGE_DIR, uid, 'playlists.json')
    if not os.path.exists(pl_path):
        return jsonify({"success": False})
    with open(pl_path, 'r', encoding='utf-8') as f:
        playlists = json.load(f)
    for pl in playlists:
        if pl['id'] == pl_id:
            if file_id not in pl['items']:
                pl['items'].append(file_id)
            break
    with open(pl_path, 'w', encoding='utf-8') as f:
        json.dump(playlists, f, ensure_ascii=False)
    return jsonify({"success": True})

if __name__ == '__main__':
    print("🚀 MPL Server 시작 (Port: 5000)")
    app.run(host='0.0.0.0', port=5000, debug=False)
