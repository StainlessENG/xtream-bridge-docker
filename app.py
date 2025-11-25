
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
import requests
import time
from datetime import datetime
import re

app = FastAPI()

M3U_URL = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"
EPG_URL = "http://m3u4u.com/xml/p87vnr8dzdu4w2q6n41j"

USERNAME = "John"
PASSWORD = "Sidford2025"

@app.get("/player_api.php")
def player_api(username: str, password: str, action: str = None):
    if username != USERNAME or password != PASSWORD:
        return {"user_info": {"auth": 0, "status": "Failed"}}

    response = requests.get(M3U_URL, timeout=30)
    if response.status_code != 200:
        return {"error": "Failed to fetch playlist"}

    lines = response.text.splitlines()
    channels = []
    categories_map = {}
    category_counter = 1

    for i in range(len(lines)):
        if lines[i].startswith("#EXTINF"):
            name = lines[i].split(",")[-1]
            match = re.search(r'group-title="([^"]+)"', lines[i])
            category_name = match.group(1) if match else "Other"

            if category_name not in categories_map:
                categories_map[category_name] = str(category_counter)
                category_counter += 1

            category_id = categories_map[category_name]
            url = lines[i+1].strip() if i+1 < len(lines) else ""

            channels.append({
                "num": i,
                "name": name,
                "stream_type": "live",
                "stream_id": i,
                "stream_icon": "",
                "epg_channel_id": "",
                "added": str(int(time.time())),
                "category_id": category_id,
                "custom_sid": "",
                "tv_archive": 0,
                "direct_source": url,
                "url": f"https://xtream-bridge.onrender.com/live/{USERNAME}/{PASSWORD}/{i}.m3u8"
            })

    categories = [{"category_id": cid, "category_name": cname, "parent_id": 0}
                  for cname, cid in categories_map.items()]

    if action == "get_live_categories":
        return categories
    elif action == "get_live_streams":
        return channels
    else:
        return {
            "user_info": {
                "username": username,
                "password": password,
                "auth": 1,
                "status": "Active",
                "exp_date": "0000-00-00 00:00:00",
                "is_trial": "0",
                "active_cons": "1",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "max_connections": "1"
            },
            "server_info": {
                "url": "xtream-bridge.onrender.com",
                "port": "443",
                "https": True,
                "server_protocol": "https",
                "rtmp_port": "8000",
                "timezone": "Europe/London",
                "timestamp_now": int(time.time())
            }
        }

@app.get("/get.php", response_class=PlainTextResponse)
def get_m3u(username: str, password: str, type: str = "m3u"):
    if username != USERNAME or password != PASSWORD:
        return "#EXTM3U\n# Authentication Failed"
    return requests.get(M3U_URL).text

@app.get("/xmltv.php", response_class=PlainTextResponse)
def get_epg(username: str, password: str):
    if username != USERNAME or password != PASSWORD:
        return "<xmltv></xmltv>"
    return requests.get(EPG_URL).text

@app.get("/live/{username}/{password}/{stream_id}.m3u8")
def proxy_hls_playlist(username: str, password: str, stream_id: int):
    if username != USERNAME or password != PASSWORD:
        return PlainTextResponse("Authentication Failed", status_code=403)

    response = requests.get(M3U_URL, timeout=30)
    lines = response.text.splitlines()
    urls = [lines[i+1].strip() for i in range(len(lines)) if lines[i].startswith("#EXTINF")]

    if stream_id >= len(urls):
        return PlainTextResponse("Stream Not Found", status_code=404)

    stream_url = urls[stream_id]
    # Proxy the HLS playlist
    r = requests.get(stream_url)
    return PlainTextResponse(r.text, media_type="application/vnd.apple.mpegurl")
