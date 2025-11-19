import os
import time
import re
import requests
from flask import Flask, request, redirect, jsonify, Response
from xml.etree.ElementTree import Element, SubElement, tostring

app = Flask(__name__)

# ---------------- CONFIG ----------------

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

# Default playlist for dad, john, mark, james, ian, harry
DEFAULT_M3U_URL = (
    "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"
)

# Custom playlists - John and main get their own
USER_M3U_URLS = {
    "John": (
        "http://m3u4u.com/m3u/5g28nejz1zhv45q3yzpe"
    ),
    "main": (
        "http://m3u4u.com/m3u/p87vnr8dzdu4w2q6n41j"
    )
}

CACHE_TTL = 86400
_m3u_cache = {}

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ---------------- HELPERS ----------------

def valid_user(username, password):
    return username in USERS and USERS[username] == password


def get_m3u_url_for_user(username):
    """Return per-user playlist or default."""
    url = USER_M3U_URLS.get(username, DEFAULT_M3U_URL)
    print(f"[CONFIG] User '{username}' → {'CUSTOM' if username in USER_M3U_URLS else 'DEFAULT'} playlist")
    print(f"[CONFIG] URL: {url[:80]}...")
    return url


def wants_json():
    """Determine if client wants JSON response."""
    fmt = request.values.get("output", "").lower()
    if fmt == "json":
        return True
    if fmt in ["xml", "m3u8", "ts"]:
        return False

    ua = request.headers.get("User-Agent", "").lower()
    accept = request.headers.get("Accept", "").lower()

    if "smarters" in ua or "okhttp" in ua:
        return True
    if "json" in accept:
        return True
    if "xml" in accept and "json" not in accept:
        return False

    return True


def list_to_xml(root_tag, item_tag, data_list):
    """Convert list of dicts to XML string"""
    root = Element(root_tag)
    for item in data_list:
        item_elem = SubElement(root, item_tag)
        for key, val in item.items():
            child = SubElement(item_elem, key)
            child.text = str(val) if val is not None else ""
    return tostring(root, encoding='unicode')


def fetch_m3u(url, username=""):
    now = time.time()
    entry = _m3u_cache.get(url)

    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["parsed"]

    try:
        print(f"[INFO] Fetching: {username or url}")
        r = requests.get(url, headers=UA_HEADERS, timeout=25)
        r.raise_for_status()
        parsed = parse_m3u(r.text)

        _m3u_cache[url] = {
            "parsed": parsed,
            "ts": now,
            "last_fetch": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }
        print(f"[OK] Cached {len(parsed['streams'])} streams for {username}")
        return parsed

    except Exception as e:
        print(f"[ERROR] Fetch failed: {username} => {e}")
        if entry:
            return entry["parsed"]
        return {"categories": [], "streams": [], "epg_url": None}


def fetch_m3u_for_user(username):
    return fetch_m3u(get_m3u_url_for_user(username), username)


def parse_m3u(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    streams, cat_map = [], {}
    stream_id = 1
    next_cat = 1
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')
    epg_url = None

    # Extract EPG URL from M3U header
    if lines and lines[0].startswith("#EXTM3U"):
        header_attrs = dict(attr_re.findall(lines[0]))
        epg_url = header_attrs.get("url-tvg") or header_attrs.get("x-tvg-url")

    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            attrs = dict(attr_re.findall(lines[i]))
            name = lines[i].split(",", 1)[1].strip() if "," in lines[i] else "Channel"
            group = attrs.get("group-title", "Uncategorised")
            logo = attrs.get("tvg-logo", "")
            epg = attrs.get("tvg-id", "")

            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            url = lines[j] if j < len(lines) else ""

            if group not in cat_map:
                cat_map[group] = next_cat
                next_cat += 1

            streams.append({
                "stream_id": stream_id,
                "num": stream_id,
                "name": name,
                "stream_type": "live",
                "stream_icon": logo,
                "epg_channel_id": epg,
                "added": "1640000000",
                "category_id": str(cat_map[group]),
                "category_name": group,
                "direct_source": url,
                "tv_archive": 0,
                "tv_archive_duration": 0,
                "custom_sid": "",
                "tv_archive_start": "",
                "tv_archive_stop": "",
                "container_extension": "m3u8"
            })

            stream_id += 1
            i = j
        else:
            i += 1

    categories = [
        {"category_id": str(v), "category_name": k, "parent_id": 0}
        for k, v in cat_map.items()
    ]

    return {"categories": categories, "streams": streams, "epg_url": epg_url}

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    default = _m3u_cache.get(DEFAULT_M3U_URL, {})
    john = _m3u_cache.get(USER_M3U_URLS.get("John", ""), {})
    main = _m3u_cache.get(USER_M3U_URLS.get("main", ""), {})
    return (
        f"✅ Xtream Bridge (Multi-User)<br><br>"
        f"<b>Default:</b> {len(default.get('parsed', {}).get('streams', []))} streams<br>"
        f"<b>John:</b> {len(john.get('parsed', {}).get('streams', []))} streams<br>"
        f"<b>Main:</b> {len(main.get('parsed', {}).get('streams', []))} streams<br><br>"
        f"<a href='/whoami?username=main&password=admin'>🧭 Test Login</a> | "
        f"<a href='/debug'>🔍 Debug Users</a> | "
        f"<a href='/refresh'>🔄 Refresh Cache</a> | "
        f"<a href='/test_stream/1?username=main&password=admin'>🎬 Test Stream</a>"
    )


@app.route("/debug")
def debug_info():
    """Show which URLs and files are currently mapped and cached."""
    info = ["<h2>🔍 User-to-Playlist Mapping</h2>"]
    
    # Show what the code THINKS each user should get
    info.append("<h3>Expected Assignments:</h3>")
    for user in USERS.keys():
        expected_url = USER_M3U_URLS.get(user, DEFAULT_M3U_URL)
        is_custom = user in USER_M3U_URLS
        info.append(f"<b>{user}</b>: {'CUSTOM' if is_custom else 'DEFAULT'} → {expected_url[:80]}...<br>")
    
    info.append("<hr><h3>Actual Cache Status:</h3>")
    
    for user in USERS.keys():
        url = get_m3u_url_for_user(user)
        cache = _m3u_cache.get(url, {})
        streams = len(cache.get("parsed", {}).get("streams", []))
        last_fetch = cache.get("last_fetch", "Never")
        epg_url = cache.get("parsed", {}).get("epg_url", "Not found")
        
        info.append(f"""
        <div style='border:1px solid #ccc; padding:10px; margin:10px 0;'>
            <b>User:</b> {user}<br>
            <b>Playlist:</b> {'Custom' if user in USER_M3U_URLS else 'Default'}<br>
            <b>Streams:</b> {streams}<br>
            <b>Last Fetch:</b> {last_fetch}<br>
            <b>EPG URL:</b> <small>{epg_url}</small><br>
            <b>M3U URL:</b> <small>{url[:80]}...</small>
        </div>
        """)
    
    info.append("<br><a href='/'>← Back to Home</a> | <a href='/refresh'>🔄 Force Refresh Now</a>")
    return "".join(info)


@app.route("/refresh")
def refresh_all():
    """Force clear and re-fetch all playlists."""
    print("[INFO] 🔄 Manual full refresh triggered...")
    _m3u_cache.clear()
    fetch_m3u(DEFAULT_M3U_URL, "Default")
    for user, url in USER_M3U_URLS.items():
        fetch_m3u(url, user)
    return """
    <h2>✅ Cache Refreshed</h2>
    <p>All playlists have been forcibly refreshed and re-cached.</p>
    <a href='/'>← Back to Home</a> | <a href='/debug'>Check Debug</a>
    """


@app.route("/whoami")
def whoami():
    """Show which playlist and cache info this user gets."""
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    
    if not valid_user(username, password):
        return jsonify({"error": "Invalid credentials"}), 403
    
    url = get_m3u_url_for_user(username)
    cache = _m3u_cache.get(url, {})
    
    return jsonify({
        "username": username,
        "playlist_url": url,
        "streams": len(cache.get("parsed", {}).get("streams", [])),
        "last_fetch": cache.get("last_fetch", "Never"),
        "is_custom": username in USER_M3U_URLS
    })


@app.route("/test_stream/<int:stream_id>")
def test_stream(stream_id):
    """Debug endpoint to test stream URLs directly"""
    username = request.args.get("username", "main")
    password = request.args.get("password", "admin")
    
    if not valid_user(username, password):
        return "Invalid credentials", 403
    
    data = fetch_m3u_for_user(username)
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            return f"""
            <h3>Stream #{stream_id}: {s['name']}</h3>
            <p><b>Direct URL:</b><br><textarea style="width:100%;height:60px">{s['direct_source']}</textarea></p>
            <p><b>Xtream URL:</b><br>http://{request.host}/live/{username}/{password}/{stream_id}.m3u8</p>
            <p><a href="{s['direct_source']}" target="_blank">Test Direct Link</a></p>
            <p><a href="/live/{username}/{password}/{stream_id}.m3u8">Test Via Proxy</a></p>
            """
    
    return "Stream not found", 404


@app.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    username = request.values.get("username", "")
    password = request.values.get("password", "")
    action = request.values.get("action", "")
    use_json = wants_json()

    print(f"[API] user={username}, action={action}, json={use_json}, UA={request.headers.get('User-Agent', '')[:40]}")

    if not valid_user(username, password):
        msg = {
            "user_info": {
                "username": username,
                "password": password,
                "message": "Invalid credentials",
                "auth": 0,
                "status": "Disabled"
            }
        }
        if use_json:
            return jsonify(msg), 403
        else:
            xml = '<?xml version="1.0"?><response><user_info><auth>0</auth><status>Disabled</status></user_info></response>'
            return Response(xml, status=403, content_type="application/xml")

    if action == "":
        info = {
            "user_info": {
                "username": username,
                "password": password,
                "message": "Active",
                "auth": 1,
                "status": "Active",
                "exp_date": None,
                "is_trial": "0",
                "active_cons": "0",
                "created_at": "1640000000",
                "max_connections": "1",
                "allowed_output_formats": ["m3u8", "ts"]
            },
            "server_info": {
                "url": request.host.split(":")[0],
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "1935",
                "timezone": "UTC",
                "timestamp_now": int(time.time()),
                "time_now": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        
        if use_json:
            return jsonify(info)
        else:
            xml = '<?xml version="1.0" encoding="UTF-8"?><response><user_info>'
            for k, v in info["user_info"].items():
                if isinstance(v, list):
                    v = ",".join(v)
                xml += f'<{k}>{v}</{k}>'
            xml += '</user_info><server_info>'
            for k, v in info["server_info"].items():
                xml += f'<{k}>{v}</{k}>'
            xml += '</server_info></response>'
            return Response(xml, content_type="application/xml")

    if action == "get_live_categories":
        cats = fetch_m3u_for_user(username)["categories"]
        if use_json:
            return jsonify(cats)
        else:
            xml = list_to_xml("categories", "category", cats)
            return Response(f'<?xml version="1.0"?>{xml}', content_type="application/xml")

    if action == "get_live_streams":
        data = fetch_m3u_for_user(username)
        cat_filter = request.values.get("category_id")

        # Work on a COPY of each stream so we don't mutate the cache
        streams = []
        for s in data["streams"]:
            if cat_filter and str(s["category_id"]) != str(cat_filter):
                continue
            streams.append(dict(s))  # shallow copy of each stream dict
        
        # SPECIAL: Force John and john's streams through our bridge for Smarters compatibility
        if username in ["John", "john"]:
            server_url = request.host
            user_password = USERS[username]  # Get their actual password
            for stream in streams:
                stream_id = stream["stream_id"]
                stream["direct_source"] = f"http://{server_url}/live/{username}/{user_password}/{stream_id}.m3u8"
            print(f"[SMARTERS-FIX] {username}: {len(streams)} streams rewritten to use bridge")

        if use_json:
            return jsonify(streams)
        else:
            xml = list_to_xml("streams", "channel", streams)
            return Response(f'<?xml version="1.0"?>{xml}', content_type="application/xml")

    if action == "get_account_info":
        account_info = {
            "username": username,
            "password": password,
            "message": "Active",
            "auth": 1,
            "status": "Active",
            "exp_date": None,
            "is_trial": "0",
            "active_cons": "0",
            "created_at": "1640000000",
            "max_connections": "1"
        }
        if use_json:
            return jsonify(account_info)
        else:
            xml = '<?xml version="1.0"?><user_info>'
            for k, v in account_info.items():
                xml += f'<{k}>{v}</{k}>'
            xml += '</user_info>'
            return Response(xml, content_type="application/xml")

    if action in [
        "get_vod_categories", "get_vod_streams", "get_series_categories",
        "get_series", "get_series_info", "get_vod_info", "get_short_epg"
    ]:
        if use_json:
            return jsonify([])
        else:
            return Response('<?xml version="1.0"?><response></response>', content_type="application/xml")

    if use_json:
        return jsonify({"error": "action not handled", "action": action})
    else:
        return Response(f'<?xml version="1.0"?><e>Unknown action: {action}</e>', 
                      status=400, content_type="application/xml")


@app.route("/live/<username>/<password>/<int:stream_id>.<ext>")
@app.route("/live/<username>/<password>/<int:stream_id>")
@app.route("/<username>/<password>/<int:stream_id>.<ext>")
@app.route("/<username>/<password>/<int:stream_id>")
def live(username, password, stream_id, ext=None):
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)

    data = fetch_m3u_for_user(username)
    target_stream = None
    for s in data["streams"]:
        if s["stream_id"] == stream_id:
            target_stream = s
            break

    if not target_stream:
        return Response("Stream not found", status=404)

    upstream_url = target_stream.get("direct_source")
    if not upstream_url:
        return Response("Upstream URL missing", status=500)

    requested_ext = ext or "none"
    actual_ext = "m3u8" if ".m3u8" in upstream_url else "ts" if ".ts" in upstream_url else "unknown"
    print(f"[STREAM] User: {username}, Stream: {stream_id} ({target_stream['name']}), Req ext: {requested_ext}, Actual: {actual_ext}")
    print(f"[STREAM] Upstream URL: {upstream_url[:80]}...")

    # FULL PROXY MODE for John/john
    if username in ["John", "john"]:
        print(f"[PROXY] Streaming via proxy for {username}, stream {stream_id}")
        try:
            upstream_resp = requests.get(upstream_url, headers=UA_HEADERS, stream=True, timeout=20)

            def generate():
                for chunk in upstream_resp.iter_content(chunk_size=1024 * 32):
                    if not chunk:
                        continue
                    yield chunk

            # Keep only essential headers
            headers = {}
            content_type = upstream_resp.headers.get("Content-Type")
            if content_type:
                headers["Content-Type"] = content_type

            return Response(generate(), status=upstream_resp.status_code, headers=headers)
        except Exception as e:
            print(f"[ERROR] Proxy stream failed for {username}, stream {stream_id}: {e}")
            return Response("Stream error", status=500)

    # Everyone else: regular redirect to upstream
    return redirect(upstream_url, code=302)


@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    
    data = fetch_m3u_for_user(username)
    epg_url = data.get("epg_url")
    
    if not epg_url:
        epg_url = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"
        print(f"[EPG] No EPG in M3U for {username}, using fallback")
    else:
        print(f"[EPG] Using EPG from M3U for {username}: {epg_url[:60]}...")
    
    return redirect(epg_url)


@app.route("/get.php")
def get_m3u():
    username = request.args.get("username", "")
    password = request.args.get("password", "")
    if not valid_user(username, password):
        return Response("Invalid credentials", status=403)
    return redirect(get_m3u_url_for_user(username))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
