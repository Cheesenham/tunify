// ota_manager.js
// 어떤 에러가 발생해도 절대 꺼지지 않는 "비상 무선망 통신병" (포트 4000)
// 외부 모듈(express 등) 없이 순수 코어 엔진만 써서 무조건 켜지도록 설계됨

const http = require('http');
const fs = require('fs');
const { spawn } = require('child_process');
const path = require('path');

let serverProcess = null;

function startMainServer() {
    console.log("-----------------------------------------");
    console.log("서버 가동 준비중입니다.");
    
    // server.js를 자식 프로세스로 띄움 (에러로 죽어도 감시자는 안 죽음)
    serverProcess = spawn('node', ['server.js'], { stdio: 'inherit' });
    
    serverProcess.on('close', (code) => {
        console.log(`서버에 오류가 발생하였습니다. (코드: ${code}).`);
        console.log("서버를 재부팅합니다.");
        console.log("-----------------------------------------");
        setTimeout(startMainServer, 1000);
    });
}

// 1. 메인 시스템 가동
startMainServer();

// 2. 비상 무전망 (포트 4000) 구동
const otaServer = http.createServer((req, res) => {
    // CORS 처리
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        return res.end();
    }

    if (req.method === 'POST' && req.url === '/emergency-update') {
        let body = '';
        req.on('data', chunk => {
            body += chunk;
            // 폭탄 방어 로직 (최대 100MB까지만)
            if (body.length > 100 * 1024 * 1024) req.connection.destroy();
        });
        
        req.on('end', () => {
            try {
                const data = JSON.parse(body);
                console.log("코드가 수신되었습니다.");
                
                if (data.serverJs) fs.writeFileSync('server.js', data.serverJs);
                if (data.indexHtml) fs.writeFileSync(path.join('public', 'index.html'), data.indexHtml);
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ success: true }));
                
                console.log("서버를 재부팅합니다.");
                if (serverProcess) serverProcess.kill();
                setTimeout(startMainServer, 1000); // 1초 뒤 완전히 새 코드로 재부팅

            } catch (e) {
                res.writeHead(500);
                res.end(JSON.stringify({ success: false, error: e.message }));
            }
        });
    } else {
        res.writeHead(404);
        res.end();
    }
});

otaServer.listen(4000, () => {
    console.log("port 4000을 수신상태로 변경하였습니다.");
});
