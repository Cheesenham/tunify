import os
import json

base_dir = r'c:\Users\kihwa\OneDrive\바탕 화면\mpl_system'

# 1. Update index.html and public/index.html
html_paths = [os.path.join(base_dir, 'index.html'), os.path.join(base_dir, 'public\index.html')]

html_additions = """
<script>
// [Admin Panel Logic]
// Included at the end of scripts.
</script>
"""

# Let's do a more robust string replacement for HTML
for hp in html_paths:
    with open(hp, 'r', encoding='utf-8') as f:
        html = f.read()

    # Changing placeholder
    html = html.replace('placeholder="서버 IP 주소 (예: 192.168.0.x:3000)"', 'placeholder="서버 번호를 입력하세요"')

    # Updating login logic
    old_login = "let serverIP = document.getElementById('apiServer').value.trim();\n            if (!serverIP.startsWith('http')) serverIP = 'http://' + serverIP;"
    new_login = """let serverIP = document.getElementById('apiServer').value.trim();
            if (serverIP === '1211') serverIP = 'https://reaches-pick-grow-open.trycloudflare.com';
            else if (serverIP !== '' && !serverIP.startsWith('http')) serverIP = 'http://' + serverIP;"""
    html = html.replace(old_login, new_login)

    # Adding pw support
    old_fetch = "body: JSON.stringify({ id: v })"
    new_fetch = "body: JSON.stringify({ id: v, pw: document.getElementById('userPw').value })"
    html = html.replace(old_fetch, new_fetch)

    # We will write the full implementation securely later.
    
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html)
