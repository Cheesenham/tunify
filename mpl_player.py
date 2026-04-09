import sys
import os
import json
import zipfile
import tempfile
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
try:
    import vlc
    HAS_VLC = True
except ImportError:
    HAS_VLC = False

VERSION = "v2.2"

class MPLPlayerV2(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"MPL Player {VERSION}")
        self.geometry("1000x700")
        self.configure(bg="white")
        
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lyrics_data = [] 
        self.is_playing = False
        
        if HAS_VLC:
            self.vlc_instance = vlc.Instance()
            self.media_player = self.vlc_instance.media_player_new()
        else:
            self.media_player = None
            messagebox.showwarning("Warning", "VLC not found. Please install 'python-vlc' and VLC media player.")

        self.init_ui()
        
    def init_ui(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("White.TFrame", background="white")
        style.configure("Control.TFrame", background="#f8f9fa")
        
        main_frame = tk.Frame(self, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_bar = tk.Frame(main_frame, bg="white", padx=10, pady=10, highlightthickness=1, highlightbackground="#eeeeee")
        top_bar.pack(fill=tk.X)
        
        self.open_btn = tk.Button(top_bar, text="📁 .MPL 파일 열기", command=self.open_file, bg="#008CBA", fg="white", font=("Arial", 10, "bold"), padx=15)
        self.open_btn.pack(side=tk.LEFT)
        
        self.info_label = tk.Label(top_bar, text="곡을 선택해 주세요", bg="white", fg="#444444", font=("Arial", 12))
        self.info_label.pack(side=tk.LEFT, padx=20)
        
        display_frame = tk.Frame(main_frame, bg="white")
        display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.video_container = tk.Frame(display_frame, bg="black")
        self.video_container.pack(fill=tk.BOTH, expand=True)
        
        self.lyric_top = tk.Label(self.video_container, text="", bg="black", fg="white", font=("Arial", 20, "bold"), wraplength=800)
        self.lyric_top.place(relx=0.5, rely=0.1, anchor="n")
        
        self.lyric_center = tk.Label(self.video_container, text="", bg="black", fg="white", font=("Arial", 20, "bold"), wraplength=800)
        self.lyric_center.place(relx=0.5, rely=0.5, anchor="center")
        
        self.lyric_bottom = tk.Label(self.video_container, text="", bg="black", fg="white", font=("Arial", 20, "bold"), wraplength=800)
        self.lyric_bottom.place(relx=0.5, rely=0.9, anchor="s")

        controls_frame = tk.Frame(main_frame, bg="#f8f9fa", padx=10, pady=10)
        controls_frame.pack(fill=tk.X)
        
        self.play_btn = tk.Button(controls_frame, text="▶ 재생", command=self.toggle_play, bg="white", font=("Arial", 11), width=10)
        self.play_btn.pack(side=tk.LEFT)
        
        self.time_slider = ttk.Scale(controls_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.seek_media)
        self.time_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20)
        
        self.time_label = tk.Label(controls_frame, text="00:00 / 00:00", bg="#f8f9fa", font=("Courier", 10))
        self.time_label.pack(side=tk.RIGHT)

        self.update_tick()

    def toggle_play(self):
        if not self.media_player: return
        if self.is_playing:
            self.media_player.pause()
            self.play_btn.config(text="▶ 재생")
            self.is_playing = False
        else:
            self.media_player.play()
            self.play_btn.config(text="⏸ 일시정지")
            self.is_playing = True
            
    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("MPL 파일", "*.mpl")])
        if path:
            self.load_mpl(path)
            
    def load_mpl(self, path):
        if not HAS_VLC: return
        
        self.media_player.stop()
        self.lyrics_data.clear()
        self.clear_lyrics()
        
        self.temp_dir.cleanup()
        self.temp_dir = tempfile.TemporaryDirectory()
        
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                zf.extractall(self.temp_dir.name)
        except:
            return
            
        media_file, lrc_file, meta_file = None, None, None
        for f in os.listdir(self.temp_dir.name):
            # media. 로 시작하는 어떤 확장자든 미디어 파일로 인식합니다.
            if f.startswith("media."):
                media_file = os.path.join(self.temp_dir.name, f)
            elif f.endswith(".lrc"):
                lrc_file = os.path.join(self.temp_dir.name, f)
            elif f == "metadata.json":
                meta_file = os.path.join(self.temp_dir.name, f)
        
        if meta_file:
            with open(meta_file, 'r', encoding='utf-8') as mf:
                meta = json.load(mf)
                self.info_label.config(text=f"🎵 {meta.get('title')} - {meta.get('artist')}")
        
        if lrc_file:
            self.parse_lrc_v2(lrc_file)
            
        if media_file:
            media = self.vlc_instance.media_new(media_file)
            self.media_player.set_media(media)
            if sys.platform.startswith('win'):
                self.media_player.set_hwnd(self.video_container.winfo_id())
            else:
                self.media_player.set_xwindow(self.video_container.winfo_id())
            self.media_player.play()
            self.is_playing = True
            self.play_btn.config(text="⏸ 일시정지")

    def parse_lrc_v2(self, file_path):
        import re
        self.lyrics_data = []
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)')
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    mins, secs, ms_str, content = match.groups()
                    ms = int(ms_str) * 10 if len(ms_str) == 2 else int(ms_str)
                    time_ms = (int(mins) * 60 + int(secs)) * 1000 + ms
                    
                    pos = "Center"
                    pos_match = re.search(r'<pos:(Top|Center|Bottom)>', content)
                    if pos_match:
                        pos = pos_match.group(1)
                        content = content.replace(pos_match.group(0), "").strip()
                    
                    self.lyrics_data.append({'time_ms': time_ms, 'text': content.strip(), 'pos': pos})
        self.lyrics_data.sort(key=lambda x: x['time_ms'])

    def clear_lyrics(self):
        self.lyric_top.config(text="")
        self.lyric_center.config(text="")
        self.lyric_bottom.config(text="")

    def update_tick(self):
        if HAS_VLC and self.media_player and self.media_player.is_playing():
            pos = self.media_player.get_position() * 100
            self.time_slider.set(pos)
            
            curr_ms = self.media_player.get_time()
            total_ms = self.media_player.get_length()
            if total_ms > 0:
                self.time_label.config(text=f"{curr_ms//60000:02}:{(curr_ms%60000)//1000:02} / {total_ms//60000:02}:{(total_ms%60000)//1000:02}")
            self.update_lyrics(curr_ms)
        self.after(100, self.update_tick)

    def update_lyrics(self, current_time_ms):
        if not self.lyrics_data: return
        self.clear_lyrics()
        active_lyrics = {"Top": "", "Center": "", "Bottom": ""}
        for entry in self.lyrics_data:
            if entry['time_ms'] <= current_time_ms:
                active_lyrics[entry['pos']] = entry['text']
            else:
                break
        self.lyric_top.config(text=active_lyrics["Top"])
        self.lyric_center.config(text=active_lyrics["Center"])
        self.lyric_bottom.config(text=active_lyrics["Bottom"])

    def seek_media(self, val):
        if self.media_player and self.is_playing:
            self.media_player.set_position(float(val) / 100.0)

if __name__ == "__main__":
    app = MPLPlayerV2()
    app.mainloop()
