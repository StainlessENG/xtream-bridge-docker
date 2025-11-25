const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');

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

// CRITICAL: Add these middleware for parsing request bodies
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CRITICAL: Enable CORS for IPTV apps
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  next();
});

// Logging middleware
app.use((req, res, next) => {
  console.log(`Incoming request: ${req.method} ${req.url}`);
  console.log('Query params:', req.query);
  console.log('Body:', req.body);
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

  // Parse M3U manually
  channels = [];
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('#EXTINF')) {
      const name = lines[i].split(',')[1] || `Channel ${channels.length + 1}`;
      const url = lines[i + 1] || '';
      channels.push({
        name: name.trim(),
        stream_id: channels.length + 1,
        stream_type: 'live',
        stream_url: url.trim()
      });
    }
  }

  console.log(`Loaded ${channels.length} channels from uploaded file`);
  res.send(`<h2>Upload successful!</h2><p>${channels.length} channels loaded.</p>`);
});

// Authentication middleware - checks both query params AND body
function authenticate(req, res, next) {
  // Try query params first, then body
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  console.log(`Auth attempt - Username: ${username}, Password: ${password}`);
  
  if (users[username] && users[username] === password) {
    req.user = username;
    next();
  } else {
    console.log('Authentication failed');
    res.status(403).json({ 
      user_info: {
        auth: 0,
        status: 'Disabled',
        message: 'Invalid credentials'
      }
    });
  }
}

// Xtream API: player_api.php - handle different actions
app.get('/player_api.php', authenticate, (req, res) => {
  const action = req.query.action;
  
  console.log(`Action requested: ${action}`);

  // Default response (login/authentication)
  if (!action) {
    return res.json({
      user_info: {
        username: req.user,
        password: users[req.user],
        auth: 1,
        status: 'Active',
        exp_date: Math.floor(Date.now() / 1000) + (365 * 24 * 60 * 60), // 1 year from now
        is_trial: '0',
        active_cons: '0',
        created_at: Math.floor(Date.now() / 1000),
        max_connections: '1'
      },
      server_info: {
        url: req.hostname,
        port: PORT.toString(),
        https_port: '443',
        server_protocol: 'http',
        rtmp_port: '1935',
        time_now: new Date().toISOString()
      }
    });
  }

  // Handle get_live_streams
  if (action === 'get_live_streams') {
    return res.json(channels);
  }

  // Handle get_live_categories
  if (action === 'get_live_categories') {
    return res.json([
      {
        category_id: '1',
        category_name: 'All Channels',
        parent_id: 0
      }
    ]);
  }

  // Handle get_vod_streams
  if (action === 'get_vod_streams') {
    return res.json([]);
  }

  // Handle get_series
  if (action === 'get_series') {
    return res.json([]);
  }

  res.json({ error: 'Unknown action' });
});

// Also support POST requests for player_api.php
app.post('/player_api.php', authenticate, (req, res) => {
  // Redirect to GET handler
  req.query = { ...req.query, ...req.body };
  app._router.handle(req, res);
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
  console.log(`Upload page: http://localhost:${PORT}/upload`);
  console.log(`API endpoint: http://localhost:${PORT}/player_api.php`);
});
