
const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const M3UParser = require('m3u-parser');

const app = express();
const PORT = process.env.PORT || 3000;

// Load users
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));

// Upload config
const uploadDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir);
const upload = multer({ dest: uploadDir });

// Channels cache
let channels = [];

// Logging middleware
app.use((req, res, next) => {
  console.log(`Incoming request: ${req.method} ${req.url}`);
  next();
});

// Serve upload page
app.get('/upload', (req, res) => {
  res.sendFile(path.join(__dirname, 'views', 'upload.html'));
});

// Handle file upload
app.post('/upload', upload.single('playlist'), (req, res) => {
  const filePath = req.file.path;
  console.log(`File uploaded: ${filePath}`);
  const content = fs.readFileSync(filePath, 'utf8');
  if (!content.includes('#EXTM3U')) {
    return res.status(400).send('Invalid M3U file');
  }
  const parser = new M3UParser();
  parser.read(content);
  channels = parser.getItems().map((item, index) => ({
    name: item.name,
    stream_id: index + 1,
    stream_type: 'live',
    stream_url: item.url
  }));
  console.log(`Loaded ${channels.length} channels from uploaded file`);
  res.send(`<h2>Upload successful!</h2><p>${channels.length} channels loaded.</p>`);
});

// Authentication middleware
function authenticate(req, res, next) {
  const { username, password } = req.query;
  if (users[username] && users[username] === password) {
    req.user = username;
    next();
  } else {
    res.status(403).json({ error: 'Invalid credentials' });
  }
}

// Xtream API: player_api.php
app.get('/player_api.php', authenticate, (req, res) => {
  res.json({
    user_info: {
      username: req.user,
      password: users[req.user],
      auth: 1,
      status: 'Active'
    },
    server_info: {
      url: req.hostname,
      port: PORT,
      https_port: 443,
      server_protocol: 'http'
    },
    available_channels: channels
  });
});

// Xtream API: get.php (returns M3U)
app.get('/get.php', authenticate, (req, res) => {
  const m3uContent = channels.map(ch => `#EXTINF:-1,${ch.name}\n${ch.stream_url}`).join('\n');
  res.setHeader('Content-Type', 'application/vnd.apple.mpegurl');
  res.send(`#EXTM3U\n${m3uContent}`);
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
