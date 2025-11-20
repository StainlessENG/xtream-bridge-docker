import os
import re
import time
import json
import requests
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, redirect, url_for,
    render_template, flash, session, Response, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader

# ==========================================================
#                    APP + CONFIG
# ==========================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "changeme")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///xtream_users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")

db = SQLAlchemy(app)

# ==========================================================
#                        DATABASE
# ==========================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    m3u_url = db.Column(db.String(512), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ==========================================================
#                        TEMPLATES
# ==========================================================

BASE_TEMPLATE = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Xtream Admin</title></head>
<body style="font-family:Arial;margin:0;padding:20px">
<header>
  <h1>Xtream Admin</h1>
  {% if session.get('admin_logged_in') %}
    <a href="{{ url_for('admin_users') }}">Users</a> |
    <a href="{{ url_for('admin_logout') }}">Logout</a>
  {% endif %}
</header>
<hr>

{% with msgs = get_flashed_messages(with_categories=true) %}
  {% for c,m in msgs %}
    <p><b>{{c}}</b>: {{m}}</p>
  {% endfor %}
{% endwith %}

{% block content %}{% endblock %}
</body>
</html>
"""

LOGIN_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h2>Admin Login</h2>
<form method="post">
  <p>Username: <input name="username"></p>
  <p>Password: <input name="password" type="password"></p>
  <button>Login</button>
</form>
{% endblock %}
"""

USERS_LIST_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h2>Users</h2>
<p><a href="{{ url_for('admin_new_user') }}">+ New User</a></p>

<table border="1" cellpadding="6">
<tr><th>ID</th><th>User</th><th>M3U URL</th><th>Active</th><th>Actions</th></tr>
{% for u in users %}
<tr>
  <td>{{u.id}}</td>
  <td>{{u.username}}</td>
  <td style="max-width:300px;word-break:break-all">{{u.m3u_url}}</td>
  <td>{{"Yes" if u.is_active else "No"}}</td>
  <td>
    <a href="{{url_for('admin_edit_user', user_id=u.id)}}">Edit</a> |
    <form method="post" action="{{url_for('admin_delete_user',user_id=u.id)}}" style="display:inline">
      <button onclick="return confirm('Delete?')">Delete</button>
    </form>
  </td>
</tr>
{% endfor %}
</table>
{% endblock %}
"""

USER_FORM_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<h2>{{ "Edit User" if user else "New User" }}</h2>
<form method="post">
  <p>Username: <input name="username" value="{{ user.username if user else '' }}"></p>
  <p>Password: <input name="password" value="{{ user.password if user else '' }}"></p>
  <p>M3U URL: <input name="m3u_url" value="{{ user.m3u_url if user else '' }}"></p>
  <p>Active: <input type="checkbox" name="is_active" value="1" {% if user and user.is_active %}checked{% endif %}></p>
  <button>Save</button>
</form>
{% endblock %}
"""

app.jinja_loader = DictLoader({
    "base.html": BASE_TEMPLATE,
    "login.html": LOGIN_TEMPLATE,
    "users_list.html": USERS_LIST_TEMPLATE,
    "user_form.html": USER_FORM_TEMPLATE
})

# ==========================================================
#                AUTH DECORATOR
# ==========================================================

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapper

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == ADMIN_USERNAME and request.form["password"] == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_users"))
        flash("Invalid login", "error")
    return render_template("login.html")

@app.route("/admin/logout")
@login_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

# ==========================================================
#                USER MANAGEMENT
# ==========================================================

@app.route("/admin/users")
@login_required
def admin_users():
    return render_template("users_list.html", users=User.query.all())

@app.route("/admin/users/new", methods=["GET","POST"])
@login_required
def admin_new_user():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        m = request.form["m3u_url"]
        a = request.form.get("is_active") == "1"

        if User.query.filter_by(username=u).first():
            flash("User exists", "error")
        else:
            db.session.add(User(username=u, password=p, m3u_url=m, is_active=a))
            db.session.commit()
            return redirect(url_for("admin_users"))

    return render_template("user_form.html", user=None)

@app.route("/admin/users/<int:user_id>/edit", methods=["GET","POST"])
@login_required
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        user.username = request.form["username"]
        user.password = request.form["password"]
        user.m3u_url = request.form["m3u_url"]
        user.is_active = request.form.get("is_active") == "1"
        db.session.commit()
        return redirect(url_for("admin_users"))

    return render_template("user_form.html", user=user)

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    u = User.query.get_or_404(user_id)
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for("admin_users"))

# ==========================================================
#            M3U / EPG PARSER + CACHE
# ==========================================================

M3U_CACHE = {}
EPG_CACHE = {}
PLAYLIST_TTL = 300   # seconds
EPG_TTL = 600        # seconds

def xtream_auth(username, password):
    u = User.query.filter_by(username=username, password=password).first()
    return u if u and u.is_active else None

def fetch_and_parse_m3u(url):
    """
    Returns (channels, groups, epg_url)
    channels: list of {id, name, logo, group, url, tvg_id}
    groups: category names in the order they appear
    epg_url: from #EXTM3U url-tvg="..."
    """
    try:
        text = requests.get(url, timeout=15).text
    except Exception as e:
        print("Error fetching M3U:", e)
        return [], [], None

    lines = text.splitlines()
    epg_url = None

    # First line: #EXTM3U url-tvg="..."
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
            # Channel name after the comma
            name_match = re.search(r",(.+)$", line)
            name = name_match.group(1) if name_match else "Unknown"

            logo_match = re.search(r'tvg-logo="(.*?)"', line)
            logo = logo_match.group(1) if logo_match else ""

            group_match = re.search(r'group-title="(.*?)"', line)
            group = group_match.group(1) if group_match else "Other"

            tvg_id_match = re.search(r'tvg-id="(.*?)"', line)
            tvg_id = tvg_id_match.group(1) if tvg_id_match else ""

            # Next line: actual stream URL
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
    M3U_CACHE[url] = {
        "channels": channels,
        "groups": groups,
        "epg_url": epg_url,
        "ts": now
    }
    return M3U_CACHE[url]

# ==========================================================
#                   XTREAM API
# ==========================================================

@app.route("/player_api.php")
def player_api():
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action")

    user = xtream_auth(username, password)
    if not user:
        return jsonify({"user_info": {"auth": 0}})

    playlist = get_playlist_data(user.m3u_url)
    channels = playlist["channels"]
    groups = playlist["groups"]

    host = request.host
    if ":" in host:
        ip = host.split(":", 1)[0]
    else:
        ip = host

    # ---------------- LOGIN (no action) ----------------
    if not action:
        user_info = {
            "auth": 1,
            "username": user.username,
            "password": user.password,
            "status": "Active",
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

    # ---------------- LIVE CATEGORIES ----------------
    if action == "get_live_categories":
        payload = [
            {"category_id": str(i + 1), "category_name": g, "parent_id": 0}
            for i, g in enumerate(groups)
        ]
        return Response(json.dumps(payload), mimetype="application/json")

    # ---------------- LIVE STREAMS ----------------
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

    # ---------------- MINIMAL VOD/SERIES (EMPTY) ----------------
    if action in [
        "get_vod_categories", "get_vod_streams",
        "get_series_categories", "get_series",
        "get_series_info"
    ]:
        return Response("[]", mimetype="application/json")

    return jsonify({"error": "Invalid action"})

# ==========================================================
#                      XMLTV EPG
# ==========================================================

@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username")
    password = request.args.get("password")

    user = xtream_auth(username, password)
    if not user:
        return "Auth failed", 401

    playlist = get_playlist_data(user.m3u_url)
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

# ==========================================================
#                   STREAM REDIRECT
# ==========================================================

@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
def live_redirect(username, password, stream_id, ext):
    print(f"[STREAM REQUEST] {username} -> {stream_id}.{ext}")

    user = xtream_auth(username, password)
    if not user:
        return "Auth failed", 401

    playlist = get_playlist_data(user.m3u_url)
    chan = next((c for c in playlist["channels"] if c["id"] == stream_id), None)

    if not chan:
        return "Stream not found", 404

    return redirect(chan["url"], code=302)

# ==========================================================
#                     ROOT CHECK
# ==========================================================

@app.route("/")
def root():
    return "Xtream API Server OK", 200

# ==========================================================
#                        RUN LOCAL
# ==========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
