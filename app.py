
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
import requests
import time
from datetime import datetime
import re

app = FastAPI()

# Your playlist and EPG URLs
M3U_URL = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"
EPG_URL = "http://m3u4u.com/xml/p87vnr8dzdu4w2q6n41j"

# Credentials
USERNAME = "John"
PASSWORD = "Sidford2025"

@app.get("/player_api.php")
def player_api(username: str, password: str):
    if username != USERNAME or password != PASSWORD:
        return {"user_info": {"auth": 0, "status": "Failed"}}

    # Fetch playlist
    response = requests.get(M3U_URL)
    if response.status_code != 200:
        return {"error": "Failed to fetch playlist"}

    lines = response.text.splitlines()
    channels = []
    categories_map = {}
    category_counter = 1

    for i in range(len(lines)):
        if lines[i].startswith("#EXTINF"):
            # Extract channel name
            name = lines[i].split(",")[-1]

            # Extract group-title
            match = re.search(r'group-title="([^"]+)"', lines[i])
            category_name = match.group(1) if match else "Other"

            # Assign category_id
            if category_name not in categories_map:
                categories_map[category_name] = str(category_counter)
                category_counter += 1

            category_id = categories_map[category_name]

            # Channel URL
            url = lines[i+1] if i+1 < len(lines) else ""

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
                "direct_source": url
            })

    # Build categories list
    categories = [{"category_id": cid, "category_name": cname, "parent_id": 0}
                  for cname, cid in categories_map.items()]

    return {
        "user_info": {
            "username": username,
            "password": password,
            "message": "",
            "auth": 1,
            "status": "Active",
            "exp_date": "0000-00-00 00:00:00",
            "is_trial": "0",
            "active_cons": "1",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "max_connections": "1"
        },
        "server_info": {
            "url": "your-render-domain.onrender.com",
            "port": "443",
            "https": True,
            "server_protocol": "https",
            "rtmp_port": "8000",
            "timezone": "Europe/London",
            "timestamp_now": int(time.time())
        },
        "categories": categories,
        "available_channels": channels,
        "available_movies": [],
        "available_series": []
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
