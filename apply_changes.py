import os
import json
import re

base_dir = r'c:\Users\kihwa\OneDrive\바탕 화면\mpl_system'

server_py = os.path.join(base_dir, 'server.py')
with open(server_py, 'r', encoding='utf-8') as f:
    text = f.read()

# Add users.json logic to server.py
users_logic = """
USERS_DB = os.path.join(STORAGE_DIR, 'users.json')

def load_users():
    if not os.path.exists(USERS_DB):
        # Default admin account
        with open(USERS_DB, 'w', encoding='utf-8') as f:
            json.dump({"admin": {"pw": "admin123", "role": "admin"}}, f)
    with open(USERS_DB, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {"admin": {"pw": "admin123", "role": "admin"}}

def save_users(users):
    with open(USERS_DB, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
def admin_users():
    users = load_users()
    data = request.json if request.is_json else {}
    if request.method == 'GET':
        return jsonify({"success": True, "users": users})
    elif request.method == 'POST':
        uid = data.get('id')
        if not uid: return jsonify({"success": False})
        users[uid] = {"pw": data.get('pw', '0000'), "role": "user"}
        save_users(users)
        os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
        return jsonify({"success": True})
    elif request.method == 'DELETE':
        uid = data.get('id')
        if uid in users and uid != 'admin':
            del users[uid]
            save_users(users)
        return jsonify({"success": True})

@app.route('/api/delete_file', methods=['POST'])
def soft_delete_file():
    # 7일 후 완전 삭제를 위한 임시 휴지통 스케줄 (가안)
    data = request.json
    uid = data.get('id', '').strip()
    filename = data.get('filename', '').strip()
    target = os.path.join(STORAGE_DIR, uid, filename)
    trash = os.path.join(STORAGE_DIR, uid, '.trash')
    os.makedirs(trash, exist_ok=True)
    if os.path.exists(target):
        os.rename(target, os.path.join(trash, filename))
    return jsonify({"success": True, "msg": "휴지통으로 이동되었습니다. (7일 후 영구삭제)"})
"""

# Replace old login with new login handling
old_login = """@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id', '').strip()
    if not uid:
        return jsonify({"success": False, "msg": "아이디를 입력하세요."})
    os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
    return jsonify({"success": True, "id": uid, "role": "user"})"""

new_login = """@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id', '').strip()
    pw = data.get('pw', '').strip()
    if not uid:
        return jsonify({"success": False, "msg": "아이디를 입력하세요."})
        
    users = load_users()
    if uid not in users:
        return jsonify({"success": False, "msg": "존재하지 않는 계정입니다."})
    
    if users[uid].get('pw') != pw:
        return jsonify({"success": False, "msg": "비밀번호가 일치하지 않습니다."})
        
    os.makedirs(os.path.join(STORAGE_DIR, uid), exist_ok=True)
    return jsonify({"success": True, "id": uid, "role": users[uid].get('role', 'user')})"""

text = text.replace(old_login, new_login)
if 'USERS_DB =' not in text:
    # Insert users logic after the imports and os.makedirs(PUBLIC_DIR, exist_ok=True)
    text = text.replace("os.makedirs(PUBLIC_DIR, exist_ok=True)", "os.makedirs(PUBLIC_DIR, exist_ok=True)\n" + users_logic)

with open(server_py, 'w', encoding='utf-8') as f:
    f.write(text)

# Also update index.html to have Server input 1211 logic
with open(os.path.join(base_dir, 'public', 'index.html'), 'r', encoding='utf-8') as f:
    html = f.read()

# Make placeholder change
html = html.replace('서버 IP 주소 (예: 192.168.0.x:3000)', '서버 번호를 입력하세요')

js_old_login = """let serverIP = document.getElementById('apiServer').value.trim();
            if (!serverIP.startsWith('http')) serverIP = 'http://' + serverIP;"""
js_new_login = """let serverIP = document.getElementById('apiServer').value.trim();
            if (serverIP === '1211') { serverIP = 'https://reaches-pick-grow-open.trycloudflare.com'; }
            else if (serverIP && !serverIP.startsWith('http')) { serverIP = 'http://' + serverIP; }"""
html = html.replace(js_old_login, js_new_login)

# Add role parameter to login response check
fetch_old = "if ((await r.json()).success) {"
fetch_new = """const res = await r.json();
            if (res.success) {
                localStorage.setItem('MPL_ROLE', res.role);"""
html = html.replace(fetch_old, fetch_new)

# Add password payload to fetch
html = html.replace("body: JSON.stringify({ id: v })", "body: JSON.stringify({ id: v, pw: document.getElementById('userPw').value })")

with open(os.path.join(base_dir, 'public', 'index.html'), 'w', encoding='utf-8') as f:
    f.write(html)
with open(os.path.join(base_dir, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(html)

print("Patch applied.")
