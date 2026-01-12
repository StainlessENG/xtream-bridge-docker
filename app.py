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
  if (!url) return url;
  try {
    const u = new URL(url);
    u.searchParams.set('dl', '1');
    return u.toString();
  } catch {
    return url;
  }
}

function safeHost(u) {
  try {
    return new URL(u).host;
  } catch {
    return 'unknown';
  }
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
    headers: {
      // IPTV providers often hate "node/axios" looking clients
      'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
      'Accept': '*/*'
    },
    maxContentLength: Infinity,
    maxBodyLength: Infinity,
    // Avoid axios throwing on 30x/40x if you want to inspect later (not needed here but safe)
    validateStatus: (s) => s >= 200 && s < 400
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

/**
 * Xtream API: player_api.php
 * Returns JSON with channels in available_channels
 */
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

/**
 * Xtream API: get.php (returns M3U)
 */
app.get('/get.php', authenticate, async (req, res) => {
  try {
    const channels = await loadPlaylistForUser(req.user);

    const m3uContent = channels
      .map(ch => `#EXTINF:-1,${ch.name}\n${ch.stream_url}`)
      .join('\n');

    res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.send(`#EXTM3U\n${m3uContent}`);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * DEBUG: Inspect stream URLs inside the playlist
 *
 * Query params:
 * - contains: substring filter for URLs (e.g. defaultgen.com:5050)
 * - limit: number of samples returned (max 200)
 */
app.get('/debug/streams', authenticate, async (req, res) => {
  try {
    const { contains = '', limit = '20' } = req.query;
    const channels = await loadPlaylistForUser(req.user);

    // Group counts by hostname
    const countsByHost = {};
    for (const ch of channels) {
      const host = safeHost(ch.stream_url);
      countsByHost[host] = (countsByHost[host] || 0) + 1;
    }

    const n = Math.max(1, Math.min(parseInt(limit, 10) || 20, 200));
    const samples = channels
      .filter(ch => !contains || (ch.stream_url || '').includes(contains))
      .slice(0, n)
      .map(ch => ({ name: ch.name, url: ch.stream_url, host: safeHost(ch.stream_url) }));

    res.json({
      user: req.user,
      total_channels: channels.length,
      contains,
      sample_count: samples.length,
      countsByHost,
      samples
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * DEBUG: Probe a single stream URL from the Render server
 * This helps confirm IP/UA restrictions:
 *
 * /debug/probe?username=main&password=admin&url=http://defaultgen.com:5050/live/user/pass/123.ts
 *
 * Notes:
 * - validateStatus() keeps axios from throwing on 401/403 etc.
 * - We only fetch headers + status; NOT downloading full stream.
 */
app.get('/debug/probe', authenticate, async (req, res) => {
  try {
    const { url } = req.query;
    if (!url) return res.status(400).json({ error: 'Missing url=' });

    // Basic guard: only allow http(s)
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return res.status(400).json({ error: 'Invalid url' });
    }
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return res.status(400).json({ error: 'Only http/https URLs allowed' });
    }

    // Use a HEAD first (lighter). If provider blocks HEAD, fallback to GET with Range.
    let r;
    try {
      r = await axios.head(url, {
        timeout: 15000,
        headers: {
          'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
          'Accept': '*/*'
        },
        validateStatus: () => true
      });
    } catch {
      r = await axios.get(url, {
        timeout: 15000,
        headers: {
          'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
          'Accept': '*/*',
          // Request only first bytes so we don't pull a whole stream
          'Range': 'bytes=0-2047'
        },
        responseType: 'arraybuffer',
        validateStatus: () => true
      });
    }

    res.json({
      probed_host: safeHost(url),
      status: r.status,
      statusText: r.statusText,
      // return a small, useful subset of headers
      headers: {
        'content-type': r.headers?.['content-type'],
        'content-length': r.headers?.['content-length'],
        'www-authenticate': r.headers?.['www-authenticate'],
        'server': r.headers?.['server'],
        'date': r.headers?.['date'],
        'location': r.headers?.['location']
      }
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
