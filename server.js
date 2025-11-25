const express = require('express');
const https = require('https');
const http = require('http');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

// IMPORTANT: Set your public URL here
const SERVER_URL = process.env.SERVER_URL || 'https://xtream-bridge.onrender.com';

// Load users with their individual M3U and EPG URLs
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));
console.log('Loaded users:', Object.keys(users));

// Per-user channels and categories cache
const userChannels = {}; // username -> channels array
const userCategories = {}; // username -> categories array

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
  if (!users[username]) {
    return res.status(404).send('User not found');
  }
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
      loadUserM3U(actualUsername).then(() => {
        next();
      }).catch(err => {
        console.error(`Failed to load M3U for ${actualUsername}:`, err);
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

// Stream proxy endpoint
app.get('/live/:username/:password/:stream_id', (req, res) => {
  const { username, password, stream_id } = req.params;
  const usernameLower = username.toLowerCase();
  
  // Case-insensitive auth for streams
  const actualUsername = Object.keys(users).find(u => u.toLowerCase() === usernameLower);
  
  if (!actualUsername || users[actualUsername].password !== password) {
    console.log('❌ Stream auth failed');
    return res.status(403).send('Invalid credentials');
  }
  
  const cleanStreamId = parseInt(stream_id.replace(/\.(m3u8|ts)$/, ''));
  
  console.log(`🎬 Stream request: User=${actualUsername}, StreamID=${cleanStreamId}`);
  
  const channels = userChannels[actualUsername] || [];
  const channel = channels.find(ch => ch.stream_id === cleanStreamId);
  
  if (!channel) {
    console.log(`❌ Channel not found: ${cleanStreamId}`);
    return res.status(404).send('Channel not found');
  }
  
  console.log(`✓ Proxying: ${channel.name}`);
  
  const streamUrl = channel.direct_source;
  const client = streamUrl.startsWith('https') ? https : http;
  
  const proxyReq = client.get(streamUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Referer': streamUrl
    }
  }, (proxyRes) => {
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
    
    console.log(`✓ Sending login response for ${req.user}`);
    return res.json(response);
  }

  if (action === 'get_live_categories') {
    console.log(`✓ Returning ${categories.length} categories for ${req.user}`);
    return res.json(categories);
  }

  if (action === 'get_live_streams') {
    let filtered = categoryId ? channels.filter(ch => ch.category_id === categoryId) : channels;
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

// Get M3U file with proxied URLs
app.get('/get.php', authenticate, (req, res) => {
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  const channels = userChannels[req.user] || [];
  const categories = userCategories[req.user] || [];
  
  const m3uContent = channels.map(ch => {
    const proxyUrl = `${SERVER_URL}/live/${username}/${password}/${ch.stream_id}.m3u8`;
    const cat = categories.find(cat => cat.category_id === ch.category_id);
    return `#EXTINF:-1 tvg-id="${ch.epg_channel_id || ''}" tvg-logo="${ch.stream_icon}" group-title="${cat?.category_name || 'Uncategorized'}",${ch.name}\n${proxyUrl}`;
  }).join('\n');
  
  res.setHeader('Content-Type', 'application/vnd.apple.mpegurl');
  res.send(`#EXTM3U\n${m3uContent}`);
});

// EPG endpoint - per user
app.get('/xmltv.php', authenticate, async (req, res) => {
  console.log(`📺 EPG requested for ${req.user}`);
  
  try {
    const userConfig = users[req.user];
    if (!userConfig || !userConfig.epg_url) {
      console.log(`No EPG URL configured for ${req.user}`);
      res.setHeader('Content-Type', 'application/xml');
      return res.send('<?xml version="1.0" encoding="UTF-8"?><tv></tv>');
    }

    // Check if we have cached EPG that's still fresh
    const now = Date.now();
    const cached = userEPG[req.user];
    
    if (cached && (now - cached.lastFetched) < EPG_CACHE_DURATION) {
      console.log(`✓ Returning cached EPG for ${req.user}`);
      res.setHeader('Content-Type', 'application/xml');
      return res.send(cached.data);
    }
    
    // Fetch fresh EPG
    console.log(`Fetching fresh EPG for ${req.user}...`);
    const epgData = await fetchUrl(userConfig.epg_url);
    
    // Cache it
    userEPG[req.user] = {
      data: epgData,
      lastFetched: now
    };
    
    console.log(`✓ EPG loaded for ${req.user} (${(epgData.length / 1024).toFixed(0)} KB)`);
    res.setHeader('Content-Type', 'application/xml');
    res.send(epgData);
  } catch (error) {
    console.error(`❌ EPG fetch failed for ${req.user}:`, error.message);
    res.setHeader('Content-Type', 'application/xml');
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
