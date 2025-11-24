import requests
from flask import Flask, request, redirect, jsonify, Response

app = Flask(**name**)

# –––––––– USERS ––––––––

USERS = {
“dad”: “devon”,
“john”: “pass123”,
“John”: “Sidford2025”,
“mark”: “Sidmouth2025”,
“james”: “October2025”,
“ian”: “October2025”,
“harry”: “October2025”,
“main”: “admin”
}

# –––––––– PLAYLIST MAP ––––––––

PLAYLISTS = {
“john”: “http://m3u4u.com/m/m73wp7qe3es9qvmpjk9x”,
“John”: “http://m3u4u.com/m/m73wp7qe3es9qvmpjk9x”,
“main”: “http://m3u4u.com/m3u/p87vnr8dzdu4w2q6n41j”,
}

DEFAULT_PLAYLIST = “http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721”

# –––––––– HELPERS ––––––––

def get_playlist(username):
return PLAYLISTS.get(username, DEFAULT_PLAYLIST)

def auth_ok(username, password):
return username in USERS and USERS[username] == password

# –––––––– ROUTES ––––––––

@app.route(”/”)
def home():
return “Xtream Bridge Running”

# XTREAM API LOGIN - Handle both GET and POST

@app.route(”/player_api.php”, methods=[“GET”, “POST”])
def player_api():
# Get credentials from either GET params or POST form
if request.method == “POST”:
username = request.form.get(“username”, “”)
password = request.form.get(“password”, “”)
action = request.form.get(“action”, “”)
else:
username = request.args.get(“username”, “”)
password = request.args.get(“password”, “”)
action = request.args.get(“action”, “”)

```
if not auth_ok(username, password):
    return jsonify({"user_info": {"auth": 0}})

# Handle category requests
if action == "get_live_categories":
    return jsonify([
        {"category_id": "1", "category_name": "Live", "parent_id": 0}
    ])

if action == "get_live_streams":
    # Return empty list - streams come from M3U
    return jsonify([])

if action == "get_vod_categories":
    return jsonify([])

if action == "get_series_categories":
    return jsonify([])

# Default response - login info
playlist = get_playlist(username)

return jsonify({
    "user_info": {
        "auth": 1,
        "username": username,
        "password": password,
        "status": "Active",
        "exp_date": "1999999999",
        "is_trial": "0",
        "active_cons": "0",
        "created_at": "1640000000",
        "max_connections": "1"
    },
    "server_info": {
        "url": request.host,
        "port": "80",
        "https_port": "443",
        "server_protocol": "http",
        "rtmp_port": "1935",
        "timezone": "UTC",
        "timestamp_now": 1640000000
    }
})
```

# — M3U REDIRECT —

@app.route(”/get.php”)
def get_php():
username = request.args.get(“username”, “”)
password = request.args.get(“password”, “”)

```
if not auth_ok(username, password):
    return "Auth Failed", 401

playlist = get_playlist(username)
return redirect(playlist, code=302)
```

# — STREAM REDIRECT (live, movie, series) —

@app.route(”/live/<user>/<password>/<stream_id>.m3u8”)
def live(user, password, stream_id):
if not auth_ok(user, password):
return “Unauthorized”, 401

```
playlist = get_playlist(user)
# M3U4U uses direct links
url = playlist.replace(".m3u", f"/{stream_id}.m3u8")
return redirect(url, code=302)
```

# RAW STREAM PATH

@app.route(”/<user>/<password>/<stream_id>”)
def raw_stream(user, password, stream_id):
if not auth_ok(user, password):
return “Unauthorized”, 401

```
playlist = get_playlist(user)
url = playlist.replace(".m3u", f"/{stream_id}.m3u8")
return redirect(url, code=302)
```

# –––––––– RUN ––––––––

if **name** == “**main**”:
app.run(host=“0.0.0.0”, port=10000)
