import os
import json
import yt_dlp
import requests

# Final Pure Handler to avoid Flask routing issues on Vercel
def handler(request):
    path = request.path
    method = request.method
    
    # 1. Routing logic inside handler
    if path.endswith('/search') and method == 'POST':
        return search(request)
    elif path.endswith('/extract') and method == 'POST':
        return extract(request)
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"success": False, "msg": f"Route {path} not found"}),
            "headers": {"Content-Type": "application/json"}
        }

def search(request):
    try:
        data = json.loads(request.body)
        query = data.get('query')
        source = data.get('source', 'yt')
        
        if not query:
            return {"statusCode": 400, "body": json.dumps({"success": False, "msg": "No query"})}

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
            
            return {
                "statusCode": 200,
                "body": json.dumps({"success": True, "results": output}),
                "headers": {"Content-Type": "application/json"}
            }
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"success": False, "msg": str(e)})}

def extract(request):
    try:
        data = json.loads(request.body)
        GH_TOKEN = os.environ.get('GH_TOKEN')
        if not GH_TOKEN:
            return {"statusCode": 500, "body": json.dumps({"success": False, "msg": "GH_TOKEN missing"})}

        gh_url = f"https://api.github.com/repos/Cheesenham/tunify/dispatches"
        headers = {
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "event_type": "extract_request",
            "client_payload": data
        }
        res = requests.post(gh_url, headers=headers, json=payload)
        return {"statusCode": 200, "body": json.dumps({"success": True, "msg": "Sent to GitHub"})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"success": False, "msg": str(e)})}
