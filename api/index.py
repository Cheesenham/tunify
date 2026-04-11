import os
import json
import yt_dlp
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# GitHub Settings (for extraction trigger)
GH_TOKEN = os.environ.get('GH_TOKEN')
REPO_OWNER = "Cheesenham"
REPO_NAME = "tunify"

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query')
    source = data.get('source', 'yt')
    
    if not query:
        return jsonify({"success": False, "msg": "검색어를 입력하세요."})

    try:
        search_query = f"ytsearch5:{query}" if source == 'yt' else f"scsearch5:{query}"
        ydl_opts = {'quiet': True, 'skip_download': True, 'extract_flat': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(search_query, download=False)
            entries = results.get('entries', [])
            output = []
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
    if not GH_TOKEN:
        return jsonify({"success": False, "msg": "GH_TOKEN 설정이 필요합니다."}), 500

    gh_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/dispatches"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "event_type": "extract_request",
        "client_payload": data
    }
    res = requests.post(gh_url, headers=headers, json=payload)
    if res.status_code == 204:
        return jsonify({"success": True, "msg": "Cloud Worker 호출 성공!"})
    return jsonify({"success": False, "msg": f"GitHub 호출 실패: {res.text}"}), res.status_code

# Vercel entry point
def handler(request):
    return app(request)

if __name__ == "__main__":
    app.run(debug=True)
