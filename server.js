const express = require('express');
const fileUpload = require('express-fileupload');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

// --- 데이터 및 폴더 초기화 ---
const ROOT_DIR = __dirname;
const STORAGE_DIR = path.join(ROOT_DIR, 'mpl_storage');
const DB_DIR = path.join(ROOT_DIR, 'db');

if (!fs.existsSync(STORAGE_DIR)) fs.mkdirSync(STORAGE_DIR);
if (!fs.existsSync(DB_DIR)) fs.mkdirSync(DB_DIR);

const USERS_FILE = path.join(DB_DIR, 'users.json');
const LOGS_FILE = path.join(DB_DIR, 'audit_log.json');

// 기본 관리자(admin) 계정 생성
if (!fs.existsSync(USERS_FILE)) {
    fs.writeFileSync(USERS_FILE, JSON.stringify([
        { id: "admin", pw: "1234", role: "admin" }
    ], null, 4));
}
if (!fs.existsSync(LOGS_FILE)) {
    fs.writeFileSync(LOGS_FILE, JSON.stringify([]));
}

app.use(cors());
app.use(express.json());
app.use(express.static('public'));
app.use(fileUpload());

// --- 헬퍼 함수 ---
function writeLog(userId, action, detail) {
    try {
        const logs = JSON.parse(fs.readFileSync(LOGS_FILE, 'utf-8'));
        logs.push({
            time: new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }),
            user: userId || "Unknown",
            action: action,
            detail: detail
        });
        // 최신 2000개만 유지 (용량 방지)
        if (logs.length > 2000) logs.shift();
        fs.writeFileSync(LOGS_FILE, JSON.stringify(logs, null, 4));
    } catch(e) { console.error("Log Error:", e); }
}

function getUser(id) {
    const users = JSON.parse(fs.readFileSync(USERS_FILE, 'utf-8'));
    return users.find(u => u.id === id);
}

function getUserDir(id) {
    const dir = path.join(STORAGE_DIR, id);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);
    return dir;
}

// --- 1. 인증 및 사용자 관리 API ---
app.post('/api/login', (req, res) => {
    const { id, pw } = req.body;
    const user = getUser(id);
    
    if (user && user.pw === pw) {
        writeLog(id, "LOGIN", "로그인 성공");
        getUserDir(id); // 폴더가 없으면 생성
        return res.json({ success: true, id: user.id, role: user.role });
    }
    writeLog(id || "Unknown", "LOGIN_FAIL", "로그인 실패 (비밀번호 불일치 또는 없는 아이디)");
    res.status(401).json({ success: false, msg: "아이디나 비밀번호가 틀립니다." });
});

app.post('/api/logout', (req, res) => {
    const { id } = req.body;
    writeLog(id, "LOGOUT", "로그아웃");
    res.json({ success: true });
});

app.post('/api/change-password', (req, res) => {
    const { id, currentPw, newPw } = req.body;
    let users = JSON.parse(fs.readFileSync(USERS_FILE, 'utf-8'));
    const userIndex = users.findIndex(u => u.id === id && u.pw === currentPw);
    
    if (userIndex !== -1) {
        users[userIndex].pw = newPw;
        fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 4));
        writeLog(id, "PW_CHANGE", "비밀번호 변경 완료");
        return res.json({ success: true });
    }
    writeLog(id, "PW_CHANGE_FAIL", "비밀번호 변경 실패 (현재 비번 틀림)");
    res.status(400).json({ success: false, msg: "현재 비밀번호가 일치하지 않습니다." });
});

// 관리자: 새 계정 생성
app.post('/api/admin/create-user', (req, res) => {
    const { adminId, newId, newPw } = req.body;
    const adminUser = getUser(adminId);
    
    if (adminUser && adminUser.role === 'admin') {
        let users = JSON.parse(fs.readFileSync(USERS_FILE, 'utf-8'));
        if (users.find(u => u.id === newId)) {
            return res.status(400).json({ success: false, msg: "이미 존재하는 아이디입니다." });
        }
        users.push({ id: newId, pw: newPw, role: "user" });
        fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 4));
        writeLog(adminId, "ADMIN_CREATE_USER", `새 계정 생성: ${newId}`);
        getUserDir(newId); // 계정 생성 시 개인 폴더도 즉시 만듦
        return res.json({ success: true });
    }
    res.status(403).json({ success: false, msg: "관리자 권한이 없습니다." });
});

// 관리자: 로그 조회
app.get('/api/admin/logs', (req, res) => {
    const { adminId } = req.query;
    const adminUser = getUser(adminId);
    if (adminUser && adminUser.role === 'admin') {
        const logs = JSON.parse(fs.readFileSync(LOGS_FILE, 'utf-8'));
        return res.json({ success: true, logs: logs.reverse() }); // 최신순 정렬
    }
    res.status(403).json({ success: false, msg: "관리자 권한이 없습니다." });
});

// --- 2. 파일 관리 API ---
app.get('/api/files', (req, res) => {
    const { id } = req.query;
    if (!id) return res.status(400).send("ID is required");
    
    const userDir = getUserDir(id);
    fs.readdir(userDir, (err, files) => {
        if (err) return res.status(500).send(err);
// 지원하는 확장자 필터링 (.mpl, .mplp)
        const validFiles = files.filter(f => f.endsWith('.mpl') || f.endsWith('.mplp'));
        res.json({ success: true, files: validFiles });
    });
});

app.post('/api/upload', (req, res) => {
    const { id } = req.body;
    if (!id || !req.files || !req.files.mplFile) {
        return res.status(400).json({ success: false, msg: "잘못된 요청입니다." });
    }
    
    const file = req.files.mplFile;
    const userDir = getUserDir(id);
    const savePath = path.join(userDir, file.name);
    
    file.mv(savePath, (err) => {
        if (err) return res.status(500).json({ success: false, msg: err.toString() });
        writeLog(id, "UPLOAD", `파일 업로드: ${file.name}`);
        res.json({ success: true });
    });
});

app.post('/api/rename', (req, res) => {
    const { id, oldName, newName } = req.body;
    if (!id || !oldName || !newName) return res.status(400).json({ success: false });

    const userDir = getUserDir(id);
    const oldPath = path.join(userDir, oldName);
    const newPath = path.join(userDir, newName);

    if (fs.existsSync(oldPath)) {
        fs.renameSync(oldPath, newPath);
        writeLog(id, "RENAME", `파일명 변경: ${oldName} -> ${newName}`);
        return res.json({ success: true });
    }
    res.status(404).json({ success: false, msg: "파일을 찾을 수 없습니다." });
});

app.get('/api/download/:id/:filename', (req, res) => {
    // 본인의 디렉토리에만 접근 가능
    const { id, filename } = req.params;
    const userDir = getUserDir(id);
    const filePath = path.join(userDir, filename);
    
    // 경로 조작 방지 (디렉토리 이탈 차단)
    if (!path.normalize(filePath).startsWith(userDir)) {
        writeLog(id, "HACK_ATTEMPT", `권한 없는 경로 접근 시도: ${filename}`);
        return res.status(403).send("Forbidden");
    }

    if (!fs.existsSync(filePath)) return res.status(404).send("File not found");
    
    writeLog(id, "PLAY/DOWNLOAD", `파일 스트리밍: ${filename}`);
    res.sendFile(filePath);
});

const { exec, execSync } = require('child_process');

// --- 2.5 Web Maker API (Native NodeJS Extraction) ---
// 파이썬 문제 해결을 위해 순수 JS 강제 자동 설치 패치 (파이썬/ffmpeg 모듈 완전 제거)
let ytdl, ytSearch, SoundCloud;
try {
    ytdl = require('@distube/ytdl-core');
    ytSearch = require('yt-search');
    SoundCloud = require('soundcloud-scraper');
} catch(e) {
    console.log("🚀 [Auto-Install] 필수 순수 JS 라이브러리를 휴대폰에 자동 설치합니다... (최대 1~2분 소요)");
    try {
        execSync('npm install @distube/ytdl-core yt-search soundcloud-scraper', { stdio: 'inherit' });
        console.log("✅ 설치 완료! 서버가 곧 재부팅됩니다.");
    } catch(err) {
        console.log("❌ 자동 설치 실패! npm 권한 문제일 수 있습니다.", err.message);
    }
    process.exit(1); 
}

const scClient = new SoundCloud.Client();

app.post('/api/maker/search', async (req, res) => {
    const { platform, query } = req.body;
    
    if (platform === 'soundcloud') {
        try {
            const result = await scClient.search(query, 'track');
            // search result returns an array of tracks
            const entries = result.slice(0, 5).map(e => ({
                title: e.title || e.name,
                url: e.url,
                thumbnail: e.thumbnail || 'https://via.placeholder.com/60'
            }));
            res.json({ success: true, results: entries });
        } catch(e) {
            res.json({ success: false, error: "사클 순수 JS 검색 실패: " + e.message });
        }
        return;
    }

    // 유튜브 검색 (순수 자바스크립트 엔진)
    try {
        const r = await ytSearch(query);
        const videos = r.videos.slice(0, 5);
        const entries = videos.map(v => ({
            title: v.title,
            url: v.url,
            thumbnail: v.thumbnail
        }));
        res.json({ success: true, results: entries });
    } catch(e) {
        res.json({ success: false, error: "유튜브 JS 검색 실패: " + e.message });
    }
});

app.post('/api/maker/extract', async (req, res) => {
    const { url, type } = req.body;
    
    // 사클 순수 JS 추출
    if (url.includes('soundcloud.com')) {
        try {
            const info = await scClient.getSongInfo(url);
            const title = info.title.replace(/[\/\?<>\\:\*\|":]/g, '');
            const artist = info.author.name;
            const ext = 'mp3';
            
            const fname = `maker_temp_${Date.now()}.${ext}`;
            const savePath = path.join(STORAGE_DIR, fname);
            
            const stream = await info.downloadProgressive();
            stream.pipe(fs.createWriteStream(savePath));
            
            let thumbFname = "";
            if (info.thumbnail) {
                thumbFname = `maker_temp_${Date.now()}_thumb.jpg`;
                try {
                    const thumbImg = await fetch(info.thumbnail);
                    fs.writeFileSync(path.join(STORAGE_DIR, thumbFname), Buffer.from(await thumbImg.arrayBuffer()));
                } catch(e) {}
            }
            
            stream.on('end', () => res.json({ success: true, file: fname, thumb: thumbFname, title: title, artist: artist, ext: ext }));
        } catch(e) {
            res.json({ success: false, error: "사클 JS 추출 실패: " + e.message });
        }
        return;
    }

    // 유튜브 순수 JS 엔진 추출
    try {
        const info = await ytdl.getInfo(url);
        const title = info.videoDetails.title.replace(/[\/\?<>\\:\*\|":]/g, '');
        const artist = info.videoDetails.author.name;
        const ext = type === 'video' ? 'mp4' : 'm4a';
        
        let thumb = "";
        const thumbnails = info.videoDetails.thumbnails;
        if(thumbnails && thumbnails.length > 0) thumb = thumbnails[thumbnails.length-1].url;

        const fname = `maker_temp_${Date.now()}.${ext}`;
        const savePath = path.join(STORAGE_DIR, fname);

        let selectedFormat = null;
        try {
            if (type === 'video') {
                try {
                    selectedFormat = ytdl.chooseFormat(info.formats, { filter: 'audioandvideo' });
                } catch(e) {
                    console.log("audioandvideo 합본 검색 실패. 외부 병합기 없는 순수 비디오 추출 우회 가동...");
                    const videoOnly = info.formats.filter(f => f.hasVideo && f.container === 'mp4');
                    if (videoOnly.length > 0) selectedFormat = videoOnly[0];
                }
            } else {
                selectedFormat = ytdl.chooseFormat(info.formats, { filter: 'audioonly', quality: 'highestaudio' });
            }
        } catch(formatPickErr) {
            return res.json({ success: false, error: "파싱 에러 - 지원가능한 포맷이 아예 존재하지 않습니다." });
        }
        
        let ytdlOpts = selectedFormat ? { format: selectedFormat } : { quality: 'highest' };
        let stream = ytdl.downloadFromInfo(info, ytdlOpts);

        stream.pipe(fs.createWriteStream(savePath));
        
        stream.on('end', async () => {
            let thumbFname = "";
            if (thumb) {
                thumbFname = `maker_temp_${Date.now()}_thumb.jpg`;
                const thumbPath = path.join(STORAGE_DIR, thumbFname);
                try {
                    const thumbImg = await fetch(thumb);
                    fs.writeFileSync(thumbPath, Buffer.from(await thumbImg.arrayBuffer()));
                } catch(e) {}
            }
            res.json({
                success: true,
                file: fname,
                thumb: thumbFname,
                title: title,
                artist: artist,
                ext: ext
            });
        });
        
        stream.on('error', (e) => {
            res.json({ success: false, error: "ytdl 스트림 에러: " + e.message });
        });
    } catch(e) {
        res.json({ success: false, error: "ytdl 추출 실패: " + e.message });
    }
});

app.post('/api/maker/lyrics', (req, res) => {
    const { query } = req.body;
    const pyScript = `
import syncedlyrics
import json

search_query = ${JSON.stringify(query)}
try:
    lrc = syncedlyrics.search(search_query)
    print(json.dumps({"success": True, "lrc": lrc}))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
`;
    fs.writeFileSync('temp_lrc.py', pyScript);
    exec('python temp_lrc.py', (err, stdout) => {
        try {
            const outputs = stdout.trim().split('\n');
            const result = JSON.parse(outputs[outputs.length - 1]);
            res.json(result);
        } catch(e) {
            res.json({ success: false, error: "가사를 찾을 수 없습니다." });
        }
    });
});

app.get('/api/maker/temp/:filename', (req, res) => {
    const fp = path.join(STORAGE_DIR, req.params.filename);
    if (!fs.existsSync(fp)) return res.status(404).send("File not found");
    res.sendFile(fp);
});

// --- 3. 시스템 무선 업데이트 API (OTA) ---
app.post('/api/admin/update-system', (req, res) => {
    const { adminId, adminPw } = req.body;
    const adminUser = getUser(adminId);
    
    // 관리자 실명 인증 확인
    if (adminUser && adminUser.pw === adminPw && adminUser.role === 'admin') {
        const { serverCode, indexCode } = req.files || {};
        try {
            if (serverCode) fs.writeFileSync(path.join(ROOT_DIR, 'server.js'), serverCode.data);
            if (indexCode) {
                const publicDir = path.join(ROOT_DIR, 'public');
                if (!fs.existsSync(publicDir)) fs.mkdirSync(publicDir);
                fs.writeFileSync(path.join(publicDir, 'index.html'), indexCode.data);
            }
            writeLog(adminId, "SYSTEM_UPDATE", "시스템 무선 업데이트 패치 완료");
            console.log("❗ 원격 업데이트 요청 수신. 코드를 교체하고 서버를 재시작합니다...");
            res.json({ success: true, msg: "업데이트가 성공적으로 전송되었습니다." });
            
            // 1초 뒤 서버 자살 (터눅스의 루프 스크립트가 인식하고 새 코드로 부활시킴)
            setTimeout(() => process.exit(0), 1000);
            return;
        } catch(e) {
            return res.status(500).json({ success: false, msg: "코드 교체 중 오류: " + e.message });
        }
    }
    res.status(403).json({ success: false, msg: "업데이트 권한이 없습니다." });
});

// 서버 가동
app.listen(PORT, '0.0.0.0', () => {
    console.log(`================================`);
    console.log(` MPL PRO Server Running `);
    console.log(` Port: ${PORT} `);
    console.log(` Directory: ${ROOT_DIR} `);
    console.log(`================================`);
});
