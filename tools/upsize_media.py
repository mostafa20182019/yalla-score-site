#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-fetch under-1200px article photos from Wikimedia Commons at full width,
in place, under the SAME filename.

    "C:\\Program Files\\Python312\\python.exe" tools/upsize_media.py --dry
    "C:\\Program Files\\Python312\\python.exe" tools/upsize_media.py            # rewrite what matched
    "C:\\Program Files\\Python312\\python.exe" tools/upsize_media.py a.jpg b.jpg

Why (SEO pass, 2026-11-04): Google Discover shows an article only with an
image at least 1200px wide (plus max-image-preview:large, which every page
already sends). 78 indexable articles share 26 hero files that were saved
from Commons at 720-1176px. The photos themselves are fine - the originals on
Commons are bigger - so the fix is to fetch the SAME file wider, not to pick
another photo (the credit line names this photo and its author).

How a file is matched: the article's credit names the photographer
(«تصوير <name>»); the filename gives the subject words. Commons search over
both -> the candidates' 320px thumbs are compared to our file by perceptual
hash (dHash, 64 bits). Only a candidate within HASH_MAX bits AND wider than
what we hold is fetched (width 1600, the site's cap) and written over the
file - never a guess, never an upscale, never a rename. Everything else is
reported and left alone.
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageOps

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(HERE, "media")
ARTICLES = os.path.join(HERE, "data", "articles.json")
API = "https://commons.wikimedia.org/w/api.php"
UA = "yallascore-media-upsize/1.0 (https://elgoon.com; yallascore.eg@gmail.com)"
MIN_W = 1200          # Discover's floor
MAX_W = 1600          # the site's cap (shrink_media.py)
HASH_MAX = 10         # dHash bits apart at most (identical photos sit at 0-6)
QUALITY = 85
PAUSE = 1.2           # Commons rate-limits bursts (429)


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _api(**params):
    params.update(format="json", formatversion="2")
    return json.loads(_get(API + "?" + urllib.parse.urlencode(params)))


def dhash(im, size=8):
    """64-bit difference hash: robust to scale and JPEG quality."""
    g = ImageOps.exif_transpose(im).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left, right = px[row * (size + 1) + col], px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def credits_for(name):
    """{author words, article ids} from articles.json for media/<name>."""
    with open(ARTICLES, encoding="utf-8") as f:
        doc = json.load(f)
    arts = doc if isinstance(doc, list) else doc["results"][0]["items"]
    authors, ids = set(), []
    for a in arts:
        if (a.get("image_url") or "").split("/")[-1] != name:
            continue
        ids.append(str(a.get("article_id")))
        m = re.search(r"تصوير\s+([^،,()\-—]+)", a.get("image_credit") or "")
        if m:
            authors.add(m.group(1).strip())
    return authors, ids


def subject_words(name):
    stem = os.path.splitext(name)[0]
    return [w for w in re.split(r"[-_]+", stem) if w and not w.isdigit() and len(w) > 2]


def candidates(name):
    """Commons file titles worth comparing: author + subject words first, the
    subject words alone as the fallback (a credit without «تصوير»)."""
    authors, ids = credits_for(name)
    words = " ".join(subject_words(name))
    queries = [f"{a} {words}" for a in authors] + [words]
    seen, out = set(), []
    for q in queries:
        try:
            res = _api(action="query", list="search", srnamespace=6, srlimit=25, srsearch=q)
        except Exception as e:                                   # noqa: BLE001
            print(f"    search failed ({e})")
            continue
        time.sleep(PAUSE)
        for hit in res.get("query", {}).get("search", []):
            t = hit["title"]
            if t not in seen and t.lower().endswith((".jpg", ".jpeg", ".png")):
                seen.add(t)
                out.append(t)
    return out, authors, ids


def imageinfo(titles):
    """{title: (width, height, thumburl320, url)} for up to 50 titles."""
    out = {}
    for i in range(0, len(titles), 50):
        res = _api(action="query", prop="imageinfo", iiprop="size|url", iiurlwidth=320,
                   titles="|".join(titles[i:i + 50]))
        time.sleep(PAUSE)
        for p in res.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            if ii.get("width"):
                out[p["title"]] = (ii["width"], ii["height"], ii.get("thumburl"), ii.get("url"))
    return out


def match(name, local_hash, local_w):
    """(title, width, distance) of the Commons file that IS our photo and is
    wider than what we hold, else None. Prints the near misses."""
    titles, authors, ids = candidates(name)
    print(f"  articles {', '.join(ids)}; author {', '.join(authors) or '-'}; {len(titles)} candidates")
    if not titles:
        return None
    info = imageinfo(titles)
    best = None
    for t in titles:
        w, h, thumb, url = info.get(t, (0, 0, None, None))
        if not thumb or w <= local_w:
            continue
        try:
            d = hamming(local_hash, dhash(Image.open(io.BytesIO(_get(thumb)))))
        except Exception:                                        # noqa: BLE001
            continue
        time.sleep(PAUSE * 0.5)
        if best is None or d < best[2]:
            best = (t, w, d)
    if best and best[2] <= HASH_MAX:
        return best
    if best:
        print(f"    nearest: {best[0]} ({best[1]}px) {best[2]} bits apart - not the same photo")
    return None


def fetch_wide(title, width):
    fname = title.split(":", 1)[1]
    url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
           + urllib.parse.quote(fname) + f"?width={min(width, MAX_W)}")
    im = Image.open(io.BytesIO(_get(url, timeout=60)))
    return ImageOps.exif_transpose(im)


def process(name, dry):
    path = os.path.join(MEDIA, name)
    with Image.open(path) as im:
        local_w = im.width
        local_hash = dhash(im)
        fmt = im.format
    print(f"{name}: {local_w}px")
    if local_w >= MIN_W:
        print("  already wide enough")
        return "ok"
    found = match(name, local_hash, local_w)
    if not found:
        print("  NOT FOUND on Commons - left alone")
        return "miss"
    title, w, d = found
    print(f"  matched {title} ({w}px, {d} bits apart)")
    if dry:
        return "would"
    im = fetch_wide(title, w)
    if im.width <= local_w:
        print(f"  the wide fetch came back {im.width}px - left alone")
        return "miss"
    if fmt == "JPEG" or path.lower().endswith((".jpg", ".jpeg")):
        im.convert("RGB").save(path, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    else:
        im.save(path, fmt or "PNG", optimize=True)
    with Image.open(path) as chk:
        print(f"  written {chk.width}x{chk.height}, {os.path.getsize(path) // 1024} KB")
    return "done"


def under_width():
    out = []
    for n in sorted(os.listdir(MEDIA)):
        p = os.path.join(MEDIA, n)
        if not os.path.isfile(p) or not n.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        try:
            with Image.open(p) as im:
                if im.width < MIN_W:
                    out.append(n)
        except Exception:                                        # noqa: BLE001
            continue
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="media/ filenames (default: every one under 1200px that an article uses)")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    names = a.files or [n for n in under_width() if credits_for(n)[1]]
    tally = {}
    for n in names:
        r = process(n, a.dry)
        tally[r] = tally.get(r, 0) + 1
    print("\n" + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
