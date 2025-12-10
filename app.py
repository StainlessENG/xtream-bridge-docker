const express = require('express');
const axios = require('axios');
const fs = require('fs');
const M3UParser = require('m3u-parser');
const app = express();
const PORT = process.env.PORT || 3000;
// ------------------------------
// Load users
// ------------------------------
const users = JSON.parse(fs.readFileSync('users.json', 'utf8'));
// Your Dropbox M3U URL
const M3U_URL = 'http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721it';
// Cache for channels
let channels = [];
// ---------------------------------------------------
// Load Playlist + Replace Tiny Pop ONLY
// ---------------------------------------------------
async function loadPlaylist() {
  try {
    const response = await axios.get(M3U_URL);
    const parser = new M3UParser();
    parser.read(response.data);
    channels = parser.getItems().map((item, index) => {
      let url = item.url;
      const lower = item.name.toLowerCase();
      // Replace any Tiny Pop variant
      if (
        lower.includes("tiny pop") ||
        lower.includes("tinypop") ||
        lower.includes("tiny-pop")
      ) {
        url = `https://xtream-bridge.onrender.com/tinypop`;
      }
      return {
        name: item.name,
        stream_id: index + 1,
        stream_type: 'live',
        stream_url: url
      };
    });
    console.log(`Loaded ${channels.length} channels (Tiny Pop replaced)`);
  } catch (error) {
    console.error('Error loading playlist:', error.message);
  }
}
// ------------------------------
// Authentication middleware
// ------------------------------
function authenticate(req, res, next) {
  const { username, password } = req.query;
  if (users[username] && users[username] === password) {
    req.user = username;
    next();
  } else {
    res.status(403).json({ error: 'Invalid credentials' });
  }
}
// ------------------------------
// Xtream API: /player_api.php
// ------------------------------
app.get('/player_api.php', authenticate, (req, res) => {
  res.json({
    user_info: {
      username: req.user,
      password: users[req.user],
      auth: 1,
      status: "Active"
    },
    server_info: {
      url: req.hostname,
      port: PORT,
      https_port: 443,
      server_protocol: "http"
    },
    available_channels: channels
  });
});
// ------------------------------
// Xtream API: /get.php (M3U)
// ------------------------------
app.get('/get.php', authenticate, (req, res) => {
  const m3uContent = channels.map(ch => {
    return `#EXTINF:-1,${ch.name}\n${ch.stream_url}`;
  }).join("\n");
  res.setHeader("Content-Type", "application/vnd.apple.mpegurl");
  res.send(`#EXTM3U\n${m3uContent}`);
});
// ---------------------------------------------------
// TINY POP PROXY (simple — master only)
// ---------------------------------------------------
const TINYPOP_MASTER =
  "https://live-pop-ssai.simplestreamcdn.com/v1/master/774d979dd66704abea7c5b62cb34c6815fda0d35/narrative-tinypop-live-amagi/playlist.m3u8";
app.get("/tinypop", async (req, res) => {
  try {
    const response = await axios.get(TINYPOP_MASTER, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
      }
    });
    res.setHeader("Content-Type", "application/vnd.apple.mpegurl");
    res.send(response.data);
  } catch (err) {
    console.error("TinyPop Proxy Error:", err.message);
    res.status(500).send('#EXTM3U');
  }
});
// ------------------------------
// Start Server
// ------------------------------
app.listen(PORT, async () => {
  console.log(`Server running on port ${PORT}`);
  await loadPlaylist();
});
