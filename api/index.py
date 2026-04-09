import os
from flask import Flask, request, jsonify, send_from_directory
import json
import yt_dlp
import syncedlyrics

app = Flask(__name__)

# Vercel은 /tmp 폴더만 쓰기 가능
STORAGE_DIR = '/tmp/mpl_storage'
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

@app.route('/api/status')
def status():
    return jsonify({"msg": "funclass Vercel API is running", "storage": STORAGE_DIR})

@app.route('/api/maker/search', methods=['POST'])
def maker_search():
    data = request.json
    query = data.get('query')
    platform = data.get('platform', 'youtube')
    
    results = []
    if platform == 'youtube':
        search_url = f"ytsearch10:{query}"
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(search_url, download=False)
            for entry in info.get('entries', []):
                results.append({
                    "title": entry.get('title'),
                    "url": entry.get('webpage_url'),
                    "thumbnail": entry.get('thumbnail'),
                    "duration": entry.get('duration')
                })
    return jsonify({"results": results})

@app.route('/api/maker/extract', methods=['POST'])
def maker_extract():
    data = request.json
    url = data.get('url')
    is_video = data.get('type') == 'video'
    
    # Vercel은 ffmpeg가 없으므로 무조건 단일파일(18)
    fmt = '18/best[ext=mp4]' if is_video else '140/m4a/ba/b'
    
    opts = {
        'format': fmt,
        'outtmpl': os.path.join(STORAGE_DIR, 'maker_temp_%(id)s.%(ext)s'),
        'writethumbnail': True,
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = os.path.basename(ydl.prepare_filename(info))
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
                "ext": info.get('ext')
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/maker/temp/<path:filename>')
def serve_temp(filename):
    return send_from_directory(STORAGE_DIR, filename)

@app.route('/api/maker/lyrics', methods=['POST'])
def maker_lyrics():
    data = request.json
    try:
        lrc = syncedlyrics.search(data.get('query'))
        return jsonify({"success": True, "lrc": lrc})
    except:
        return jsonify({"success": False, "msg": "No lyrics found"})

# Vercel용 핸들러
def handler(event, context):
    return app(event, context)
