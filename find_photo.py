#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — find a FREE photo of a person or club (2026-11-06).

    python find_photo.py "Mohamed Salah" --out /tmp/salah            # table + /tmp/salah.json + /tmp/salah.png
    python find_photo.py "Al Ahly SC" --category "Al Ahly SC" --min-width 1200 --limit 16
    python find_photo.py "Zamalek" --category "Zamalek SC players" --sheet-only

Why: the article pipeline searched Wikimedia Commons by name only, which
finds a handful of snapshots per player. Three wider nets, one tool:
  1. Commons full-text search (as before),
  2. Commons CATEGORY members — «Category:<name>» and its first-level
     subcategories, where whole match albums sit that a name search misses,
  3. Openverse (api.openverse.org, no key): the CC index of FLICKR and
     Wikimedia with a licence filter — thousands of fan and press-pass
     photos of the big European clubs that never reached Commons.
Every hit is checked for licence (CC BY / CC BY-SA / CC0 / public domain
only), width, author and date, merged, sorted widest first, and written as
JSON plus a contact sheet PNG — open the sheet with the Read tool, pick,
then download by the `url` in the JSON. The licence and identity rules in
the article prompt are unchanged: this finds candidates, it does not vet
them. A file name or description that does not NAME the person is a candidate
for the bin, not for the site.
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

UA = {"User-Agent": "elgoon-photo-finder/1.0 (https://elgoon.com)"}
COMMONS = "https://commons.wikimedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"
OK_LICENCES = ("cc by", "cc by-sa", "cc0", "public domain", "pd", "by", "by-sa", "pdm")


def get_json(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def licence_ok(s):
    s = (s or "").strip().lower()
    if not s:
        return False
    if "nc" in s.split("-") or "-nc" in s or "nd" in s.split("-") or "-nd" in s:
        return False
    s = s.replace("cc pdm", "public domain").replace("cc-pdm", "public domain")
    return any(s == k or s.startswith(k + " ") or s.startswith(k + "-") or s == k.replace(" ", "-")
               for k in OK_LICENCES) or s.startswith("cc by") or s.startswith("cc-by") or s in ("cc0 1.0",)


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------------------------------------------------------------- Commons
def commons_imageinfo(titles):
    out = []
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": "|".join(chunk),
                                    "prop": "imageinfo", "iiprop": "url|size|extmetadata",
                                    "iiurlwidth": 1280})
        j = get_json(f"{COMMONS}?{q}")
        for p in (j.get("query", {}).get("pages", {}) or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {}) or {}
            lic = em.get("LicenseShortName", {}).get("value", "")
            out.append({
                "source": "commons", "title": p.get("title", ""),
                "url": ii.get("url"), "thumb": ii.get("thumburl") or ii.get("url"),
                "page": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p.get('title', '').replace(' ', '_'))}",
                "width": ii.get("width"), "height": ii.get("height"),
                "licence": lic, "author": strip_html(em.get("Artist", {}).get("value", ""))[:80],
                "date": (em.get("DateTimeOriginal", {}).get("value") or "")[:10],
                "description": strip_html(em.get("ImageDescription", {}).get("value", ""))[:160],
            })
    return out


def commons_search(query, limit):
    q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search", "srnamespace": 6,
                                "srlimit": limit, "srsearch": f"filetype:bitmap {query}"})
    j = get_json(f"{COMMONS}?{q}")
    return [r["title"] for r in j.get("query", {}).get("search", [])]


def commons_category(cat, limit):
    """Files in Category:<cat> plus its first-level subcategories."""
    titles, subcats = [], []
    cat = cat if cat.lower().startswith("category:") else f"Category:{cat}"
    q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "categorymembers",
                                "cmtitle": cat, "cmtype": "subcat|file", "cmlimit": 200})
    for m in get_json(f"{COMMONS}?{q}").get("query", {}).get("categorymembers", []):
        (subcats if m["ns"] == 14 else titles).append(m["title"])
    for sc in subcats[:12]:
        q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "categorymembers",
                                    "cmtitle": sc, "cmtype": "file", "cmlimit": 100})
        titles += [m["title"] for m in get_json(f"{COMMONS}?{q}").get("query", {}).get("categorymembers", [])]
    titles = [t for t in titles if re.search(r"\.(jpe?g|png|webp)$", t, re.I)]
    return titles[:limit], subcats


# ---------------------------------------------------------------- Openverse
def openverse(query, limit):
    q = urllib.parse.urlencode({"q": query, "license": "by,by-sa,cc0,pdm", "mature": "false",
                                "page_size": min(50, max(limit, 20)), "source": "flickr,wikimedia"})
    try:
        j = get_json(f"{OPENVERSE}?{q}")
    except Exception as e:                                   # noqa: BLE001
        print(f"  openverse unavailable: {str(e)[:80]}")
        return []
    out = []
    for r in j.get("results", []):
        out.append({
            "source": f"openverse/{r.get('source')}", "title": r.get("title") or "",
            "url": r.get("url"), "thumb": r.get("thumbnail") or r.get("url"),
            "page": r.get("foreign_landing_url"), "width": r.get("width"), "height": r.get("height"),
            "licence": {"by": "CC BY", "by-sa": "CC BY-SA", "cc0": "CC0", "pdm": "Public domain"}.get(
                (r.get("license") or "").lower(), f"CC {(r.get('license') or '').upper()}")
            + (f" {r.get('license_version')}" if r.get("license_version") else ""),
            "author": (r.get("creator") or "")[:80], "date": "",
            "description": "", "tags": [t.get("name") for t in (r.get("tags") or [])][:8],
        })
    return out


# ---------------------------------------------------------------- merge + sheet
def find(query, category=None, min_width=1200, limit=24, no_openverse=False):
    titles = commons_search(query, limit)
    subcats = []
    if category:
        more, subcats = commons_category(category, limit * 2)
        titles += [t for t in more if t not in titles]
    cands = commons_imageinfo(titles)
    if not no_openverse:
        cands += openverse(query, limit)
    seen, out = set(), []
    for c in cands:
        key = (c.get("url") or c.get("page") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        c["licence_ok"] = licence_ok(c.get("licence"))
        c["wide"] = bool(c.get("width") and c["width"] >= min_width)
        if c["licence_ok"] and c.get("width"):
            out.append(c)
    out.sort(key=lambda c: (-int(c["wide"]), -(c.get("width") or 0)))
    return out[:limit], subcats


def contact_sheet(cands, path, cols=4, tw=320, th=240):
    from PIL import Image, ImageDraw                         # noqa: PLC0415
    n = len(cands)
    sheet = Image.new("RGB", (cols * tw, ((n + cols - 1) // cols) * (th + 28)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, c in enumerate(cands):
        x, y = (i % cols) * tw, (i // cols) * (th + 28)
        try:
            data = urllib.request.urlopen(urllib.request.Request(c["thumb"], headers=UA), timeout=40).read()
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((tw - 8, th - 8))
            sheet.paste(im, (x + 4 + (tw - 8 - im.width) // 2, y + 4 + (th - 8 - im.height) // 2))
        except Exception:                                    # noqa: BLE001
            d.text((x + 10, y + 10), "thumb failed", fill=(200, 80, 80))
        d.text((x + 6, y + th + 4), f"#{i + 1} {c.get('width')}x{c.get('height')} {c.get('licence')}"[:52],
               fill=(230, 230, 230))
    sheet.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="English search text (Commons + Openverse), e.g. \"Mohamed Salah\"")
    ap.add_argument("--category", help="a Commons category to walk, e.g. \"Mohamed Salah\"")
    ap.add_argument("--min-width", type=int, default=1200)
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--out", help="basename: writes <out>.json and <out>.png")
    ap.add_argument("--no-openverse", action="store_true")
    ap.add_argument("--sheet-only", action="store_true", help="no table on stdout")
    args = ap.parse_args()
    cands, subcats = find(args.query, args.category, args.min_width, args.limit, args.no_openverse)
    if subcats:
        print("subcategories walked:", ", ".join(s.replace("Category:", "") for s in subcats[:12]))
    if not args.sheet_only:
        for i, c in enumerate(cands):
            flag = "" if c["wide"] else " (narrow)"
            print(f"#{i + 1:<3}{c['width']}x{c['height']}{flag} | {c['licence']} | {c['author'][:28]} | "
                  f"{c['source']} | {c['title'][:60]}")
            if c.get("description"):
                print(f"      {c['description'][:110]}")
    print(f"{len(cands)} free candidates (>= {args.min_width}px first)")
    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump(cands, f, ensure_ascii=False, indent=1)
        contact_sheet(cands, args.out + ".png")
        print(f"→ {args.out}.json  {args.out}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
