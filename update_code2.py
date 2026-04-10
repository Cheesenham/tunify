import os

base_dir = r'c:\Users\kihwa\OneDrive\바탕 화면\mpl_system'

# Fix index.html undefined 'f' variable inside onclick
for hp in [os.path.join(base_dir, 'index.html'), os.path.join(base_dir, 'public', 'index.html')]:
    with open(hp, 'r', encoding='utf-8') as file:
        html = file.read()
    
    old_onclick = "onclick=\"window.location.href='/player?file='+encodeURIComponent(f)\""
    new_onclick = "onclick=\"window.location.href='/player?file=' + encodeURIComponent(`${f}`)\""
    if old_onclick in html:
        html = html.replace(old_onclick, new_onclick)
        with open(hp, 'w', encoding='utf-8') as file:
            file.write(html)


# Update player.html: Add virtual playlist for single file + Sync adjustment
player_paths = [os.path.join(base_dir, 'player.html'), os.path.join(base_dir, 'public', 'player.html')]

sync_html = """
        <div class="time-row">
            <span id="timeCurr">00:00</span>
            <div style="display:flex; gap:5px; align-items:center;">
                <button onclick="adjustSync(-0.5)" style="background:none; border:1px solid #fff; color:#fff; border-radius:5px; cursor:pointer;" title="가사 빠르게">-0.5s</button>
                <span id="syncStatus" style="font-size:0.7rem;">0.0s</span>
                <button onclick="adjustSync(0.5)" style="background:none; border:1px solid #fff; color:#fff; border-radius:5px; cursor:pointer;" title="가사 느리게">+0.5s</button>
            </div>
            <span id="timeTotal">00:00</span>
        </div>
"""

for pp in player_paths:
    with open(pp, 'r', encoding='utf-8') as file:
        html = file.read()
    
    # 1. Inject Sync UI
    old_time_row = """        <div class="time-row">
            <span id="timeCurr">00:00</span>
            <span id="timeTotal">00:00</span>
        </div>"""
    if old_time_row in html:
        html = html.replace(old_time_row, sync_html)

    # 2. Add lyricOffset variable and adjust function
    if "let lyricOffset = 0;" not in html:
        html = html.replace("let PLAYER_CORE = null, LYRICS = [], COLOR_THIEF = new ColorThief();", "let PLAYER_CORE = null, LYRICS = [], COLOR_THIEF = new ColorThief();\n        let lyricOffset = 0;\n        function adjustSync(val) { lyricOffset += val; document.getElementById('syncStatus').innerText = (lyricOffset>0?'+':'')+lyricOffset.toFixed(1)+'s'; }")
    
    # 3. Apply lyricOffset to Render
    html = html.replace("const ms = PLAYER_CORE.currentTime * 1000;", "const ms = (PLAYER_CORE.currentTime - lyricOffset) * 1000;")

    # 4. Fix Single File Play -> Next Song logic
    init_old = """            } else if (singleFile) {
                // === Single File Mode ===
                await loadTrack(singleFile);
            } else {"""
    init_new = """            } else if (singleFile) {
                // === Single File Mode ===
                const r = await fetch(API_URL + `/api/files?id=${uid}`);
                const d = await r.json();
                playlist = d.files || [];
                currentIndex = playlist.indexOf(singleFile);
                if(currentIndex === -1) currentIndex = 0;
                
                document.getElementById('playlistToggle').classList.remove('hidden');
                document.getElementById('shuffleBtn').style.display = '';
                document.getElementById('prevBtn').style.display = '';
                document.getElementById('nextBtn').style.display = '';
                document.getElementById('repeatBtn').style.display = '';
                
                shuffledOrder = [...Array(playlist.length).keys()];
                if (playlist.length > 0) renderTrackList();
                await loadTrack(singleFile);
            } else {"""
    if init_old in html:
        html = html.replace(init_old, init_new)

    with open(pp, 'w', encoding='utf-8') as file:
        file.write(html)

print("Patch applied to all html files")
