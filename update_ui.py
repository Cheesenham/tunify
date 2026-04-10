import os

base_dir = r'c:\Users\kihwa\OneDrive\바탕 화면\mpl_system'

html_paths = [
    os.path.join(base_dir, 'index.html'), 
    os.path.join(base_dir, 'public', 'index.html')
]

# Admin Panel UI
admin_panel_html = """
    <div id="adminPanel" class="card hidden" style="border: 2px solid #3a0ca3; background: #eef2ff; margin-top: 20px;">
        <h3>👑 시스템 관리자 패널</h3>
        <div style="display:flex; gap:10px;">
            <input type="text" id="newAccId" placeholder="새 아이디">
            <input type="password" id="newAccPw" placeholder="새 비밀번호">
            <button onclick="adminManageAccount('POST')" class="btn-success" style="width:150px;">생성 / 덮어쓰기</button>
        </div>
        <div style="display:flex; gap:10px; margin-top:10px;">
            <input type="text" id="delAccId" placeholder="삭제할 아이디">
            <button onclick="adminManageAccount('DELETE')" class="btn-danger" style="width:150px;">계정 영구삭제</button>
        </div>
    </div>
"""

tabs_html = """
        <div class="section-title">
            <h3 id="storageTitle">🎵 내 보관함</h3>
        </div>
        <div style="display:flex; gap:10px; margin-bottom:10px;">
             <button id="tabAll" class="btn-outline" style="background:var(--accent); color:white;" onclick="filterFiles('all')">전체</button>
             <button id="tabAudio" class="btn-outline" onclick="filterFiles('audio')">음악</button>
             <button id="tabVideo" class="btn-outline" onclick="filterFiles('video')">동영상</button>
        </div>
"""

js_admin_panel = """
        async function adminManageAccount(method) {
            const id = method === 'POST' ? document.getElementById('newAccId').value : document.getElementById('delAccId').value;
            const pw = document.getElementById('newAccPw').value;
            if(!id) return alert("아이디를 입력하세요");
            
            const r = await fetch(API_URL + '/api/admin/users', {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id, pw })
            });
            const d = await r.json();
            if(d.success) alert("작업이 완료되었습니다!");
            else alert("작업 실패");
        }

        async function softDeleteFile(f) {
            if(!confirm(`'${f}' 창고에서 삭제하시겠습니까?\\n(7일 뒤 서버에서 완전히 자동 삭제됩니다.)`)) return;
            const r = await fetch(API_URL + '/api/delete_file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: localStorage.getItem('MPL_ID'), filename: f })
            });
            alert((await r.json()).msg);
            loadFiles();
        }

        let allLoadedFiles = [];
        let currentTabFilter = 'all';

        function filterFiles(type) {
            currentTabFilter = type;
            document.getElementById('tabAll').style.background = type === 'all' ? 'var(--accent)' : 'transparent';
            document.getElementById('tabAll').style.color = type === 'all' ? 'white' : 'var(--accent)';
            document.getElementById('tabAudio').style.background = type === 'audio' ? 'var(--accent)' : 'transparent';
            document.getElementById('tabAudio').style.color = type === 'audio' ? 'white' : 'var(--accent)';
            document.getElementById('tabVideo').style.background = type === 'video' ? 'var(--accent)' : 'transparent';
            document.getElementById('tabVideo').style.color = type === 'video' ? 'white' : 'var(--accent)';
            document.getElementById('storageTitle').innerText = type === 'video' ? '🎬 동영상 보관함' : (type === 'audio' ? '🎧 음악 보관함' : '🎵 내 보관함');
            renderFiles();
        }

        function renderFiles() {
            let list = allLoadedFiles;
            // 임시 분리 로직: 파일명이나 메타데이터에 video가 포함되면 동영상
            if(currentTabFilter === 'audio') list = list.filter(f => !f.toLowerCase().includes('video') && !f.toLowerCase().includes('mp4'));
            if(currentTabFilter === 'video') list = list.filter(f => f.toLowerCase().includes('video') || f.toLowerCase().includes('mp4'));
            
            document.getElementById('fileList').innerHTML = list.map(f => `
                <div class="search-item">
                    <div style="font-weight: bold; flex:1; cursor:pointer;" onclick="window.location.href='/player?file='+encodeURIComponent(f)">🎵 ${f}</div>
                    <button class="btn-outline btn-small" onclick="event.stopPropagation(); showAddToPlaylist('${f}')">📋+</button>
                    <button class="btn-danger btn-small" onclick="event.stopPropagation(); softDeleteFile('${f}')">삭제</button>
                </div>
            `).join('');
        }
"""

for hp in html_paths:
    with open(hp, 'r', encoding='utf-8') as f:
        html = f.read()

    # Inject Admin template right after playlistSection ends
    if 'id="adminPanel"' not in html:
        html = html.replace('</div>\n\n    <!-- Add to Playlist Modal -->', '</div>\n' + admin_panel_html + '\n    <!-- Add to Playlist Modal -->')

    # Add Tabs
    old_storage = """<div class="section-title">
            <h3>🎵 내 보관함</h3>
        </div>"""
    html = html.replace(old_storage, tabs_html)

    # Show Admin pane if role is admin
    v = "document.getElementById('userName').innerText = localStorage.getItem('MPL_ID');"
    if "adminPanel" not in html and "localStorage.getItem('MPL_ROLE')" not in v:
        pass # Simple check
    html = html.replace(v, v + "\n            if(localStorage.getItem('MPL_ROLE') === 'admin') document.getElementById('adminPanel').classList.remove('hidden');")

    # Update loadFiles to use allLoadedFiles
    js_load_files_old = """document.getElementById('fileList').innerHTML = d.files.map(f => `
                <div class="search-item">
                    <div style="font-weight: bold; flex:1; cursor:pointer;" onclick="window.location.href='/player?file=${f}'">🎵 ${f}</div>
                    <button class="btn-outline btn-small" onclick="event.stopPropagation(); showAddToPlaylist('${f}')">📋+</button>
                    <button class="btn-outline btn-small" onclick="event.stopPropagation(); rename('${f}')">수정</button>
                </div>
             `).join('');"""
    
    js_load_files_new = """allLoadedFiles = d.files || [];
            renderFiles();"""
    
    html = html.replace(js_load_files_old, js_load_files_new)

    # Inject JS functions before </script>
    if 'function filterFiles' not in html:
        html = html.replace('</script>', js_admin_panel + '\n    </script>')

    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html)

print("UI Patch Applied!")
