# app.py
import os
import re
import time
import json
import requests
from datetime import datetime
from functools import wraps

from flask import Flask, request, redirect, url_for, Response, jsonify
from flask_sqlalchemy import SQLAlchemy

# ---------------- APP CONFIG ----------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "changeme")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///xtream_users.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")

db = SQLAlchemy(app)

# ---------------- DATABASE ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    m3u_url = db.Column(db.String(512), nullable=False, default="")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ---------------- ORIGINAL USERS (seed) ----------------
ORIGINAL_USERS = {
    "dad": "devon",
    "john": "pass123",
    "John": "Sidford2025",
    "mark": "Sidmouth2025",
    "james": "October2025",
    "ian": "October2025",
    "harry": "October2025",
    "main": "admin"
}

DEFAULT_M3U_URL = os.getenv(
    "DEFAULT_M3U_URL",
    "https://example.com/default_playlist.m3u"  # replace if you want
)

def seed_original_users():
    """
    Insert original users into the SQLite DB if they don't already exist.
    Preserves existing users and passwords.
    """
    for uname, pwd in ORIGINAL_USERS.items():
        found = User.query.filter_by(username=uname).first()
        if not found:
            u = User(username=uname, password=pwd, m3u_url=DEFAULT_M3U_URL, is_active=True)
            db.session.add(u)
    db.session.commit()

with app.app_context():
    seed_original_users()

# ---------------- CACHES / PARSERS (lightweight, identical to your earlier code) ----------------
M3U_CACHE = {}
EPG_CACHE = {}
PLAYLIST_TTL = 300
EPG_TTL = 600

def fetch_and_parse_m3u(url):
    try:
        text = requests.get(url, timeout=15).text
    except Exception as e:
        print("Error fetching M3U:", e)
        return [], [], None

    lines = text.splitlines()
    epg_url = None

    if lines and lines[0].startswith("#EXTM3U"):
        m = re.search(r'url-tvg="(.*?)"', lines[0])
        if m:
            epg_url = m.group(1)

    channels = []
    groups = []
    stream_id = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            name_match = re.search(r",(.+)$", line)
            name = name_match.group(1) if name_match else "Unknown"
            logo_match = re.search(r'tvg-logo="(.*?)"', line)
            logo = logo_match.group(1) if logo_match else ""
            group_match = re.search(r'group-title="(.*?)"', line)
            group = group_match.group(1) if group_match else "Other"
            tvg_id_match = re.search(r'tvg-id="(.*?)"', line)
            tvg_id = tvg_id_match.group(1) if tvg_id_match else ""
            stream_url = ""
            if i + 1 < len(lines):
                stream_url = lines[i + 1].strip()
            if group not in groups:
                groups.append(group)
            channels.append({
                "id": stream_id,
                "name": name,
                "logo": logo,
                "group": group,
                "url": stream_url,
                "tvg_id": tvg_id
            })
            stream_id += 1
        i += 1

    return channels, groups, epg_url

def get_playlist_data(url):
    now = time.time()
    if url in M3U_CACHE and (now - M3U_CACHE[url]["ts"] < PLAYLIST_TTL):
        return M3U_CACHE[url]
    channels, groups, epg_url = fetch_and_parse_m3u(url)
    M3U_CACHE[url] = {"channels": channels, "groups": groups, "epg_url": epg_url, "ts": now}
    return M3U_CACHE[url]

# ---------------- AUTH ----------------
def xtream_auth(username, password):
    u = User.query.filter_by(username=username, password=password).first()
    return u if u and u.is_active else None

# ---------------- XTREAM API ----------------
@app.route("/player_api.php")
def player_api():
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action")

    user = xtream_auth(username, password)
    if not user:
        return jsonify({"user_info": {"auth": 0}})

    playlist = get_playlist_data(user.m3u_url or DEFAULT_M3U_URL)
    channels = playlist["channels"]
    groups = playlist["groups"]

    host = request.host
    ip = host.split(":", 1)[0] if ":" in host else host

    if not action:
        user_info = {
            "auth": 1,
            "username": user.username,
            "password": user.password,
            "status": "Active" if user.is_active else "Inactive",
            "exp_date": None,
            "is_trial": "0",
            "active_cons": 0,
            "created_at": str(user.created_at),
            "max_connections": 1,
            "allowed_output_formats": ["ts", "m3u8"]
        }
        server_info = {
            "url": ip,
            "port": 443,
            "https_port": 443,
            "server_protocol": "https",
            "rtmp_port": 0,
            "timezone": "Europe/London",
            "timestamp_now": int(time.time())
        }
        return jsonify({"user_info": user_info, "server_info": server_info})

    if action == "get_live_categories":
        payload = [{"category_id": str(i + 1), "category_name": g, "parent_id": 0} for i, g in enumerate(groups)]
        return Response(json.dumps(payload), mimetype="application/json")

    if action == "get_live_streams":
        cat_map = {g: (i + 1) for i, g in enumerate(groups)}
        payload = []
        for c in channels:
            payload.append({
                "num": c["id"],
                "stream_id": c["id"],
                "name": c["name"],
                "stream_type": "live",
                "stream_icon": c["logo"],
                "category_id": str(cat_map.get(c["group"], 0)),
                "custom_sid": "",
                "direct_source": "",
                "tv_archive": 0,
                "epg_channel_id": c.get("tvg_id", ""),
                "container_extension": "ts",
                "stream_url": f"https://{ip}/live/{user.username}/{user.password}/{c['id']}.ts"
            })
        return Response(json.dumps(payload), mimetype="application/json")

    if action in ["get_vod_categories", "get_vod_streams", "get_series_categories", "get_series", "get_series_info"]:
        return Response("[]", mimetype="application/json")

    return jsonify({"error": "Invalid action"})

# ---------------- XMLTV ----------------
@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username")
    password = request.args.get("password")

    user = xtream_auth(username, password)
    if not user:
        return "Auth failed", 401

    playlist = get_playlist_data(user.m3u_url or DEFAULT_M3U_URL)
    epg_url = playlist.get("epg_url")
    if not epg_url:
        return Response("<tv></tv>", mimetype="application/xml")

    now = time.time()
    if epg_url in EPG_CACHE and (now - EPG_CACHE[epg_url]["ts"] < EPG_TTL):
        return Response(EPG_CACHE[epg_url]["xml"], mimetype="application/xml")

    try:
        xml = requests.get(epg_url, timeout=20).text
    except Exception as e:
        print("Error fetching EPG:", e)
        xml = "<tv></tv>"

    EPG_CACHE[epg_url] = {"xml": xml, "ts": now}
    return Response(xml, mimetype="application/xml")

# ---------------- STREAM REDIRECT ----------------
@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    print(f"[STREAM REQUEST] {username} -> {stream_id}.{ext}")
    user = xtream_auth(username, password)
    if not user:
        return "Auth failed", 401
    playlist = get_playlist_data(user.m3u_url or DEFAULT_M3U_URL)
    chan = next((c for c in playlist["channels"] if c["id"] == stream_id), None)
    if not chan:
        return "Stream not found", 404
    return redirect(chan["url"], code=302)

# ---------------- SIMPLE USERS LIST (NO PANEL) ----------------
@app.route("/users")
def users_list():
    """
    Minimal, unauthenticated JSON list of users.
    Returns: [{"id":..,"username":..,"password":..,"m3u_url":..,"is_active":..}, ...]
    """
    users = User.query.order_by(User.id).all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "password": u.password,
            "m3u_url": u.m3u_url,
            "is_active": bool(u.is_active),
            "created_at": str(u.created_at)
        })
    return jsonify(out)

# ---------------- ROOT ----------------
@app.route("/")
def root():
    return "Xtream API Server OK", 200

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
