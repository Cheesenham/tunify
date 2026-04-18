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

import re as _re
def _parse_lrc(lrc_str):
    lines = []
    for line in lrc_str.splitlines():
        m = _re.match(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)', line.strip())
        if m:
            mins, secs, text = m.groups()
            lines.append({"time": round(int(mins)*60 + float(secs), 2), "text": text.strip()})
    return lines

def _auto_fetch_lyrics(title, artist=''):
    try:
        q = urllib.parse.quote(f"{artist} {title}".strip())
        req = urllib.request.Request(f"https://lrclib.net/api/search?q={q}",
                                     headers={'User-Agent': 'Tunify/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())
        for item in results:
            if item.get('syncedLyrics'):
                return _parse_lrc(item['syncedLyrics'])
    except:
        pass
    return []

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

        playlist_title = res.get('title') or res.get('uploader') or ''
        is_url = query.startswith('http')
        entries = res.get('entries', [res])
        output = []
        for e in entries:
            if not e:
                continue
            url = e.get('url') or e.get('webpage_url') or ''
            title = e.get('title') or e.get('track')
            if not title and url:
                slug = url.rstrip('/').split('/')[-1]
                title = slug.replace('-', ' ').title()
            thumbnail = (e.get('thumbnail') or
                         (e.get('thumbnails') or [{}])[-1].get('url', '') or
                         e.get('artwork_url', ''))
            output.append({
                "id": e.get('id'),
                "url": url,
                "title": title or 'Unknown',
                "thumbnail": thumbnail,
                "uploader": e.get('uploader') or e.get('channel', ''),
                "is_playlist": e.get('_type') == 'playlist'
            })
        return jsonify({"success": True, "results": output,
                        "playlist_title": playlist_title if is_url and res.get('entries') else ""})
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
        req = urllib.request.Request(url, headers={"User-Agent": "Tunify/1.0"})
        res = json.loads(urllib.request.urlopen(req, timeout=8).read())
        results = []
        for item in res:
            synced = item.get('syncedLyrics')
            if not synced:
                continue
            parsed = _parse_lrc(synced)
            if parsed:
                results.append({
                    "title": item.get('trackName', ''),
                    "artist": item.get('artistName', ''),
                    "album": item.get('albumName', ''),
                    "duration": item.get('duration', 0),
                    "lyrics": parsed
                })
            if len(results) >= 8:
                break
        if results:
            return jsonify({"success": True, "results": results})
        return jsonify({"success": False, "msg": "싱크 가사를 찾지 못했습니다."})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

# --- 추출 + 로컬 저장 ---
_pl_sem = threading.Semaphore(128)

def _run_single(url, job_id, mode, uid, artist, selected_lyrics, use_sem=False, auto_lyrics=False):
    ctx = _pl_sem if use_sem else __import__('contextlib').nullcontext()
    with ctx:
        try:
            import glob as _glob
            file_id = int(job_id)
            user_dir = os.path.join(STORAGE_DIR, uid)
            os.makedirs(user_dir, exist_ok=True)
            tmp_base = os.path.join(user_dir, f"mpl_{file_id}")

            jobs[job_id].update({"progress": 10, "status": "다운로드 중..."})

            # 다운로드 + --print로 title/uploader/id 캡처 (thumbnail은 id로 구성)
            dl_cmd = [YTDLP, '--no-warnings',
                      '--print', '%(title)s\t%(uploader)s\t%(id)s',
                      '-o', tmp_base + '.%(ext)s']
            if mode == 'music':
                dl_cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
                if check_ffmpeg():
                    dl_cmd += ['--embed-thumbnail', '--add-metadata']
            else:
                dl_cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]' if check_ffmpeg() else 'best[ext=mp4]']
            dl_cmd.append(url)

            res = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                err = (res.stderr.strip().split('\n') or [''])[-1]
                raise Exception(err[:200])

            # --print 출력 파싱
            meta_line = res.stdout.strip().split('\n')[0] if res.stdout.strip() else ''
            parts = [p.strip() for p in meta_line.split('\t')]
            def _v(i): return parts[i] if len(parts) > i and parts[i] not in ('', 'NA', 'None') else ''
            title    = _v(0) or jobs[job_id].get('title') or 'Unknown'
            uploader = _v(1)
            vid_id   = _v(2)
            # YouTube 썸네일 URL 구성
            thumbnail = (f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg"
                         if vid_id and 'youtube' not in url and 'youtu.be' not in url
                         else f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id else '')
            jobs[job_id].update({"title": title, "thumbnail": thumbnail, "progress": 85, "status": "저장 중..."})

            # 오디오 파일 탐색 (audio 우선, 점(.)이 아닌 것도 포함)
            AUDIO_EXTS = {'.mp3', '.m4a', '.ogg', '.opus', '.flac', '.wav', '.aac'}
            VIDEO_EXTS = {'.mp4', '.mkv', '.webm'}
            found = _glob.glob(tmp_base + '*')  # tmp_base + '.*' 대신 '*' 로 더 넓게
            found = [f for f in found if not f.endswith('.part') and not f.endswith('.json')]
            audio = [f for f in found if os.path.splitext(f)[1].lower() in AUDIO_EXTS]
            video = [f for f in found if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
            picked = audio[0] if audio else (video[0] if video else None)
            if not picked:
                raise Exception(f"파일 없음 (found: {[os.path.basename(f) for f in _glob.glob(tmp_base+'*')]})")
            filename = os.path.basename(picked)

            # 가사
            lrc_filename = None
            lyrics_data = selected_lyrics or []
            if not lyrics_data and auto_lyrics:
                jobs[job_id].update({"status": "가사 검색 중..."})
                lyrics_data = _auto_fetch_lyrics(title, artist or uploader)
            if lyrics_data:
                lrc_filename = f"mpl_{file_id}.json"
                with open(os.path.join(user_dir, lrc_filename), 'w', encoding='utf-8') as f:
                    json.dump({"title": title, "artist": artist or uploader,
                               "synced_lyrics": lyrics_data}, f, ensure_ascii=False)

            # DB 저장
            db_path = os.path.join(STORAGE_DIR, 'db.json')
            db = []
            if os.path.exists(db_path):
                with open(db_path, 'r', encoding='utf-8') as f:
                    db = json.load(f)
            db.append({"id": file_id, "uid": uid, "filename": title, "file": filename,
                       "lrc_file": lrc_filename, "thumbnail": thumbnail,
                       "artist": artist or uploader, "type": mode, "created_at": file_id})
            with open(db_path, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)

            jobs[job_id].update({"progress": 100, "status": "완료 ✓"})
            print(f"✅ {title}")
        except Exception as e:
            jobs[job_id].update({"progress": 0, "status": f"실패: {str(e)[:80]}", "error": str(e)})
            print(f"❌ {e}")

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.json
    url = data.get('url')
    mode = data.get('mode', 'music')
    uid = data.get('uid', 'admin')
    artist = data.get('artist', '')
    selected_lyrics = data.get('selected_lyrics')
    auto_lyrics = data.get('auto_lyrics', False)

    if not url:
        return jsonify({"success": False, "msg": "URL이 없습니다."})

    # 플레이리스트 감지
    try:
        detect_res = subprocess.run(
            [YTDLP, '--flat-playlist', '--dump-single-json', '--no-warnings', '--yes-playlist', url],
            capture_output=True, text=True, timeout=60
        )
        meta = json.loads(detect_res.stdout)
        entries = [e for e in meta.get('entries', []) if e]
    except:
        meta = {}
        entries = []

    if entries:
        is_sc = 'soundcloud.com' in url
        convert = data.get('convert_sc', False)
        job_ids = []

        # SC 플리 → YT 변환: 제목을 1번 일괄 조회 후 ytsearch URL 생성
        sc_yt_urls = {}  # index → ytsearch URL
        if is_sc and convert:
            try:
                batch = subprocess.run(
                    [YTDLP, '--no-warnings', '--skip-download',
                     '--print', '%(title)s\t%(uploader)s', '--yes-playlist', url],
                    capture_output=True, text=True, timeout=180
                )
                lines = [l.strip() for l in batch.stdout.strip().split('\n') if l.strip()]
                for i, line in enumerate(lines):
                    p = line.split('\t')
                    t = p[0].strip() if p else ''
                    a = p[1].strip() if len(p) > 1 else ''
                    if t and t != 'NA':
                        sc_yt_urls[i] = (f"ytsearch1:{a} {t}".strip(), t, a)
            except Exception as e:
                print(f"SC 일괄 조회 실패: {e}")

        for i, entry in enumerate(entries):
            jid = str(int(time.time() * 1000) + i)

            if is_sc and convert:
                if i not in sc_yt_urls:
                    jobs[jid] = {"title": entry.get('title') or f'Track {i+1}',
                                 "progress": 0, "status": "SC 제목 없음", "thumbnail": "", "error": "SC 제목 조회 실패"}
                    job_ids.append(jid)
                    continue
                yt_url, sc_title, sc_artist = sc_yt_urls[i]
                jobs[jid] = {"title": sc_title, "progress": 0, "status": "대기 중", "thumbnail": "", "error": None}
                threading.Thread(target=_run_single,
                                 kwargs=dict(url=yt_url, job_id=jid, mode=mode, uid=uid,
                                             artist=sc_artist, selected_lyrics=None,
                                             use_sem=True, auto_lyrics=auto_lyrics),
                                 daemon=True).start()
            else:
                track_url = entry.get('webpage_url') or entry.get('url') or ''
                if not track_url.startswith('http'):
                    track_url = url
                title = entry.get('title') or f'Track {i+1}'
                jobs[jid] = {"title": title, "progress": 0, "status": "대기 중",
                             "thumbnail": entry.get('thumbnail', '') or '', "error": None}
                threading.Thread(target=_run_single,
                                 kwargs=dict(url=track_url, job_id=jid, mode=mode, uid=uid,
                                             artist=artist, selected_lyrics=None,
                                             use_sem=True, auto_lyrics=auto_lyrics),
                                 daemon=True).start()
            job_ids.append(jid)

        return jsonify({"success": True, "job_ids": job_ids, "count": len(job_ids),
                        "msg": f"{'SC→YT 변환' if is_sc and convert else '플레이리스트'} {len(job_ids)}곡 추출 시작"})

    # 단일 트랙
    job_id = str(int(time.time() * 1000))
    jobs[job_id] = {"title": url, "progress": 0, "status": "대기 중", "thumbnail": "", "error": None}
    threading.Thread(target=_run_single,
                     kwargs=dict(url=url, job_id=job_id, mode=mode, uid=uid,
                                 artist=artist, selected_lyrics=selected_lyrics,
                                 auto_lyrics=auto_lyrics),
                     daemon=True).start()
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

# --- 파일 삭제 ---
@app.route('/api/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    db_path = os.path.join(STORAGE_DIR, 'db.json')
    if not os.path.exists(db_path):
        return jsonify({"success": False, "msg": "DB 없음"})
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    item = next((x for x in db if str(x['id']) == file_id), None)
    if not item:
        return jsonify({"success": False, "msg": "항목 없음"})
    uid = item['uid']
    for fname in [item.get('file'), item.get('lrc_file')]:
        if fname:
            p = os.path.join(STORAGE_DIR, uid, fname)
            if os.path.exists(p):
                os.remove(p)
    db = [x for x in db if str(x['id']) != file_id]
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
