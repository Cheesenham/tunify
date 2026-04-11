import os
import json
import yt_dlp
from flask import Flask, request, jsonify

# Vercel API: Search YouTube/SoundCloud
def handler(request):
    if request.method != 'POST':
        return jsonify({"success": False, "msg": "Method not allowed"}), 405
        
    data = request.json
    query = data.get('query')
    source = data.get('source', 'yt') # 'yt' or 'sc'
    
    if not query:
        return jsonify({"success": False, "msg": "검색어를 입력하세요."})

    try:
        # yt-dlp search logic
        search_query = f"ytsearch5:{query}" if source == 'yt' else f"scsearch5:{query}"
        
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': True,
            'force_generic_extractor': True if source == 'sc' else False
        }
        
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
                    "duration": entry.get('duration'),
                    "uploader": entry.get('uploader')
                })
                
            return jsonify({"success": True, "results": output})
            
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500
