const express = require('express');
const https = require('https');
const http = require('http');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

// IMPORTANT: Set your public URL here
const SERVER_URL = process.env.SERVER_URL || 'https://xtream-bridge.onrender.com';

// Your embedded M3U URL
const M3U_URL = 'https://www.dropbox.com/scl/fi/go509m79v58q86rhmyii4/m3u4u-102864-670937-Playlist.m3u?rlkey=hz4r443sknsa17oqhr4jzk33j&st=pkbymt55&dl=1';

// Your EPG URL
const EPG_URL = 'https://www.dropbox.com/scl/fi/wmt9vxra8pc3t7arprpz5/m3u4u-102864-674859-EPG.xml?rlkey=yfti8u9yqmn1e7z4ed9nnjoxl&st=w312omu0&dl=1';

// Load users
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));
console.log('Loaded users:', Object.keys(users));

// Channels and categories cache
let channels = [];
let categories = [];

// EPG cache
let cachedEPG = null;
let epgLastFetched = 0;
const EPG_CACHE_DURATION = 6 * 60 * 60 * 1000; // 6 hours

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// Logging
app.use((req, res, next) => {
  console.log(`${req.method} ${req.url}`);
  next();
});

// Helper function to fetch URL content
function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;
    
    client.get(url, { 
      headers: { 'User-Agent': 'Mozilla/5.0' }
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetchUrl(res.headers.location).then(resolve).catch(reject);
      }
      
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode}`));
      }
      
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

// Helper function to parse M3U content
function parseM3U(content) {
  if (!content.includes('#EXTM3U')) {
    throw new Error('Invalid M3U file');
  }

  const newChannels = [];
  const newCategories = [];
  const categoryMap = new Map();
  let categoryIdCounter = 1;
  
  const lines = content.split('\n').map(line => line.trim()).filter(line => line);
  
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('#EXTINF')) {
      const extinf = lines[i];
      const url = lines[i + 1] || '';
      
      if (!url || url.startsWith('#')) continue;
      
      let categoryName = 'Uncategorized';
      let groupMatch = extinf.match(/group-title="([^"]*)"/i);
      if (!groupMatch) {
        groupMatch = extinf.match(/group-title=([^\s,]+)/i);
      }
      if (!groupMatch) {
        groupMatch = extinf.match(/tvg-group="([^"]*)"/i);
      }
      if (groupMatch && groupMatch[1]) {
        categoryName = groupMatch[1].trim();
      }
      
      if (!categoryMap.has(categoryName)) {
        categoryMap.set(categoryName, categoryIdCounter++);
        newCategories.push({
          category_id: categoryMap.get(categoryName).toString(),
          category_name: categoryName,
          parent_id: 0
        });
      }
      const categoryId = categoryMap.get(categoryName);
      
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
      
      i++;
    }
  }
  
  return { channels: newChannels, categories: newCategories };
}

// Load M3U on startup
async function loadM3U() {
  try {
    console.log('Fetching M3U from embedded URL...');
    const content = await fetchUrl(M3U_URL);
    const result = parseM3U(content);
    
    channels = result.channels;
    categories = result.categories;
    
    console.log(`✓ Loaded ${channels.length} channels in ${categories.length} categories`);
  } catch (error) {
    console.error('Failed to load M3U:', error.message);
  }
}

// Endpoint to manually reload M3U
app.get('/reload', async (req, res) => {
  await loadM3U();
  res.json({
    success: true,
    channels: channels.length,
    categories: categories.length
  });
});

// Root endpoint
app.get('/', (req, res) => {
  res.send(`
    <h1>Xtream Bridge Server</h1>
    <p>Channels: ${channels.length}</p>
    <p>Categories: ${categories.length}</p>
    <p>Users: ${Object.keys(users).join(', ')}</p>
    <p>EPG: ${cachedEPG ? 'Loaded' : 'Not loaded'}</p>
    <p><a href="/reload">Reload M3U</a></p>
  `);
});

// Authentication middleware - CASE INSENSITIVE
function authenticate(req, res, next) {
  const username = (req.query.username || req.body.username || '').toLowerCase();
  const password = req.query.password || req.body.password;
  
  console.log(`🔐 Auth attempt: username="${username}", password="${password ? '***' : 'MISSING'}"`);
  
  // Find user case-insensitively
  const actualUsername = Object.keys(users).find(u => u.toLowerCase() === username);
  
  if (actualUsername && users[actualUsername] === password) {
    console.log(`✓ Auth success for: ${actualUsername}`);
    req.user = actualUsername;
    next();
  } else {
    console.log(`❌ Auth failed. Available users: ${Object.keys(users).join(', ')}`);
    return res.status(403).json({ 
      user_info: { 
        auth: 0, 
        status: 'Disabled', 
        message: 'Invalid credentials' 
      }
    });
  }
}

// Stream proxy endpoint
app.get('/live/:username/:password/:stream_id', (req, res) => {
  const { username, password, stream_id } = req.params;
  const usernameLower = username.toLowerCase();
  
  // Case-insensitive auth for streams
  const actualUsername = Object.keys(users).find(u => u.toLowerCase() === usernameLower);
  
  if (!actualUsername || users[actualUsername] !== password) {
    console.log('❌ Stream auth failed');
    return res.status(403).send('Invalid credentials');
  }
  
  const cleanStreamId = parseInt(stream_id.replace(/\.(m3u8|ts)$/, ''));
  
  console.log(`🎬 Stream request: User=${actualUsername}, StreamID=${cleanStreamId}`);
  
  const channel = channels.find(ch => ch.stream_id === cleanStreamId);
  
  if (!channel) {
    console.log(`❌ Channel not found: ${cleanStreamId}`);
    return res.status(404).send('Channel not found');
  }
  
  console.log(`✓ Proxying: ${channel.name}`);
  console.log(`  Source: ${channel.direct_source}`);
  
  const streamUrl = channel.direct_source;
  const client = streamUrl.startsWith('https') ? https : http;
  
  const proxyReq = client.get(streamUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Referer': streamUrl
    }
  }, (proxyRes) => {
    console.log(`  Response: ${proxyRes.statusCode}`);
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
    
    proxyRes.on('error', (err) => {
      console.error(`❌ Stream error:`, err.message);
    });
  });
  
  proxyReq.on('error', (err) => {
    console.error(`❌ Proxy error:`, err.message);
    if (!res.headersSent) {
      res.status(500).send('Stream error');
    }
  });
  
  req.on('close', () => {
    proxyReq.destroy();
  });
});

// Xtream API - CRITICAL: This is what IPTV Smarters checks on login
app.get('/player_api.php', authenticate, (req, res) => {
  const action = req.query.action;
  const categoryId = req.query.category_id;
  
  console.log(`📡 API Call: action="${action}", category="${categoryId}", user="${req.user}"`);

  // CRITICAL: Default response when no action (this is the login check)
  if (!action) {
    const response = {
      user_info: {
        username: req.user,
        password: users[req.user],
        message: '',
        auth: 1,
        status: 'Active',
        exp_date: '1767225600',
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
    
    console.log('✓ Sending login response');
    return res.json(response);
  }

  if (action === 'get_live_categories') {
    console.log(`✓ Returning ${categories.length} categories`);
    return res.json(categories);
  }

  if (action === 'get_live_streams') {
    let filtered = categoryId ? channels.filter(ch => ch.category_id === categoryId) : channels;
    console.log(`✓ Returning ${filtered.length} channels`);
    return res.json(filtered);
  }

  if (action === 'get_vod_categories') return res.json([]);
  if (action === 'get_vod_streams') return res.json([]);
  if (action === 'get_series_categories') return res.json([]);
  if (action === 'get_series') return res.json([]);

  console.log(`❓ Unknown action: ${action}`);
  res.json({ error: 'Unknown action' });
});

app.post('/player_api.php', authenticate, (req, res) => {
  req.query = { ...req.query, ...req.body };
  app._router.handle(req, res);
});

// Get M3U file with proxied URLs
app.get('/get.php', authenticate, (req, res) => {
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  const m3uContent = channels.map(ch => {
    const proxyUrl = `${SERVER_URL}/live/${username}/${password}/${ch.stream_id}.m3u8`;
    const cat = categories.find(cat => cat.category_id === ch.category_id);
    return `#EXTINF:-1 tvg-id="${ch.epg_channel_id || ''}" tvg-logo="${ch.stream_icon}" group-title="${cat?.category_name || 'Uncategorized'}",${ch.name}\n${proxyUrl}`;
  }).join('\n');
  
  res.setHeader('Content-Type', 'application/vnd.apple.mpegurl');
  res.send(`#EXTM3U\n${m3uContent}`);
});

// EPG endpoint - fetch from Dropbox
app.get('/xmltv.php', authenticate, async (req, res) => {
  console.log('📺 EPG requested');
  
  try {
    // Check if we have cached EPG that's still fresh
    const now = Date.now();
    if (cachedEPG && (now - epgLastFetched) < EPG_CACHE_DURATION) {
      console.log('✓ Returning cached EPG');
      res.setHeader('Content-Type', 'application/xml');
      return res.send(cachedEPG);
    }
    
    // Fetch fresh EPG
    console.log('Fetching fresh EPG from Dropbox...');
    const epgData = await fetchUrl(EPG_URL);
    
    // Cache it
    cachedEPG = epgData;
    epgLastFetched = now;
    
    console.log(`✓ EPG loaded (${(epgData.length / 1024).toFixed(0)} KB)`);
    res.setHeader('Content-Type', 'application/xml');
    res.send(epgData);
  } catch (error) {
    console.error('❌ EPG fetch failed:', error.message);
    // Return empty EPG on error so it doesn't break the app
    res.setHeader('Content-Type', 'application/xml');
    res.send('<?xml version="1.0" encoding="UTF-8"?><tv></tv>');
  }
});

// Start server and load M3U
app.listen(PORT, async () => {
  console.log(`Server running on ${SERVER_URL}`);
  console.log(`API endpoint: ${SERVER_URL}/player_api.php`);
  console.log('');
  await loadM3U();
});
