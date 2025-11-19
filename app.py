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

# Required mappings you provided
DEFAULT_M3U_URL = "http://m3u4u.com/m3u/jwmzn1w282ukvxw4n721"

USER_M3U_URLS = {
    "john": "http://m3u4u.com/m3u/m/m73wp7qe3es9qvmpjk9x",
    "John": "http://m3u4u.com/m3u/m/m73wp7qe3es9qvmpjk9x",
    "main": "http://m3u4u.com/m3u/p87vnr8dzdu4w2q6n41j"
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
    return USER_M3U_URLS.get(username, DEFAULT_M3U_URL)


def wants_json():
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
    root = Element(root_tag)
    for item in data_list:
        item_elem = SubElement(root, item_tag)
        for key, val in item.items():
            child = SubElement(item_elem, key)
            child.text = str(val) if val else ""
    return tostring(root, encoding='unicode')


def fetch_m3u(url, username=""):
    now = time.time()
    entry = _m3u_cache.get(url)

    if entry and now - entry["ts"] < CACHE_TTL:
        return entry["parsed"]

    print(f"[FETCH] Fetching playlist for {username}: {url}")

    try:
        r = requests.get(url, headers=UA_HEADERS, timeout=15)
        r.raise_for_status()
        parsed = parse_m3u(r.text)

        _m3u_cache[url] = {
            "parsed": parsed,
            "ts": now
        }

        print(f"[FETCH OK] {len(parsed['streams'])} streams cached for {username}")
        return parsed

    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return {"categories": [], "streams": [], "epg_url": None}


def fetch_m3u_for_user(username):
    url = get_m3u_url_for_user(username)
    return fetch_m3u(url, username)


def parse_m3u(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    streams = []
    cats = {}
    cat_id = 1
    attr_re = re.compile(r'(\w[\w-]*)="([^"]*)"')
    epg_url = None
    sid = 1

    if lines and lines[0].startswith("#EXTM3U"):
        header_attrs = dict(attr_re.findall(lines[0]))
        epg_url = header_attrs.get("url-tvg")

    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            attrs = dict(attr_re.findall(lines[i]))
            name = lines[i].split(",", 1)[1]
            group = attrs.get("group-title", "Other")
            logo = attrs.get("tvg-logo", "")
            epgid = attrs.get("tvg-id", "")

            if group not in cats:
                cats[group] = cat_id
                cat_id += 1

            # Find URL
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            url = lines[j] if j < len(lines) else ""

            streams.append({
                "stream_id": sid,
                "name": name,
                "stream_icon": logo,
                "epg_channel_id": epgid,
                "category_id": cats[group],
                "category_name": group,
                "direct_source": url,
                "container_extension": "m3u8"
            })

            sid += 1
            i = j
        else:
            i += 1

    categories = [
        {"category_id": cid, "category_name": name, "parent_id": 0}
        for name, cid in cats.items()
    ]

    return {"categories": categories, "streams": streams, "epg_url": epg_url}


# ---------------- CORE ROUTES ----------------

@app.route("/player_api.php", methods=["GET", "POST"])
def player_api():
    username = request.values.get("username", "")
    password = request.values.get("password", "")
    action = request.values.get("action", "")
    use_json = wants_json()

    if not valid_user(username, password):
        return jsonify({"error": "Invalid login"}), 403

    # No action = return account info
    if action == "":
        user_info = {
            "user_info": {
                "auth": 1,
                "status": "Active",
                "username": username,
            }
        }
        return jsonify(user_info)

    # Categories
    if action == "get_live_categories":
        cats = fetch_m3u_for_user(username)["categories"]
        return jsonify(cats)

    # Streams
    if action == "get_live_streams":
        data = fetch_m3u_for_user(username)
        streams = [dict(s) for s in data["streams"]]

        # Rewrite ONLY for john + John
        if username in ["john", "John"]:
            host = request.host
            pw = USERS[username]
            for s in streams:
                s["direct_source"] = f"http://{host}/live/{username}/{pw}/{s['stream_id']}.m3u8"

        return jsonify(streams)

    return jsonify({"error": "Unknown action"}), 400


# ---------------- LIVE STREAM PROXY ----------------

@app.route("/live/<username>/<password>/<int:stream_id>.m3u8")
@app.route("/live/<username>/<password>/<int:stream_id>")
def live(username, password, stream_id):
    if not valid_user(username, password):
        return Response("Invalid login", status=403)

    data = fetch_m3u_for_user(username)

    stream = next((s for s in data["streams"] if s["stream_id"] == stream_id), None)
    if not stream:
        return Response("Stream not found", status=404)

    upstream = stream["direct_source"]
    print(f"[PLAY] {username} requested stream {stream_id}")

    # FULL PROXY MODE ONLY FOR john/John
    if username in ["john", "John"]:
        try:
            r = requests.get(upstream, headers=UA_HEADERS, stream=True, timeout=10)

            def generate():
                for chunk in r.iter_content(chunk_size=16384):
                    if chunk:
                        yield chunk

            return Response(generate(), headers={
                "Content-Type": r.headers.get("Content-Type", "video/mp2t")
            })

        except Exception as e:
            print("[PROXY ERROR]", e)
            return Response("Proxy failed", status=500)

    # Others → redirect
    return redirect(upstream, code=302)


# ---------------- EPG ----------------

@app.route("/xmltv.php")
def xmltv():
    username = request.args.get("username")
    password = request.args.get("password")
    if not valid_user(username, password):
        return Response("Invalid", status=403)

    epg = fetch_m3u_for_user(username).get("epg_url")
    if not epg:
        epg = "http://m3u4u.com/epg/476rnmqd4ds4rkd3nekg"

    return redirect(epg)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
