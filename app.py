const express = require('express');
const axios = require('axios');
const fs = require('fs');
const https = require('https');
const http = require('http');

const app = express();
const PORT = process.env.PORT || 3000;
const SERVER_URL = process.env.SERVER_URL || 'https://xtream-bridge.onrender.com';

// Load users - now expects this format:
// { "username": "password", ... }
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));

// Your M3U link
const M3U_URL = 'http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721it';

// Cache for channels
let channels = [];
let categories = [];

// Helper function to fetch URL content
function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;
    
    client.get(url, { 
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 10000
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

// Parse M3U content
function parseM3U(content) {
  const lines = content.split('\n').map(line => line.trim());
  const parsedChannels = [];
  const parsedCategories = [];
  const categoryMap = new Map();
  let categoryId = 1;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    if (line.startsWith('#EXTINF:')) {
      const extinf = line;
      const url = lines[i + 1];
      
      if (!url || url.startsWith('#')) continue;
      
      // Extract category
      let categoryName = 'Uncategorized';
      const groupMatch = extinf.match(/group-title="([^"]*)"/i);
      if (groupMatch && groupMatch[1]) {
        categoryName = groupMatch[1].trim();
      }
      
      // Add category if new
      if (!categoryMap.has(categoryName)) {
        categoryMap.set(categoryName, categoryId);
        parsedCategories.push({
          category_id: categoryId.toString(),
          category_name: categoryName,
          parent_id: 0
        });
        categoryId++;
      }
      
      // Extract channel name
      const nameParts = extinf.split(',');
      const channelName = nameParts[nameParts.length - 1].trim() || `Channel ${parsedChannels.length + 1}`;
      
      // Extract logo
      const logoMatch = extinf.match(/tvg-logo="([^"]*)"/i);
      const logo = logoMatch ? logoMatch[1] : '';
      
      const streamId = parsedChannels.length + 1;
      
      parsedChannels.push({
        num: streamId,
        name: channelName,
        stream_id: streamId,
        stream_type: 'live',
        stream_icon: logo,
        epg_channel_id: '',
        added: Math.floor(Date.now() / 1000).toString(),
        category_id: categoryMap.get(categoryName).toString(),
        custom_sid: '',
        tv_archive: 0,
        direct_source: url,
        tv_archive_duration: 0
      });
      
      i++; // Skip the URL line
    }
  }
  
  return { channels: parsedChannels, categories: parsedCategories };
}

// Fetch and parse M3U
async function loadPlaylist() {
  try {
    console.log('Fetching M3U playlist...');
    const response = await axios.get(M3U_URL);
    const result = parseM3U(response.data);
    
    channels = result.channels;
    categories = result.categories;
    
    console.log(`✓ Loaded ${channels.length} channels in ${categories.length} categories`);
  } catch (error) {
    console.error('❌ Error loading playlist:', error.message);
  }
}

// Authentication middleware
function authenticate(req, res, next) {
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  // Handle both old format (users[username] === password) 
  // and new format (users[username].password === password)
  const userConfig = users[username];
  const isValid = userConfig && (
    userConfig === password || // Old format
    userConfig.password === password // New format
  );
  
  if (isValid) {
    req.user = username;
    next();
  } else {
    res.status(403).json({ 
      user_info: {
        auth: 0,
        status: 'Disabled',
        message: 'Invalid credentials'
      }
    });
  }
}

// Stream proxy endpoint - THIS IS THE FIX!
app.get('/live/:username/:password/:stream_id', async (req, res) => {
  const { username, password, stream_id } = req.params;
  
  // Authenticate
  const userConfig = users[username];
  const isValid = userConfig && (
    userConfig === password || 
    userConfig.password === password
  );
  
  if (!isValid) {
    console.log('❌ Stream auth failed');
    return res.status(403).send('Invalid credentials');
  }
  
  const cleanStreamId = parseInt(stream_id.replace(/\.(m3u8|ts)$/, ''));
  
  console.log(`🎬 Stream request: User=${username}, StreamID=${cleanStreamId}`);
  
  const channel = channels.find(ch => ch.stream_id === cleanStreamId);
  
  if (!channel) {
    console.log(`❌ Channel not found: ${cleanStreamId}`);
    return res.status(404).send('Channel not found');
  }
  
  console.log(`✓ Proxying: ${channel.name}`);
  console.log(`   Source: ${channel.direct_source}`);
  
  const streamUrl = channel.direct_source;
  
  // If it's an M3U8 file, rewrite the URLs inside it
  if (streamUrl.includes('.m3u8') || stream_id.endsWith('.m3u8')) {
    try {
      // Fetch the M3U8 content
      const m3u8Content = await fetchUrl(streamUrl);
      
      // Parse the base URL for relative paths
      const urlObj = new URL(streamUrl);
      const baseUrl = `${urlObj.protocol}//${urlObj.host}${urlObj.pathname.substring(0, urlObj.pathname.lastIndexOf('/'))}`;
      
      // Rewrite the M3U8 content - convert relative URLs to absolute
      const lines = m3u8Content.split('\n');
      const rewrittenLines = lines.map(line => {
        const trimmed = line.trim();
        
        // Skip comments and empty lines
        if (trimmed.startsWith('#') || !trimmed) {
          return line;
        }
        
        // If it's already a full URL, leave it
        if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
          return line;
        }
        
        // Convert relative URL to absolute
        const absoluteUrl = trimmed.startsWith('/') 
          ? `${urlObj.protocol}//${urlObj.host}${trimmed}`
          : `${baseUrl}/${trimmed}`;
        
        return absoluteUrl;
      });
      
      const rewrittenContent = rewrittenLines.join('\n');
      
      console.log(`✓ Rewrote M3U8 manifest for ${channel.name}`);
      
      res.setHeader('Content-Type', 'application/vnd.apple.mpegurl');
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.send(rewrittenContent);
      
    } catch (error) {
      console.error(`❌ M3U8 rewrite error:`, error.message);
      
      // Fallback: redirect to original URL
      console.log(`⚠️ Falling back to direct redirect`);
      res.redirect(streamUrl);
    }
  } else {
    // For non-M3U8 streams (TS chunks, etc), proxy directly
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
  }
});

// Xtream API: player_api.php
app.get('/player_api.php', authenticate, (req, res) => {
  const action = req.query.action;
  const categoryId = req.query.category_id;
  
  console.log(`📡 API Call: action="${action}", user="${req.user}"`);

  // Default response (login check)
  if (!action) {
    const userConfig = users[req.user];
    const userPassword = userConfig.password || userConfig;
    
    return res.json({
      user_info: {
        username: req.user,
        password: userPassword,
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
        url: SERVER_URL.replace(/^https?:\/\//, ''),
        port: '443',
        https_port: '443',
        server_protocol: 'https',
        rtmp_port: '1935',
        timezone: 'UTC',
        timestamp_now: Math.floor(Date.now() / 1000)
      }
    });
  }

  if (action === 'get_live_categories') {
    console.log(`✓ Returning ${categories.length} categories`);
    return res.json(categories);
  }

  if (action === 'get_live_streams') {
    let filtered = categoryId 
      ? channels.filter(ch => ch.category_id === categoryId) 
      : channels;
    console.log(`✓ Returning ${filtered.length} channels`);
    return res.json(filtered);
  }

  if (action === 'get_vod_categories') return res.json([]);
  if (action === 'get_vod_streams') return res.json([]);
  if (action === 'get_series_categories') return res.json([]);
  if (action === 'get_series') return res.json([]);

  res.json({ error: 'Unknown action' });
});

// Xtream API: get.php (returns M3U with proxied URLs)
app.get('/get.php', authenticate, (req, res) => {
  const username = req.query.username || req.body.username;
  const password = req.query.password || req.body.password;
  
  const m3uContent = channels.map(ch => {
    const proxyUrl = `${SERVER_URL}/live/${username}/${password}/${ch.stream_id}.m3u8`;
    const cat = categories.find(cat => cat.category_id === ch.category_id);
    return `#EXTINF:-1 tvg-id="" tvg-logo="${ch.stream_icon}" group-title="${cat?.category_name || 'Uncategorized'}",${ch.name}\n${proxyUrl}`;
  }).join('\n');
  
  res.setHeader('Content-Type', 'application/vnd.apple.mpegurl');
  res.send(`#EXTM3U\n${m3uContent}`);
});

// Root endpoint
app.get('/', (req, res) => {
  res.send(`
    <h1>Xtream Bridge Server</h1>
    <p>Channels loaded: ${channels.length}</p>
    <p>Categories: ${categories.length}</p>
    <p><a href="/reload">Reload Playlist</a></p>
  `);
});

// Reload endpoint
app.get('/reload', async (req, res) => {
  await loadPlaylist();
  res.send('<h2>Playlist reloaded!</h2><a href="/">Back</a>');
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    channels: channels.length,
    categories: categories.length,
    uptime: process.uptime()
  });
});

// Start server and load playlist
app.listen(PORT, async () => {
  console.log(`
╔════════════════════════════════════════════╗
║   Xtream Bridge Server                     ║
║   Running on ${SERVER_URL}                 ║
╚════════════════════════════════════════════╝
  `);
  
  await loadPlaylist();
  
  // Reload playlist every 6 hours
  setInterval(loadPlaylist, 6 * 60 * 60 * 1000);
  
  console.log(`✓ Server ready!`);
});
