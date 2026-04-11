import os
import time
import subprocess
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# --- [정보 입력] 사용자님의 Supabase 정보를 여기에 넣으세요 ---
SUPABASE_URL = "https://rwmifnnqlbljomwayjzm.supabase.co"
SUPABASE_KEY = " 여기에_사용자님의_Anon_Key를_넣으세요 "
# --------------------------------------------------------

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query')
    source = data.get('source', 'yt')
    
    try:
        search_query = f"ytsearch5:{query}" if source == 'yt' else f"scsearch5:{query}"
        if query.startswith('http'): search_query = query
        
        ydl_opts = {'quiet': True, 'skip_download': True, 'extract_flat': True}
        with subprocess.Popen(['python3', '-m', 'yt_dlp', '--dump-single-json', '--flat-playlist', search_query], 
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as p:
            stdout, _ = p.communicate()
            res = json.loads(stdout)
            
            output = []
            entries = res.get('entries', [res])
            for entry in entries:
                output.append({
                    "id": entry.get('id'),
                    "url": entry.get('url') or entry.get('webpage_url'),
                    "title": entry.get('title'),
                    "thumbnail": entry.get('thumbnail'),
                    "uploader": entry.get('uploader')
                })
            return jsonify({"success": True, "results": output})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.json
    target_url = data.get('url')
    mode = data.get('mode', 'music')
    uid = data.get('uid', 'admin')

    try:
        print(f"🚀 추출 시작: {target_url}")
        timestamp = int(time.time())
        
        # 1. 메타데이터 fetch
        info_cmd = ['python3', '-m', 'yt_dlp', '--dump-single-json', '--flat-playlist', target_url]
        info_res = subprocess.run(info_cmd, capture_output=True, text=True)
        metadata = json.loads(info_res.stdout)
        title = metadata.get('title', 'Unknown')
        
        clean_title = "".join(x for x in title if x.isalnum() or x in " -_").strip()
        ext = 'mp3' if mode in ['music', 'mpl'] else 'mp4'
        filename = f"{clean_title}_{timestamp}.{ext}"
        
        # 2. 다운로드 및 태깅 (무거울 수 있어 백그라운드 처리 권장되나 일단 직접 실행)
        dl_cmd = ['python3', '-m', 'yt_dlp', '--add-metadata', '--embed-thumbnail']
        if mode in ['music', 'mpl']:
            dl_cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
        else:
            dl_cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]']
        
        dl_cmd += ['-o', filename, target_url]
        subprocess.run(dl_cmd, check=True)

        # 3. Supabase 업로드
        print(f"⬆️ 업로드 중: {filename}")
        with open(filename, 'rb') as f:
            supabase.storage.from_('media').upload(
                path=f"{uid}/{filename}",
                file=f,
                file_options={"content-type": "audio/mpeg" if ext == 'mp3' else "video/mp4"}
            )
        
        p_url = supabase.storage.from_('media').get_public_url(f"{uid}/{filename}")

        # 4. DB 기록
        supabase.table('media_files').insert({
            "uid": uid, "filename": filename, "url": p_url, "type": mode
        }).execute()

        os.remove(filename)
        return jsonify({"success": True, "msg": "추출 완료!"})

    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
