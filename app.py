import requests
from flask import Flask, request, redirect, jsonify, Response

app = Flask(__name__)

# ---------------- USERS ----------------

USERS = {
    "dad": "devon",
    "john": "pass123",
    "John": "Sidford2025",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

# ---------------- PLAYLIST MAP ----------------

PLAYLISTS = {
    "john": "http://m3u4u.com/m/m73wp7qe3es9qvmpjk9x",
    "John": "http://m3u4u.com/m/m73wp7qe3es9qvmpjk9x",
    "main": "http://m3u4u.com/m3u/p87vnr8dzdu4w2q6n41j",
}

DEFAULT_PLAYLIST = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"


# ---------------- HELPERS ----------------

def get_playlist(username):
    return PLAYLISTS.get(username, DEFAULT_PLAYLIST)


def auth_ok(username, password):
    return username in USERS and USERS[username] == password


# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return "Xtream Bridge Running"


# XTREAM API LOGIN
@app.route("/player_api.php")
def player_api():
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not auth_ok(username, password):
        return jsonify({"user_info": {"auth": 0}})

    playlist = get_playlist(username)

    return jsonify({
        "user_info": {
            "auth": 1,
            "username": username,
            "password": password,
            "status": "Active",
        },
        "server_info": {
            "url": request.host
        }
    })


# --- M3U REDIRECT ---
@app.route("/get.php")
def get_php():
    username = request.args.get("username", "")
    password = request.args.get("password", "")

    if not auth_ok(username, password):
        return "Auth Failed", 401

    playlist = get_playlist(username)
    return redirect(playlist, code=302)


# --- STREAM REDIRECT (live, movie, series) ---
@app.route("/live/<user>/<password>/<stream_id>.m3u8")
def live(user, password, stream_id):

    if not auth_ok(user, password):
        return "Unauthorized", 401

    playlist = get_playlist(user)

    # M3U4U uses direct links, like /live/.../stream_id
    url = playlist.replace(".m3u", f"/{stream_id}.m3u8")
    return redirect(url, code=302)


# RAW STREAM PATH
@app.route("/<user>/<password>/<stream_id>")
def raw_stream(user, password, stream_id):

    if not auth_ok(user, password):
        return "Unauthorized", 401

    playlist = get_playlist(user)
    url = playlist.replace(".m3u", f"/{stream_id}.m3u8")
    return redirect(url, code=302)


# --- LIVE CATEGORIES ---
@app.route("/player_api.php", methods=["POST"])
def player_api_post():
    # Smarters sometimes uses POST for categories
    data = request.form
    username = data.get("username", "")
    password = data.get("password", "")
    action = data.get("action", "")

    if not auth_ok(username, password):
        return jsonify({"user_info": {"auth": 0}})

    playlist = get_playlist(username)

    if action == "get_live_categories":
        # M3U4U does not contain categories → return generic
        return jsonify([
            {"category_id": "1", "category_name": "Live", "parent_id": 0}
        ])

    return jsonify({"result": "OK"})


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
