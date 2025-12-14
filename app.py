const express = require('express');
const axios = require('axios');
const fs = require('fs');
const M3UParser = require('m3u-parser');

const app = express();
const PORT = process.env.PORT || 3000;

// users.json format expected:
// {
//   "main": { "password": "admin", "m3u_url": "https://...", "epg_url": "https://..." },
//   "sid":  { "password": "Sidford2025", "m3u_url": "https://...", "epg_url": "https://..." }
// }
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));

// Per-user cache
const playlistCache = new Map(); // username -> { channels, loadedAt, sourceUrl }
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

function normalizeDropbox(url) {
  // Ensure direct download (Dropbox sometimes serves HTML if not dl=1)
  // If you already have dl=1, this keeps it.
  if (!url) return url;
  const u = new URL(url);
  u.searchParams.set('dl', '1');
  return u.toString();
}

async function loadPlaylistForUser(username) {
  const user = users[username];
  if (!user?.m3u_url) throw new Error(`No m3u_url set for user ${username}`);

  const m3uUrl = normalizeDropbox(user.m3u_url);

  const cached = playlistCache.get(username);
  const now = Date.now();
  if (cached && (now - cached.loadedAt) < CACHE_TTL_MS && cached.sourceUrl === m3uUrl) {
    return cached.channels;
  }

  const response = await axios.get(m3uUrl, {
    timeout: 20000,
    // Some hosts are picky; setting UA can help
    headers: { 'User-Agent': 'Mozilla/5.0 (M3U Proxy)' },
    maxContentLength: Infinity,
    maxBodyLength: Infinity
  });

  const parser = new M3UParser();
  parser.read(response.data);

  const channels = parser.getItems().map((item, index) => ({
    name: item.name || `Channel ${index + 1}`,
    stream_id: index + 1,
    stream_type: 'live',
    stream_url: item.url
  }));

  playlistCache.set(username, { channels, loadedAt: now, sourceUrl: m3uUrl });
  return channels;
}

// Authentication middleware (fixed for your object structure)
function authenticate(req, res, next) {
  const { username, password } = req.query;
  const user = users[username];

  if (user && user.password === password) {
    req.user = username;
    req.userConfig = user;
    next();
  } else {
    res.status(403).json({ error: 'Invalid credentials' });
  }
}

// Xtream API: player_api.php
app.get('/player_api.php', authenticate, async (req, res) => {
  try {
    const channels = await loadPlaylistForUser(req.user);

    res.json({
      user_info: {
        username: req.user,
        password: req.userConfig.password,
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
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Xtream API: get.php (returns M3U)
app.get('/get.php', authenticate, async (req, res) => {
  try {
    const channels = await loadPlaylistForUser(req.user);

    const m3uContent = channels
      .map(ch => `#EXTINF:-1,${ch.name}\n${ch.stream_url}`)
      .join('\n');

    res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store'); // helps with app/proxy caching
    res.send(`#EXTM3U\n${m3uContent}`);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
