const express = require('express');
const fileUpload = require('express-fileupload');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

// Configuration
const ADMIN_ID = "admin";
const ADMIN_PW = "1234";
const STORAGE_PATH = path.join(__dirname, 'mpl_storage');

if (!fs.existsSync(STORAGE_PATH)) {
    fs.mkdirSync(STORAGE_PATH);
}

app.use(cors());
app.use(express.json());
app.use(express.static('public'));
app.use(fileUpload());

// --- Authentication ---
app.post('/api/login', (req, res) => {
    const { id, pw } = req.body;
    if (id === ADMIN_ID && pw === ADMIN_PW) {
        return res.json({ success: true, token: "mpl-session-active" });
    }
    res.status(401).json({ success: false, message: "ID or Password incorrect" });
});

// --- File Management ---
app.get('/api/files', (req, res) => {
    fs.readdir(STORAGE_PATH, (err, files) => {
        if (err) return res.status(500).send(err);
        const mplFiles = files.filter(f => f.endsWith('.mpl'));
        res.json(mplFiles);
    });
});

app.post('/api/upload', (req, res) => {
    if (!req.files || !req.files.mplFile) {
        return res.status(400).send('No file uploaded.');
    }
    const file = req.files.mplFile;
    const savePath = path.join(STORAGE_PATH, file.name);
    file.mv(savePath, (err) => {
        if (err) return res.status(500).send(err);
        res.send('File uploaded!');
    });
});

app.get('/api/download/:filename', (req, res) => {
    const filePath = path.join(STORAGE_PATH, req.params.filename);
    if (!fs.existsSync(filePath)) return res.status(404).send("File not found");
    res.sendFile(filePath);
});

app.listen(PORT, () => {
    console.log(`MPL Node Server is running at http://localhost:${PORT}`);
});
