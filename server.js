
const express = require('express');
const axios = require('axios');
const fs = require('fs');
const M3UParser = require('m3u-parser');

const app = express();
const PORT = process.env.PORT || 3000;

// Load users
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));

// Your M3U link
const M3U_URL = 'http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721';

// Cache for channels
let channels = [];

// Fetch and parse M3U
async function loadPlaylist() {
  try {
    const response = await axios.get(M3U_URL);
    const parser = new M3UParser();
    parser.read(response.data);
    channels = parser.getItems().map((item, index) => ({
      name: item.name,
      stream_id: index + 1,
      stream_type: 'live',
      stream_url: item.url
    }));
    console.log(`Loaded ${channels.length} channels`);
  } catch (error) {
    console.error('Error loading playlist:', error.message);
  }
}

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

// Start server and load playlist
app.listen(PORT, async () => {
  console.log(`Server running on port ${PORT}`);
  await loadPlaylist();
});
