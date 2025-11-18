const express = require('express');
const axios = require('axios');
const app = express();

const PORT = process.env.PORT || 3000;
const M3U_URL = process.env.M3U_URL || '';

// Multi-user support
const USERS = {
  "dad": "devon",
  "john": "pass123",
  "John": "Sidford2025",
  "mark": "Sidmouth2025",
  "james": "October2025",
  "ian": "October2025",
  "harry": "October2025",
  "main": "admin"
};

let channels = [];
let categories = [];

// Parse M3U file
async function parseM3U() {
  try {
    const response = await axios.get(M3U_URL);
    const content = response.data;
    const lines = content.split('\n');
    
    channels = [];
    categories = new Set();
    let currentChannel = {};

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      
      if (line.startsWith('#EXTINF:')) {
        const nameMatch = line.match(/,(.+)$/);
        const groupMatch = line.match(/group-title="([^"]+)"/);
        const logoMatch = line.match(/tvg-logo="([^"]+)"/);
        const idMatch = line.match(/tvg-id="([^"]+)"/);
        
        currentChannel = {
          num: channels.length + 1,
          name: nameMatch ? nameMatch[1].trim() : `Channel ${channels.length + 1}`,
          stream_type: 'live',
          stream_id: channels.length + 1,
          stream_icon: logoMatch ? logoMatch[1] : '',
          epg_channel_id: idMatch ? idMatch[1] : '',
          category_name: groupMatch ? groupMatch[1] : 'Uncategorized',
          category_id: 1
        };
        
        if (currentChannel.category_name) {
          categories.add(currentChannel.category_name);
        }
      } else if (line && !line.startsWith('#') && currentChannel.name) {
        currentChannel.url = line;
        channels.push({...currentChannel});
        currentChannel = {};
      }
    }

    // Create categories array
    categories = Array.from(categories).map((cat, idx) => ({
      category_id: idx + 1,
      category_name: cat,
      parent_id: 0
    }));

    console.log(`Parsed ${channels.length} channels in ${categories.length} categories`);
  } catch (error) {
    console.error('Error parsing M3U:', error.message);
  }
}

// Auth check middleware
function checkAuth(req, res, next) {
  const { username, password } = req.query;
  if (USERS[username] && USERS[username] === password) {
    req.authUser = username;
    next();
  } else {
    res.json({ user_info: { auth: 0, status: 'Invalid credentials' } });
  }
}

// Player API endpoint (main Xtream API)
app.get('/player_api.php', checkAuth, (req, res) => {
  const { action } = req.query;

  switch (action) {
    case 'get_live_categories':
      res.json(categories);
      break;

    case 'get_live_streams':
      const categoryId = req.query.category_id;
      const filtered = categoryId 
        ? channels.filter(ch => ch.category_id == categoryId)
        : channels;
      res.json(filtered);
      break;

    case 'get_vod_categories':
      res.json([]);
      break;

    case 'get_vod_streams':
      res.json([]);
      break;

    case 'get_series_categories':
      res.json([]);
      break;

    case 'get_series':
      res.json([]);
      break;

    default:
      // Authentication response
      res.json({
        user_info: {
          username: req.authUser,
          password: USERS[req.authUser],
          auth: 1,
          status: 'Active',
          exp_date: '1893456000',
          is_trial: '0',
          active_cons: '1',
          created_at: '1609459200',
          max_connections: '1',
          allowed_output_formats: ['m3u8', 'ts']
        },
        server_info: {
          url: req.protocol + '://' + req.get('host'),
          port: PORT,
          https_port: PORT,
          server_protocol: req.protocol,
          rtmp_port: '1935',
          timestamp_now: Math.floor(Date.now() / 1000)
        }
      });
  }
});

// Stream endpoint
app.get('/live/:username/:password/:streamId.:format?', (req, res) => {
  const { username, password, streamId } = req.params;
  
  if (!USERS[username] || USERS[username] !== password) {
    return res.status(403).send('Unauthorized');
  }

  const channel = channels.find(ch => ch.stream_id == streamId);
  if (channel) {
    res.redirect(channel.url);
  } else {
    res.status(404).send('Stream not found');
  }
});

// Health check for Render
app.get('/health', (req, res) => {
  res.json({ status: 'ok', channels: channels.length });
});

// Initialize
async function init() {
  if (!M3U_URL) {
    console.error('ERROR: M3U_URL environment variable not set');
    process.exit(1);
  }

  await parseM3U();
  
  // Refresh M3U every 6 hours
  setInterval(parseM3U, 6 * 60 * 60 * 1000);

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Xtream API server running on port ${PORT}`);
    console.log(`Server URL: http://localhost:${PORT}`);
  });
}

init();