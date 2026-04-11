import os
import time
import subprocess
import json
from supabase import create_client, Client

# --- Environments ---
URL = os.environ.get('SUPABASE_URL')
KEY = os.environ.get('SUPABASE_KEY')
TARGET_URL = os.environ.get('TARGET_URL')
MODE = os.environ.get('EXTRACT_MODE', 'music') # music, video, or mpl
UID = os.environ.get('USER_ID', 'public')

if not URL or not KEY or not TARGET_URL:
    print("❌ Missing required environment variables.")
    exit(1)

supabase: Client = create_client(URL, KEY)

def run():
    try:
        print(f"🚀 [Pro Worker] Starting: {TARGET_URL}")
        print(f"DEBUG: Supabase URL exists: {'Yes' if URL else 'No'}")
        print(f"DEBUG: Mode: {MODE}, User: {UID}")
        timestamp = int(time.time())
        
        # 1. Fetch Metadata first
        print("🔍 Step 1: Fetching metadata from YouTube/SC...")
        info_cmd = ['yt-dlp', '--dump-single-json', '--flat-playlist', TARGET_URL]
        info_res = subprocess.run(info_cmd, capture_output=True, text=True)
        metadata = json.loads(info_res.stdout)
        title = metadata.get('title', 'Unknown')
        uploader = metadata.get('uploader', 'Unknown')
        thumbnail = metadata.get('thumbnail', '')
        
        # 2. Setup Filename
        clean_title = "".join(x for x in title if x.isalnum() or x in " -_").strip()
        ext = 'mp3' if MODE == 'music' or MODE == 'mpl' else 'mp4'
        filename = f"{clean_title}_{timestamp}.{ext}"
        out_path = filename
        
        # 3. Download with Metadata & Lyrics
        cmd = ['yt-dlp']
        # Metadata tagging
        cmd += ['--add-metadata', '--embed-thumbnail']
        
        if MODE == 'music' or MODE == 'mpl':
            cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
            # Try to get lyrics (subtitles)
            cmd += ['--write-subs', '--write-auto-subs', '--sub-lang', 'ko,en,ja', '--embed-subs']
        else:
            cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best']
            cmd += ['--write-subs', '--embed-subs']
        
        cmd += ['-o', out_path, TARGET_URL]
        subprocess.run(cmd, check=True)

        # 4. Handle .mpl (JSON Manifest)
        mpl_url = ""
        if MODE == 'mpl':
            mpl_data = {
                "title": title,
                "artist": uploader,
                "thumbnail": thumbnail,
                "source": TARGET_URL,
                "lyrics": "Synced lyrics embedded in media",
                "version": "1.4.1"
            }
            mpl_filename = f"{clean_title}_{timestamp}.mpl"
            with open(mpl_filename, 'w', encoding='utf-8') as f:
                json.dump(mpl_data, f, indent=2, ensure_ascii=False)
            
            # Upload .mpl
            with open(mpl_filename, 'rb') as f:
                supabase.storage.from_('media').upload(path=f"{UID}/{mpl_filename}", file=f)
            mpl_url = supabase.storage.from_('media').get_public_url(f"{UID}/{mpl_filename}")
            print(f"📄 [MPL] Manifest Uploaded: {mpl_url}")

        # 5. Upload Media to Supabase Storage
        print(f"⬆️ [Supabase] Uploading Media...")
        with open(out_path, 'rb') as f:
            supabase.storage.from_('media').upload(
                path=f"{UID}/{filename}",
                file=f,
                file_options={"content-type": f"audio/mpeg" if ext == 'mp3' else "video/mp4"}
            )
        
        public_url = supabase.storage.from_('media').get_public_url(f"{UID}/{filename}")
        print(f"✅ [Supabase] Media Done: {public_url}")

        # 6. Save to DB
        supabase.table('media_files').insert({
            "uid": UID,
            "filename": filename,
            "url": public_url,
            "type": MODE,
            "mpl_url": mpl_url
        }).execute()
        print("💾 [DB] Data saved.")

    except Exception as e:
        print(f"❌ [Error] Trace: {str(e)}")
        exit(1)

if __name__ == "__main__":
    run()
