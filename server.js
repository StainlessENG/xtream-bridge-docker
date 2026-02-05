/**
 * server.js — FULL CODE (NO STREAM PROXYING)
 *
 * Key behaviour:
 * - /player_api.php: Xtream API (login + categories + streams)
 * - /get.php: returns an M3U pointing at YOUR /live/... URLs (stable)
 * - /live/...: ALWAYS 302 redirects the client to the provider (zero video bandwidth on Render)
 * - /xmltv.php: per-user EPG with 6h cache
 * - /debug/streams + /debug/probe: diagnostics
 *
 * Result:
 * - Render never carries video bytes (no proxy streaming)
 * - Clients can still use Xtream-style /live/<user>/<pass>/<id>.ts URLs
 */

const express = require('express');
const https = require('https');
const http = require('http');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

// IMPORTANT: Set your public URL here
const SERVER_URL = process.env.SERVER_URL || 'https://xtream-bridge.onrender.com';

function getHost(u) {
  try { return new URL(u).host; } catch { return ''; }
}

// Load users with their individual M3U and EPG URLs
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));
console.log('Loaded users:', Object.keys(users));

// Per-user channels and categories cache
const userChannels = {};    // username -> channels array
const userCategories = {};  // username -> categories array

// Per-user EPG cache
const userEPG = {}; // username -> { data, lastFetched }
const EPG_CACHE_DURATION = 6 * 60 * 60 * 1000; // 6 hours

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.sendStatus(200);
  next();
});

// Logging
app.use((req, res, next) => {
  console.log(`${req.method} ${req.url}`);
  next();
});

// Helper function to fetch URL content (for M3U/EPG)
function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;

    client.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' }
    }, (res) => {
      // Follow redirects
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetchUrl(res.headers.location).then(resolve).catch(reject);
      }

      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode}`));
      }

      let data = '';
      res.on('data', chunk => (data += chunk));
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

// Helper function to parse M3U content
function parseM3U(content) {
  if (!content.includes('#EXTM3U')) throw new Error('Invalid M3U file');

  const newChannels = [];
  const newCategories = [];
  const categoryMap = new Map();
  let categoryIdCounter = 1;

  const lines = content.split('\n').map(l => l.trim()).filter(Boolean);

  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('#EXTINF')) {
      const extinf = lines[i];
      const url = lines[i + 1] || '';
      if (!url || url.startsWith('#')) continue;

      // Category / group-title
      let categoryName = 'Uncategorized';
      let groupMatch = extinf.match(/group-title="([^"]*)"/i);
      if (!groupMatch) groupMatch = extinf.match(/group-title=([^\s,]+)/i);
      if (!groupMatch) groupMatch = extinf.match(/tvg-group="([^"]*)"/i);
      if (groupMatch && groupMatch[1]) categoryName = groupMatch[1].trim();

      if (!categoryMap.has(categoryName)) {
        categoryMap.set(categoryName, categoryIdCounter++);
        newCategories.push({
          category_id: categoryMap.get(categoryName).toString(),
          category_name: categoryName,
          parent_id: 0
        });
      }
      const categoryId = categoryMap.get(categoryName);

      // Channel name
      const nameParts = extinf.split(',');
      const channelName = nameParts[nameParts.length - 1].trim() || `Channel ${newChannels.length + 1}`;

      const tvgIdMatch = extinf.match(/tvg-id="([^"]*)"/i);
      const tvgLogoMatch = extinf.match(/tvg-logo="([^"]*)"/i);

      const streamId = newChannels.length + 1;

      newChannels.push({
        num: streamId,
        name: channelName,
        stream_type: 'live',
        stream_id: streamId,
        stream_icon: tvgLogoMatch ? tvgLogoMatch[1] : '',
        epg_channel_id: tvgIdMatch ? tvgIdMatch[1] : null,
        added: Math.floor(Date.now() / 1000).toString(),
        category_id: categoryId.toString(),
        custom_sid: '',
        tv_archive: 0,
        direct_source: url.trim(),
        tv_archive_duration: 0
      });

      i++; // skip URL line
    }
  }

  return { channels: newChannels, categories: newCategories };
}

// Load M3U for a specific user
async function loadUserM3U(username) {
  try {
    const userConfig = users[username];
    if (!userConfig || !userConfig.m3u_url) {
      console.log(`No M3U URL configured for user: ${username}`);
      return;
    }

    console.log(`Fetching M3U for user: ${username}`);
    const content = await fetchUrl(userConfig.m3u_url);
    const result = parseM3U(content);

    userChannels[username] = result.channels;
    userCategories[username] = result.categories;

    console.log(`✓ Loaded ${result.channels.length} channels in ${result.categories.length} categories for ${username}`);
  } catch (error) {
    console.error(`Failed to load M3U for ${username}:`, error.message);
    userChannels[username] = [];
    userCategories[username] = [];
  }
}

// Load all users' M3U files on startup
async function loadAllUsers() {
  console.log('Loading M3U files for all users...');
  for (const username of Object.keys(users)) {
    await loadUserM3U(username);
  }
  console.log('All users loaded!');
}

// Root endpoint
app.get('/', (req, res) => {
  const userStats = Object.keys(users).map(u =>
    `${u}: ${userChannels[u]?.length || 0} channels, ${userCategories[u]?.length || 0} categories`
  ).join('<br>');

  res.send(`
    <h1>Xtream Bridge Server</h1>
    <h2>Users:</h2>
    <p>${userStats}</p>
    <p><a href="/reload-all">Reload All Users</a></p>
  `);
});

// Reload all users
app.get('/reload-all', async (req, res) => {
  await loadAllUsers();
  res.send('<h2>All users reloaded!</h2><a href="/">Back</a>');
});

// Reload specific user
app.get('/reload/:username', async (req, res) => {
  const username = req.params.username;
  if (!users[username]) return res.status(404).send('User not found');
  await loadUserM3U(username);
  res.send(`<h2>User ${username} reloaded!</h2><a href="/">Back</a>`);
});

// Authentication middleware - CASE INSENSITIVE
function authenticate(req, res, next) {
  const username = (req.query.username || req.body.username || '').toLowerCase();
  const password = req.query.password || req.body.password;

  console.log(`🔐 Auth attempt: username="${username}"`);

  // Find user case-insensitively
  const actualUsername = Object.keys(users).find(u => u.toLowerCase() === username);

  if (actualUsername && users[actualUsername].password === password) {
    console.log(`✓ Auth success for: ${actualUsername}`);
    req.user = actualUsername;

    // Load user's M3U if not already loaded
    if (!userChannels[actualUsername]) {
      console.log(`First login for ${actualUsername}, loading M3U...`);
      loadUserM3U(actualUsername)
        .then(() => next())
        .catch(err => {
          console.error(`Failed to load M3U for ${actualUsername}:`, err.message);
          next();
        });
    } else {
      next();
    }
  } else {
    console.log(`❌ Auth failed`);
    return res.status(403).json({
      user_info: {
        auth: 0,
        status: 'Disabled',
        message: 'Invalid credentials'
      }
    });
  }
}

/**
 * DEBUG: Inspect direct_source URLs for a user
 * /debug/streams?username=main&password=admin&contains=defaultgen.com:5050&limit=10
 */
app.get('/debug/streams', authenticate, (req, res) => {
  const contains = req.query.contains || '';
  const limit = Math.max(1, Math.min(parseInt(req.query.limit || '20', 10), 200));

  const channels = userChannels[req.user] || [];

  const countsByHost = {};
  for (const ch of channels) {
    const host = getHost(ch.direct_source);
    countsByHost[host] = (countsByHost[host] || 0) + 1;
  }

  const samples = channels
    .filter(ch => !contains || (ch.direct_source || '').includes(contains))
    .slice(0, limit)
    .map(ch => ({
      name: ch.name,
      host: getHost(ch.direct_source),
      url: ch.direct_source
    }));

  res.json({
    user: req.user,
    total_channels: channels.length,
    contains,
    sample_count: samples.length,
    countsByHost,
    samples
  });
});

/**
 * DEBUG: Probe a single provider URL FROM Render (confirms 401 blocks)
 * /debug/probe?username=main&password=admin&url=http://provider:port/live/USER/PASS/ID.ts
 */
app.get('/debug/probe', authenticate, (req, res) => {
  const url = req.query.url;
  if (!url) return res.status(400).json({ error: 'Missing url=' });

  const client = url.startsWith('https') ? https : http;

  const upstreamReq = client.request(url, {
    method: 'GET',
    headers: {
      'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
      'Accept': '*/*',
      'Range': 'bytes=0-2047'
    }
  }, (up) => {
    up.destroy();
    res.json({
      host: getHost(url),
      status: up.statusCode,
      headers: {
        'content-type': up.headers['content-type'],
        'www-authenticate': up.headers['www-authenticate'],
        'server': up.headers['server']
      }
    });
  });

  upstreamReq.on('error', (e) => res.status(500).json({ error: e.message }));
  upstreamReq.end();
});

/**
 * STREAM ENDPOINT (NO PROXYING):
 * - Validates user/pass
 * - Finds the channel by stream_id
 * - ALWAYS redirects to provider URL
 *
 * This keeps Render bandwidth near-zero for video.
 */
app.get('/live/:username/:password/:stream_id', (req, res) => {
  const { username, password, stream_id } = req.params;
  const usernameLower = username.toLowerCase();

  // Case-insensitive auth for streams
  const actualUsername = Object.keys(users).find(u => u.toLowerCase() === usernameLower);

  if (!actualUsername || users[actualUsername].password !== password) {
    console.log('❌ Stream auth failed');
    return res.status(403).send('Invalid credentials');
  }

  const cleanStreamId = parseInt(stream_id.replace(/\.(m3u8|ts)$/, ''), 10);

  console.log(`🎬 Stream request: User=${actualUsername}, StreamID=${cleanStreamId}`);

  const channels = userChannels[actualUsername] || [];
  const channel = channels.find(ch => ch.stream_id === cleanStreamId);

  if (!channel) {
    console.log(`❌ Channel not found: ${cleanStreamId}`);
    return res.status(404).send('Channel not found');
  }

  const streamUrl = channel.direct_source;
  console.log(`↪️ Redirecting to provider: ${channel.name} -> ${getHost(streamUrl)}`);

  // 302 is broadly supported by IPTV apps/tools.
  return res.redirect(302, streamUrl);
});

// Xtream API
app.get('/player_api.php', authenticate, (req, res) => {
  const action = req.query.action;
  const categoryId = req.query.category_id;

  console.log(`📡 API Call: action="${action}", user="${req.user}"`);

  const channels = userChannels[req.user] || [];
  const categories = userCategories[req.user] || [];

  // Default response (login check)
  if (!action) {
    const response = {
      user_info: {
        username: req.user,
        password: users[req.user].password,
        message: '',
        auth: 1,
        status: 'Active',
        exp_date: '1780331400',
        is_trial: '0',
        active_cons: '0',
        created_at: '1640995200',
        max_connections: '1',
        allowed_output_formats: ['m3u8', 'ts']
      },
      server_info: {
        xui: true,
        version: '1.0.0',
        revision: 1,
        url: 'xtream-bridge.onrender.com',
        port: '443',
        https_port: '443',
        server_protocol: 'https',
        rtmp_port: '1935',
        timezone: 'UTC',
        timestamp_now: Math.floor(Date.now() / 1000),
        time_now: new Date().toISOString().replace('T', ' ').substring(0, 19)
      }
    };

    console.log(`✓ Sending login response for ${req.user}`);
    return res.json(response);
  }

  if (action === 'get_live_categories') {
    console.log(`✓ Returning ${categories.length} categories for ${req.user}`);
    return res.json(categories);
  }

  if (action === 'get_live_streams') {
    const filtered = categoryId ? channels.filter(ch => ch.category_id === categoryId) : channels;
    console.log(`✓ Returning ${filtered.length} channels for ${req.user}`);
    return res.json(filtered);
  }

  if (action === 'get_vod_categories') return res.json([]);
  if (action === 'get_vod_streams') return res.json([]);
  if (action === 'get_series_categories') return res.json([]);
  if (action === 'get_series') return res.json([]);

  res.json({ error: 'Unknown action' });
});

app.post('/player_api.php', authenticate, (req, res) => {
  req.query = { ...req.query, ...req.body };
  app._router.handle(req, res);
});

/**
 * Get M3U file (stable bridge URLs)
 * Your /live/... will redirect to provider, so no video proxying happens.
 */
app.get('/get.php', authenticate, (req, res) => {
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;

  const channels = userChannels[req.user] || [];
  const categories = userCategories[req.user] || [];

  const m3uContent = channels.map(ch => {
    const proxyUrl = `${SERVER_URL}/live/${encodeURIComponent(username)}/${encodeURIComponent(password)}/${ch.stream_id}.m3u8`;
    const cat = categories.find(cat => cat.category_id === ch.category_id);

    return `#EXTINF:-1 tvg-id="${ch.epg_channel_id || ''}" tvg-logo="${ch.stream_icon}" group-title="${cat?.category_name || 'Uncategorized'}",${ch.name}\n${proxyUrl}`;
  }).join('\n');

  res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.send(`#EXTM3U\n${m3uContent}`);
});

// EPG endpoint - per user
app.get('/xmltv.php', authenticate, async (req, res) => {
  console.log(`📺 EPG requested for ${req.user}`);

  try {
    const userConfig = users[req.user];
    if (!userConfig || !userConfig.epg_url) {
      console.log(`No EPG URL configured for ${req.user}`);
      res.setHeader('Content-Type', 'application/xml; charset=utf-8');
      return res.send('<?xml version="1.0" encoding="UTF-8"?><tv></tv>');
    }

    const now = Date.now();
    const cached = userEPG[req.user];

    if (cached && (now - cached.lastFetched) < EPG_CACHE_DURATION) {
      console.log(`✓ Returning cached EPG for ${req.user}`);
      res.setHeader('Content-Type', 'application/xml; charset=utf-8');
      return res.send(cached.data);
    }

    console.log(`Fetching fresh EPG for ${req.user}...`);
    const epgData = await fetchUrl(userConfig.epg_url);

    userEPG[req.user] = { data: epgData, lastFetched: now };

    console.log(`✓ EPG loaded for ${req.user} (${(epgData.length / 1024).toFixed(0)} KB)`);
    res.setHeader('Content-Type', 'application/xml; charset=utf-8');
    res.send(epgData);
  } catch (error) {
    console.error(`❌ EPG fetch failed for ${req.user}:`, error.message);
    res.setHeader('Content-Type', 'application/xml; charset=utf-8');
    res.send('<?xml version="1.0" encoding="UTF-8"?><tv></tv>');
  }
});

// Start server and load all users
app.listen(PORT, async () => {
  console.log(`Server running on ${SERVER_URL}`);
  console.log(`API endpoint: ${SERVER_URL}/player_api.php`);
  console.log('');
  await loadAllUsers();
});
