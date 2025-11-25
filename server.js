const express = require('express');
const https = require('https');
const http = require('http');
const fs = require('fs');
const { URL } = require('url');

const app = express();
const PORT = process.env.PORT || 3000;

// IMPORTANT: Set your public URL here (use your Render URL)
const SERVER_URL = process.env.SERVER_URL || 'https://xtream-bridge.onrender.com';

// Your embedded M3U URL
const M3U_URL = 'https://www.dropbox.com/scl/fi/h08dacb55k2aj1ufa3u62/m3u4u-102864-675597-Playlist.m3u?rlkey=0od89zpnmj69nj9fgo4280u9m&st=daeu5phc&dl=1';

// Load users
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));

// Channels and categories cache
let channels = [];
let categories = [];

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
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
      // Handle redirects
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        console.log(`Redirecting to: ${res.headers.location}`);
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
      
      // Extract category
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
      
      // Get or create category
      if (!categoryMap.has(categoryName)) {
        categoryMap.set(categoryName, categoryIdCounter++);
        newCategories.push({
          category_id: categoryMap.get(categoryName).toString(),
          category_name: categoryName,
          parent_id: 0
        });
      }
      const categoryId = categoryMap.get(categoryName);
      
      // Extract channel name
      const nameParts = extinf.split(',');
      const channelName = nameParts[nameParts.length - 1].trim() || `Channel ${newChannels.length + 1}`;
      
      // Extract other attributes
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
    categories.forEach(cat => {
      const count = channels.filter(ch => ch.category_id === cat.category_id).length;
      console.log(`  - ${cat.category_name}: ${count} channels`);
    });
  } catch (error) {
    console.error('Failed to load M3U:', error.message);
    console.log('Server will start but no channels will be available until M3U is loaded.');
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
    <p><a href="/reload">Reload M3U</a></p>
  `);
});

// Authentication middleware
function authenticate(req, res, next) {
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  if (users[username] && users[username] === password) {
    req.user = username;
    next();
  } else {
    res.status(403).json({ 
      user_info: { auth: 0, status: 'Disabled', message: 'Invalid credentials' }
    });
  }
}

// Stream proxy endpoint - handles both .m3u8 and .ts requests
app.get('/live/:username/:password/:stream_id', (req, res) => {
  const { username, password, stream_id } = req.params;
  
  // Authenticate
  if (!users[username] || users[username] !== password) {
    console.log('Stream auth failed');
    return res.status(403).send('Invalid credentials');
  }
  
  // Extract numeric stream ID
  const cleanStreamId = parseInt(stream_id.replace(/\.(m3u8|ts)$/, ''));
  
  console.log(`🎬 Stream request: User=${username}, StreamID=${cleanStreamId}`);
  
  // Find channel
  const channel = channels.find(ch => ch.stream_id === cleanStreamId);
  
  if (!channel) {
    console.log(`❌ Channel not found: ${cleanStreamId}`);
    return res.status(404).send('Channel not found');
  }
  
  console.log(`✓ Proxying: ${channel.name}`);
  console.log(`  Source: ${channel.direct_source}`);
  
  // Proxy the stream
  const streamUrl = channel.direct_source;
  const client = streamUrl.startsWith('https') ? https : http;
  
  const proxyReq = client.get(streamUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Referer': streamUrl
    }
  }, (proxyRes) => {
    console.log(`  Response: ${proxyRes.statusCode}`);
    
    // Forward status code and headers
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    
    // Pipe the stream
    proxyRes.pipe(res);
    
    proxyRes.on('error', (err) => {
      console.error(`❌ Stream error for ${channel.name}:`, err.message);
    });
  });
  
  proxyReq.on('error', (err) => {
    console.error(`❌ Proxy error for ${channel.name}:`, err.message);
    if (!res.headersSent) {
      res.status(500).send('Stream error');
    }
  });
  
  // Handle client disconnect
  req.on('close', () => {
    proxyReq.destroy();
  });
});

// Xtream API
app.get('/player_api.php', authenticate, (req, res) => {
  const action = req.query.action;
  const categoryId = req.query.category_id;
  
  console.log(`Action: ${action}, Category: ${categoryId}`);

  if (!action) {
    const serverUrl = SERVER_URL || `http://${req.hostname}:${PORT}`;
    return res.json({
      user_info: {
        username: req.user,
        password: users[req.user],
        auth: 1,
        status: 'Active',
        exp_date: Math.floor(Date.now() / 1000) + (365 * 24 * 60 * 60),
        is_trial: '0',
        active_cons: '0',
        created_at: Math.floor(Date.now() / 1000),
        max_connections: '1'
      },
      server_info: {
        url: serverUrl,
        port: PORT.toString(),
        https_port: '443',
        server_protocol: serverUrl.startsWith('https') ? 'https' : 'http',
        rtmp_port: '1935',
        timestamp_now: Math.floor(Date.now() / 1000)
      }
    });
  }

  if (action === 'get_live_categories') {
    console.log(`Returning ${categories.length} categories`);
    return res.json(categories);
  }

  if (action === 'get_live_streams') {
    let filtered = categoryId ? channels.filter(ch => ch.category_id === categoryId) : channels;
    console.log(`Returning ${filtered.length} channels`);
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
  const serverUrl = SERVER_URL || `http://${req.hostname}:${PORT}`;
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  const m3uContent = channels.map(ch => {
    const proxyUrl = `${serverUrl}/live/${username}/${password}/${ch.stream_id}.m3u8`;
    return `#EXTINF:-1 tvg-id="${ch.epg_channel_id || ''}" tvg-logo="${ch.stream_icon}" group-title="${categories.find(cat => cat.category_id === ch.category_id)?.category_name || 'Uncategorized'}",${ch.name}\n${proxyUrl}`;
  }).join('\n');
  
  res.setHeader('Content-Type', 'application/vnd.apple.mpegurl');
  res.send(`#EXTM3U\n${m3uContent}`);
});

// EPG endpoint (stub)
app.get('/xmltv.php', authenticate, (req, res) => {
  console.log('EPG requested (returning empty)');
  res.setHeader('Content-Type', 'application/xml');
  res.send('<?xml version="1.0" encoding="UTF-8"?><tv></tv>');
});

// Start server and load M3U
app.listen(PORT, async () => {
  console.log(`Server running on ${SERVER_URL || `http://localhost:${PORT}`}`);
  console.log(`API endpoint: ${SERVER_URL || `http://localhost:${PORT}`}/player_api.php`);
  console.log(`Stream format: /live/{username}/{password}/{stream_id}.m3u8`);
  console.log(`Reload M3U: ${SERVER_URL || `http://localhost:${PORT}`}/reload`);
  console.log('');
  await loadM3U();
});
