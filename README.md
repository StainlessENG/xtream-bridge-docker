
# IPTV Xtream API Bridge

This project converts an M3U playlist into Xtream Codes API format for IPTV Smarters.

## Features
- Xtream API endpoints:
  - `/player_api.php?username=<user>&password=<pass>`
  - `/get.php?username=<user>&password=<pass>&type=m3u_plus&output=m3u8`
- Authentication via `users.json`
- Dynamic M3U parsing from remote URL

## Deployment on Render
1. Push this repo to GitHub.
2. Create a new **Web Service** on Render.
3. Set:
   - Build Command: `npm install`
   - Start Command: `npm start`
4. Done!

## IPTV Smarters Login
- URL: `http://<your-render-domain>`
- Username: from `users.json`
- Password: from `users.json`
