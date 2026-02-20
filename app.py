import os
import time
import hashlib
from io import BytesIO

import requests
from PIL import Image
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# Render: ephemeral disk is fine; cache reduces repeated fetches
CACHE_DIR = os.environ.get("CACHE_DIR", "thumb_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 1024 is recommended by Discord, but 512 also works fine in practice.
# We'll serve 1024 to be safe.
SIZE = int(os.environ.get("THUMB_SIZE", "1024"))
TTL_SECONDS = int(os.environ.get("CACHE_TTL", str(60 * 60 * 24)))  # 24h

USER_AGENT = "TubePresenceThumbProxy/1.0 (+https://example.com)"

def yt_thumb_url(video_id: str) -> str:
    # Try maxres first; fall back if not available
    return f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

def yt_thumb_fallback_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

def cache_path(video_id: str) -> str:
    key = hashlib.sha1(video_id.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}_{SIZE}.png")

def is_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < TTL_SECONDS

def fetch_image(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
    r.raise_for_status()
    return r.content

def make_png_square(image_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")

    # center-crop to square
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    # resize to SIZE x SIZE
    img = img.resize((SIZE, SIZE), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()

@app.get("/")
def home():
    return jsonify({"ok": True, "service": "tubepresence-thumb-proxy", "size": SIZE})

@app.get("/thumb/<video_id>.png")
def thumb(video_id: str):
    video_id = (video_id or "").strip()

    # basic validation
    if not video_id or len(video_id) > 32:
        return jsonify({"ok": False, "error": "invalid video id"}), 400

    path = cache_path(video_id)

    if is_fresh(path):
        with open(path, "rb") as f:
            data = f.read()
        return Response(data, mimetype="image/png", headers={"Cache-Control": "public, max-age=3600"})

    # Fetch thumbnail (maxres -> fallback)
    try:
        raw = fetch_image(yt_thumb_url(video_id))
    except Exception:
        try:
            raw = fetch_image(yt_thumb_fallback_url(video_id))
        except Exception:
            # If YouTube blocks/404, return a tiny blank PNG
            blank = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
            out = BytesIO()
            blank.save(out, format="PNG")
            return Response(out.getvalue(), mimetype="image/png")

    png = make_png_square(raw)

    try:
        with open(path, "wb") as f:
            f.write(png)
    except Exception:
        # If disk write fails, still serve the image
        pass

    return Response(png, mimetype="image/png", headers={"Cache-Control": "public, max-age=3600"})

if __name__ == "__main__":
    # Local dev
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
