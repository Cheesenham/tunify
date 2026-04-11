import os
import time
import subprocess
from supabase import create_client, Client

# --- Environments ---
URL = os.environ.get('SUPABASE_URL')
KEY = os.environ.get('SUPABASE_KEY')
TARGET_URL = os.environ.get('TARGET_URL')
MODE = os.environ.get('EXTRACT_MODE', 'music')
UID = os.environ.get('USER_ID', 'public')

if not URL or not KEY or not TARGET_URL:
    print("❌ Missing required environment variables.")
    exit(1)

supabase: Client = create_client(URL, KEY)

def run():
    try:
        print(f"🚀 [Worker] Extraction Start: {TARGET_URL} (Mode: {MODE})")
        timestamp = int(time.time())
        ext = 'mp3' if MODE == 'music' else 'mp4'
        filename = f"mpl_{UID}_{timestamp}.{ext}"
        out_path = filename
        
        # 1. Download
        cmd = ['yt-dlp']
        if MODE == 'music':
            cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
        else:
            cmd += ['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best']
        
        cmd += ['-o', out_path, TARGET_URL]
        subprocess.run(cmd, check=True)

        # 2. Upload to Supabase Storage (Bucket: media)
        print(f"⬆️ [Supabase] Uploading: {filename}")
        with open(out_path, 'rb') as f:
            supabase.storage.from_('media').upload(
                path=f"{UID}/{filename}",
                file=f,
                file_options={"content-type": f"audio/mpeg" if MODE == 'music' else "video/mp4"}
            )
        
        # 3. Get URL
        public_url = supabase.storage.from_('media').get_public_url(f"{UID}/{filename}")
        print(f"✅ [Supabase] Done: {public_url}")

        # 4. Save to DB
        try:
            supabase.table('media_files').insert({
                "uid": UID,
                "filename": filename,
                "url": public_url,
                "type": MODE
            }).execute()
            print("💾 [DB] Metadata saved.")
        except Exception as e:
            print(f"⚠️ [DB] Warning: {e}")

    except Exception as e:
        print(f"❌ [Error] Trace: {str(e)}")
        exit(1)

if __name__ == "__main__":
    run()
