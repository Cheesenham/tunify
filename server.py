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
USERS_FILE = os.path.join(BASE_DIR, 'db', 'users.json')

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
_pl_sem = threading.Semaphore(6)   # 플레이리스트 최대 동시 6개 (YouTube 레이트리밋 방지)
_db_lock = threading.Lock()
_pljson_lock = threading.Lock()    # playlists.json 동시 쓰기 방지

def _create_playlist_internal(uid, name, pl_id):
    pl_path = os.path.join(STORAGE_DIR, uid, 'playlists.json')
    os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
    with _pljson_lock:
        pls = []
        if os.path.exists(pl_path):
            with open(pl_path, 'r', encoding='utf-8') as f:
                pls = json.load(f)
        pls.append({"id": pl_id, "name": name, "items": []})
        with open(pl_path, 'w', encoding='utf-8') as f:
            json.dump(pls, f, ensure_ascii=False)

def _add_to_playlist_internal(uid, pl_id, file_id):
    pl_path = os.path.join(STORAGE_DIR, uid, 'playlists.json')
    with _pljson_lock:
        if not os.path.exists(pl_path):
            return
        with open(pl_path, 'r', encoding='utf-8') as f:
            pls = json.load(f)
        for pl in pls:
            if pl['id'] == pl_id:
                if file_id not in pl['items']:
                    pl['items'].append(file_id)
                break
        with open(pl_path, 'w', encoding='utf-8') as f:
            json.dump(pls, f, ensure_ascii=False)

def _run_single(url, job_id, mode, uid, artist, selected_lyrics, use_sem=False, auto_lyrics=False, metadata=None, playlist_id=None):
    ctx = _pl_sem if use_sem else __import__('contextlib').nullcontext()
    with ctx:
        try:
            import glob as _glob
            file_id = int(job_id)
            user_dir = os.path.join(STORAGE_DIR, uid)
            os.makedirs(user_dir, exist_ok=True)
            tmp_base = os.path.join(user_dir, f"mpl_{file_id}")

            jobs[job_id].update({"progress": 10, "status": "정보 가져오는 중..."})

            if metadata:
                # flat-playlist에서 이미 받은 메타데이터 → Step 1 생략 (타임아웃/레이트리밋 방지)
                title      = (metadata.get('title') or '').strip()
                uploader   = (metadata.get('uploader') or metadata.get('channel') or '').strip()
                vid_id     = metadata.get('id') or ''
                actual_url = metadata.get('webpage_url') or metadata.get('url') or url
                thumbnail  = (metadata.get('thumbnail') or
                              (f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id else ''))

                # SC flat-playlist는 title이 비어있는 경우가 많음 → Step 1로 fallback
                if not title or title in ('NA', 'None'):
                    try:
                        jobs[job_id].update({"status": "제목 가져오는 중..."})
                        meta_res = subprocess.run(
                            [YTDLP, '--no-warnings', '--skip-download',
                             '--print', '%(title)s\t%(uploader)s', actual_url],
                            capture_output=True, text=True, timeout=45)
                        line = meta_res.stdout.strip().split('\n')[0] if meta_res.stdout.strip() else ''
                        parts = [p.strip() for p in line.split('\t')]
                        if parts and parts[0] not in ('', 'NA', 'None'):
                            title = parts[0]
                        if len(parts) > 1 and parts[1] not in ('', 'NA', 'None') and not uploader:
                            uploader = parts[1]
                    except Exception:
                        pass

                title = title or jobs[job_id].get('title') or 'Unknown'
            else:
                # Step 1: ytsearch 등 메타데이터를 모를 때만 조회
                meta_res = subprocess.run(
                    [YTDLP, '--no-warnings', '--skip-download',
                     '--print', '%(title)s\t%(uploader)s\t%(id)s\t%(webpage_url)s', url],
                    capture_output=True, text=True, timeout=45
                )
                meta_line = meta_res.stdout.strip().split('\n')[0] if meta_res.stdout.strip() else ''
                parts = [p.strip() for p in meta_line.split('\t')]
                def _v(i): return parts[i] if len(parts) > i and parts[i] not in ('', 'NA', 'None') else ''
                title      = _v(0) or jobs[job_id].get('title') or 'Unknown'
                uploader   = _v(1)
                vid_id     = _v(2)
                actual_url = _v(3) or url
                thumbnail  = f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id else ''

            jobs[job_id].update({"title": title, "thumbnail": thumbnail, "progress": 20, "status": "다운로드 중..."})

            # Step 2: 다운로드 (--print 없이, 확정된 URL 사용)
            dl_cmd = [YTDLP, '--no-warnings', '-o', tmp_base + '.%(ext)s']
            if mode == 'music':
                dl_cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
            else:
                dl_cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]' if check_ffmpeg() else 'best[ext=mp4]']
            dl_cmd.append(actual_url)

            res = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                err = (res.stderr.strip().split('\n') or [''])[-1]
                raise Exception(err[:200])
            jobs[job_id].update({"progress": 85, "status": "저장 중..."})

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

            # DB 저장 (락으로 동시 쓰기 방지)
            db_path = os.path.join(STORAGE_DIR, 'db.json')
            with _db_lock:
                db = []
                if os.path.exists(db_path):
                    with open(db_path, 'r', encoding='utf-8') as f:
                        db = json.load(f)
                db.append({"id": file_id, "uid": uid, "filename": title, "file": filename,
                           "lrc_file": lrc_filename, "thumbnail": thumbnail,
                           "artist": artist or uploader, "type": mode, "created_at": file_id,
                           "playlist_id": playlist_id})
                with open(db_path, 'w', encoding='utf-8') as f:
                    json.dump(db, f, ensure_ascii=False, indent=2)

            # 플레이리스트에 자동 추가
            if playlist_id is not None:
                _add_to_playlist_internal(uid, playlist_id, file_id)

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
            capture_output=True, text=True, timeout=120
        )
        meta = json.loads(detect_res.stdout)
        entries = [e for e in meta.get('entries', []) if e]
    except:
        meta = {}
        entries = []

    if entries:
        is_sc = 'soundcloud.com' in url
        is_yt = 'youtube.com' in url or 'youtu.be' in url
        convert = data.get('convert_sc', False)
        job_ids = []

        # 플레이리스트 자동 생성
        pl_id = int(time.time() * 1000)
        pl_title = (meta.get('title') or meta.get('playlist_title') or '').strip() or f'Playlist {pl_id}'
        _create_playlist_internal(uid, pl_title, pl_id)

        # SC→YT 변환 옵션: flat-playlist 제목이 있으면 ytsearch, 없으면 SC 직접 다운로드
        for i, entry in enumerate(entries):
            jid = str(int(time.time() * 1000) + i)

            eid = entry.get('id', '')
            track_url = entry.get('webpage_url') or entry.get('url') or ''
            if not track_url.startswith('http'):
                if eid and is_yt:
                    track_url = f'https://www.youtube.com/watch?v={eid}'
                elif eid and is_sc:
                    track_url = f'https://soundcloud.com/{eid}'
                else:
                    track_url = url

            t = (entry.get('title') or '').strip()
            a = (entry.get('uploader') or entry.get('channel') or '').strip()

            # SC→YT 변환 요청이고 제목이 있으면 YT 검색으로 다운로드
            if is_sc and convert and t and t not in ('NA', 'None'):
                yt_url = f"ytsearch1:{a} {t}".strip()
                jobs[jid] = {"title": t, "progress": 0, "status": "대기 중", "thumbnail": "", "error": None}
                threading.Thread(target=_run_single,
                                 kwargs=dict(url=yt_url, job_id=jid, mode=mode, uid=uid,
                                             artist=a, selected_lyrics=None,
                                             use_sem=True, auto_lyrics=auto_lyrics,
                                             playlist_id=pl_id),
                                 daemon=True).start()
            else:
                # SC 직접 다운로드 (제목 없어도 _run_single에서 Step 1 fallback으로 처리)
                display_title = t or f'Track {i+1}'
                jobs[jid] = {"title": display_title, "progress": 0, "status": "대기 중",
                             "thumbnail": entry.get('thumbnail', '') or '', "error": None}
                threading.Thread(target=_run_single,
                                 kwargs=dict(url=track_url, job_id=jid, mode=mode, uid=uid,
                                             artist=artist or a, selected_lyrics=None,
                                             use_sem=True, auto_lyrics=auto_lyrics,
                                             metadata=entry, playlist_id=pl_id),
                                 daemon=True).start()
            job_ids.append(jid)

        return jsonify({"success": True, "job_ids": job_ids, "count": len(job_ids),
                        "playlist_title": pl_title,
                        "msg": f"플레이리스트 '{pl_title}' {len(job_ids)}곡 추출 시작"})

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
    uid = request.args.get('uid', '').strip()
    db_path = os.path.join(STORAGE_DIR, 'db.json')
    if not os.path.exists(db_path):
        return jsonify({"success": True, "files": []})
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    if uid:
        db = [item for item in db if item.get('uid') == uid]
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
    requester_uid = request.args.get('uid', '').strip()
    db_path = os.path.join(STORAGE_DIR, 'db.json')
    if not os.path.exists(db_path):
        return jsonify({"success": False, "msg": "DB 없음"})
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    item = next((x for x in db if str(x['id']) == file_id), None)
    if not item:
        return jsonify({"success": False, "msg": "항목 없음"})
    if requester_uid and item.get('uid') != requester_uid:
        return jsonify({"success": False, "msg": "권한 없음"}), 403
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

# ─── 앨범 커버 ───────────────────────────────────────────────
@app.route('/api/cover/search', methods=['POST'])
def cover_search():
    data = request.json or {}
    title  = data.get('title', '').strip()
    artist = data.get('artist', '').strip()
    query  = f"{artist} {title}".strip() if artist else title
    if not query:
        return jsonify({'success': False, 'msg': '검색어 없음'})
    try:
        url = (f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}"
               f"&media=music&entity=song&limit=10")
        req = urllib.request.Request(url, headers={'User-Agent': 'Tunify/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read()).get('results', [])
        candidates, seen = [], set()
        for item in results:
            art = item.get('artworkUrl100', '')
            if not art or art in seen:
                continue
            seen.add(art)
            candidates.append({
                'url':    art.replace('100x100bb', '600x600bb'),
                'thumb':  art.replace('100x100bb', '300x300bb'),
                'title':  item.get('trackName', ''),
                'artist': item.get('artistName', ''),
                'album':  item.get('collectionName', ''),
            })
            if len(candidates) >= 3:
                break
        return jsonify({'success': True, 'candidates': candidates})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)})

@app.route('/api/cover/apply', methods=['POST'])
def cover_apply():
    data = request.json or {}
    file_id     = str(data.get('file_id', ''))
    cover_url   = data.get('url', '').strip()
    requester   = data.get('uid', '').strip()
    if not file_id or not cover_url:
        return jsonify({'success': False, 'msg': '파라미터 부족'})
    db_path = os.path.join(STORAGE_DIR, 'db.json')
    with _db_lock:
        if not os.path.exists(db_path):
            return jsonify({'success': False, 'msg': 'DB 없음'})
        with open(db_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
        item = next((x for x in db if str(x['id']) == file_id), None)
        if not item:
            return jsonify({'success': False, 'msg': '항목 없음'})
        if requester and item.get('uid') != requester:
            return jsonify({'success': False, 'msg': '권한 없음'}), 403
        item_uid  = item['uid']
        user_dir  = os.path.join(STORAGE_DIR, item_uid)
        os.makedirs(user_dir, exist_ok=True)
        cover_fn  = f"cover_{file_id}.jpg"
        cover_path = os.path.join(user_dir, cover_fn)
        try:
            req = urllib.request.Request(cover_url, headers={'User-Agent': 'Tunify/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                with open(cover_path, 'wb') as f2:
                    f2.write(r.read())
        except Exception as e:
            return jsonify({'success': False, 'msg': f'이미지 다운로드 실패: {e}'})
        item['thumbnail'] = f"/api/media/{item_uid}/{cover_fn}"
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    return jsonify({'success': True, 'thumbnail': item['thumbnail']})

# ─── 계정 관리 ───────────────────────────────────────────────
_users_lock = threading.Lock()

def _load_users():
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    if not os.path.exists(USERS_FILE):
        default = {"admin": {"pw": "1234", "role": "admin", "nickname": "Admin"}}
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_users(users):
    with _users_lock:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    uid = data.get('uid', '').strip()
    pw = data.get('password', '')
    users = _load_users()
    u = users.get(uid)
    if not u or u.get('pw') != pw:
        return jsonify({'success': False, 'error': '아이디 또는 비밀번호가 틀렸습니다.'}), 401
    return jsonify({'success': True, 'uid': uid,
                    'nickname': u.get('nickname', uid),
                    'role': u.get('role', 'user')})

@app.route('/api/me')
def me():
    uid = request.args.get('uid', '')
    users = _load_users()
    u = users.get(uid)
    if not u:
        return jsonify({'success': False}), 401
    return jsonify({'success': True, 'uid': uid,
                    'nickname': u.get('nickname', uid),
                    'role': u.get('role', 'user')})

@app.route('/api/users', methods=['GET'])
def list_users():
    uid = request.args.get('uid', '')
    users = _load_users()
    if users.get(uid, {}).get('role') != 'admin':
        return jsonify({'error': '권한 없음'}), 403
    return jsonify({'success': True, 'users': [
        {'uid': k, 'nickname': v.get('nickname', k), 'role': v.get('role', 'user')}
        for k, v in users.items()
    ]})

@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.json or {}
    admin_uid = data.get('admin_uid', '')
    users = _load_users()
    if users.get(admin_uid, {}).get('role') != 'admin':
        return jsonify({'error': '권한 없음'}), 403
    new_uid = data.get('uid', '').strip()
    if not new_uid:
        return jsonify({'error': '아이디를 입력하세요.'}), 400
    if new_uid in users:
        return jsonify({'error': '이미 존재하는 아이디입니다.'}), 400
    users[new_uid] = {
        'pw': data.get('password', '1234'),
        'nickname': data.get('nickname', new_uid),
        'role': 'user'
    }
    _save_users(users)
    return jsonify({'success': True})

@app.route('/api/users/<target_uid>', methods=['DELETE'])
def delete_user(target_uid):
    admin_uid = request.args.get('admin_uid', '')
    users = _load_users()
    if users.get(admin_uid, {}).get('role') != 'admin':
        return jsonify({'error': '권한 없음'}), 403
    if target_uid == 'admin':
        return jsonify({'error': 'admin 계정은 삭제할 수 없습니다.'}), 400
    if target_uid not in users:
        return jsonify({'error': '사용자 없음'}), 404
    del users[target_uid]
    _save_users(users)
    return jsonify({'success': True})

@app.route('/api/users/<target_uid>/reset', methods=['POST'])
def reset_password(target_uid):
    data = request.json or {}
    admin_uid = data.get('admin_uid', '')
    users = _load_users()
    if users.get(admin_uid, {}).get('role') != 'admin':
        return jsonify({'error': '권한 없음'}), 403
    if target_uid not in users:
        return jsonify({'error': '사용자 없음'}), 404
    users[target_uid]['pw'] = data.get('password', '1234')
    _save_users(users)
    return jsonify({'success': True})

@app.route('/api/users/<target_uid>/nickname', methods=['POST'])
def update_nickname(target_uid):
    data = request.json or {}
    admin_uid = data.get('admin_uid', '')
    users = _load_users()
    if users.get(admin_uid, {}).get('role') != 'admin':
        return jsonify({'error': '권한 없음'}), 403
    if target_uid not in users:
        return jsonify({'error': '사용자 없음'}), 404
    users[target_uid]['nickname'] = data.get('nickname', target_uid)
    _save_users(users)
    return jsonify({'success': True})

if __name__ == '__main__':
    print("🚀 MPL Server 시작 (Port: 5000)")
    app.run(host='0.0.0.0', port=5000, debug=False)
