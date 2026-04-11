import os
import json
import requests
from flask import Flask, request, jsonify

# Vercel Serverless Function (Python)
def handler(request):
    if request.method != 'POST':
        return jsonify({"success": False, "msg": "Method not allowed"}), 405
        
    data = request.json
    url = data.get('url')
    mode = data.get('mode', 'music')
    uid = data.get('uid', 'public')
    
    # GitHub Settings
    GH_TOKEN = os.environ.get('GH_TOKEN') # Vercel Env Var
    REPO_OWNER = "Cheesenham" # 사용자님의 깃허브 ID로 확인됨
    REPO_NAME = "tunify"
    
    if not GH_TOKEN:
        return jsonify({"success": False, "msg": "GH_TOKEN is not configured on Vercel."}), 500

    # Trigger GitHub Action
    gh_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/dispatches"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "event_type": "extract_request",
        "client_payload": {
            "url": url,
            "mode": mode,
            "uid": uid
        }
    }
    
    res = requests.post(gh_url, headers=headers, json=payload)
    
    if res.status_code == 204:
        return jsonify({"success": True, "msg": "GitHub 클라우드 워커 호출 성공! 1~2분 뒤 Supabase에서 확인하세요."})
    else:
        return jsonify({"success": False, "msg": f"GitHub 호출 실패: {res.text}"}), res.status_code
