
from fastapi import FastAPI, Query
import requests
from fastapi.responses import PlainTextResponse

app = FastAPI()

M3U_URL = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"
EPG_URL = "http://m3u4u.com/xml/p87vnr8dzdu4w2q6n41j"

USERNAME = "John"
PASSWORD = "Sidford2025"

@app.get("/player_api.php")
def player_api(username: str = Query(...), password: str = Query(...)):
    if username != USERNAME or password != PASSWORD:
        return {"user_info": {"auth": 0, "status": "Failed"}}

    # Fetch playlist
    response = requests.get(M3U_URL)
    if response.status_code != 200:
        return {"error": "Failed to fetch playlist"}

    lines = response.text.splitlines()
    channels = []
    for i in range(len(lines)):
        if lines[i].startswith("#EXTINF"):
            name = lines[i].split(",")[-1]
            url = lines[i+1] if i+1 < len(lines) else ""
            channels.append({
                "name": name,
                "stream_id": i,
                "stream_type": "live",
                "stream_url": url
            })

    return {
        "user_info": {
            "auth": 1,
            "username": username,
            "password": password,
            "status": "Active"
        },
        "server_info": {
            "url": "https://your-render-domain.onrender.com",
            "port": 443,
            "https": True
        },
        "available_channels": channels
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
