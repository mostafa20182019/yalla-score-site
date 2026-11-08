#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — find a FREE photo of a person or club (2026-11-06).

    python find_photo.py "Mohamed Salah" --out /tmp/salah            # table + /tmp/salah.json + /tmp/salah.png
    python find_photo.py "Al Ahly SC" --category "Al Ahly SC" --min-width 1200 --limit 16
    python find_photo.py "Zamalek" --category "Zamalek SC players" --sheet-only
    python find_photo.py "Omar Marmoush" --club "Tottenham Hotspur" --out /tmp/marm   # club-shirt photos first

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

--club (2026-11-08, user: «تخلى اللاعب لو بتتكلم على فريقه يكون لابس فانلة
فريقه»): a story about a player AT his club wants him in THAT club's shirt,
not his national team's. Commons files club photos in categories named
«<Player> with <Club>» (e.g. «Harry Kane with FC Bayern Munich»); --club
finds those categories by search; most players are filed BY YEAR instead
(«Harry Kane in 2025»), so it also walks «<Player> in <year>» from --since
(the year he joined; default last year). Every photo filed under a
«with <Club>» category, or whose name, description or categories name the
club (local spellings too: München, Spurs, PSG, Barça), is marked
`club: true`. Those sort to the top. The tag is a HINT from the filing, not
proof of the shirt: look at the photo, check its date is after he joined.
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
                                    "prop": "imageinfo|categories", "iiprop": "url|size|extmetadata",
                                    "iiurlwidth": 1280, "cllimit": "max", "clshow": "!hidden"})
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
                "categories": [c.get("title", "").replace("Category:", "") for c in (p.get("categories") or [])][:30],
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


def commons_club_categories(player, club, limit=6):
    """Categories like «<Player> with <Club F.C.>»: found by a category-
    namespace search, kept only when the name carries the player's surname
    AND a word of the club."""
    q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search", "srnamespace": 14,
                                "srlimit": 20, "srsearch": f"{player} {club}"})
    try:
        hits = [r["title"] for r in get_json(f"{COMMONS}?{q}").get("query", {}).get("search", [])]
    except Exception:                                        # noqa: BLE001
        return []
    sur = player.split()[-1].lower()
    words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", club)]
    keep = [h for h in hits if sur in h.lower() and any(w in h.lower() for w in words)]
    return keep[:limit]


def club_aliases(club):
    """Words that name the club in Commons filing: the words of what was
    passed, plus the local spellings the big clubs are filed under."""
    words = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", club)}
    extra = {"bayern": {"münchen", "munchen", "fcb"}, "munich": {"münchen", "bayern"},
             "tottenham": {"spurs", "hotspur"}, "manchester": set(), "paris": {"psg", "saint-germain"},
             "germain": {"psg"}, "barcelona": {"barça", "barca"}, "madrid": set(), "ahly": {"al-ahly", "alahly"},
             "zamalek": set(), "pyramids": set(), "liverpool": set(), "arsenal": set(), "chelsea": set()}
    for w in list(words):
        words |= extra.get(w, set())
    generic = {"football", "club", "city", "united", "real", "sporting", "athletic", "manchester", "madrid",
               "saint", "paris", "inter", "olympique"}      # «Saint-Lô», «Paris FC», «Inter Miami» are not PSG / Inter
    keep = words - generic
    return keep or {club.lower()}            # «Manchester City»: the whole name, never «city» alone


def year_files(player, since, limit):
    """Files in «<player> in <year>» for every year from `since` to now."""
    import datetime                                          # noqa: PLC0415
    titles, cats = [], []
    for y in range(int(since), datetime.date.today().year + 1):
        c = f"Category:{player} in {y}"
        q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "categorymembers",
                                    "cmtitle": c, "cmtype": "file", "cmlimit": 200})
        try:
            got = [m["title"] for m in get_json(f"{COMMONS}?{q}").get("query", {}).get("categorymembers", [])]
        except Exception:                                    # noqa: BLE001
            got = []
        if got:
            cats.append(c)
            titles += got
    titles = [t for t in titles if re.search(r"\.(jpe?g|png|webp)$", t, re.I)]
    return titles[:limit], cats


def club_files(player, club, limit):
    titles, cats = [], commons_club_categories(player, club)
    for c in cats:
        q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "categorymembers",
                                    "cmtitle": c, "cmtype": "file", "cmlimit": 100})
        try:
            titles += [m["title"] for m in get_json(f"{COMMONS}?{q}").get("query", {}).get("categorymembers", [])]
        except Exception:                                    # noqa: BLE001
            pass
    titles = [t for t in titles if re.search(r"\.(jpe?g|png|webp)$", t, re.I)]
    return titles[:limit], cats


# ---------------------------------------------------------------- Openverse
OPENVERSE_PAGE_MAX = 20     # anonymous Openverse refuses a page_size above 20 with HTTP 401


def openverse(query, limit):
    # 2026-11-08: this asked for min(50, max(limit, 20)) = 24 by default, which
    # an anonymous client may not ask for - every call came back 401 and the
    # except below swallowed it, so Openverse had silently added NOTHING since
    # 2026-11-06. One page of 20 is all an anonymous client gets.
    q = urllib.parse.urlencode({"q": query, "license": "by,by-sa,cc0,pdm", "mature": "false",
                                "page_size": OPENVERSE_PAGE_MAX, "source": "flickr,wikimedia"})
    try:
        j = get_json(f"{OPENVERSE}?{q}")
    except Exception as e:                                   # noqa: BLE001
        print(f"  WARNING openverse unavailable ({str(e)[:80]}) - the candidates below are Commons only")
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
def find(query, category=None, min_width=1200, limit=24, no_openverse=False, club=None, since=None):
    titles, subcats, club_titles = [], [], set()
    if club:
        ct, cats = club_files(query, club, limit * 2)
        club_titles = set(ct)
        titles += ct
        subcats += cats
        import datetime                                      # noqa: PLC0415
        yt, ycats = year_files(query, since or datetime.date.today().year - 1, limit * 6)
        titles += [t for t in yt if t not in titles]
        subcats += ycats
        titles += [t for t in commons_search(f"{query} {club}", limit) if t not in titles]
    titles += [t for t in commons_search(query, limit) if t not in titles]
    if category:
        more, sc = commons_category(category, limit * 2)
        subcats += sc
        titles += [t for t in more if t not in titles]
    cands = commons_imageinfo(titles)
    if not no_openverse:
        cands += openverse(f"{query} {club}" if club else query, limit)
    seen, out = set(), []
    for c in cands:
        key = (c.get("url") or c.get("page") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        c["licence_ok"] = licence_ok(c.get("licence"))
        c["wide"] = bool(c.get("width") and c["width"] >= min_width)
        if club:
            words = club_aliases(club)
            text = (f"{c.get('title', '')} {c.get('description', '')} {' '.join(c.get('tags') or [])} "
                    f"{' '.join(c.get('categories') or [])}").lower()
            c["club"] = c.get("title") in club_titles or any(w in text for w in words)
        if c["licence_ok"] and c.get("width"):
            out.append(c)
    out.sort(key=lambda c: (-int(bool(c.get("club"))), -int(c["wide"]), -(c.get("width") or 0)))
    if club:                                                 # every club photo found, then the rest
        n_club = sum(1 for c in out if c.get("club"))
        return out[:max(limit, n_club)], subcats
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
        d.text((x + 6, y + th + 4), (f"#{i + 1} {'CLUB ' if c.get('club') else ''}{c.get('date') or ''} "
                                     f"{c.get('width')}x{c.get('height')}")[:52],
               fill=(120, 230, 140) if c.get("club") else (230, 230, 230))
    sheet.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="English search text (Commons + Openverse), e.g. \"Mohamed Salah\"")
    ap.add_argument("--category", help="a Commons category to walk, e.g. \"Mohamed Salah\"")
    ap.add_argument("--club", help="the club the STORY is about, in English, e.g. \"Tottenham Hotspur\": "
                                   "photos filed under «<player> with <club>» or naming the club first, tagged club")
    ap.add_argument("--since", type=int, help="with --club: walk «<player> in <year>» from this year "
                                              "(the year he joined the club; default last year)")
    ap.add_argument("--min-width", type=int, default=1200)
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--out", help="basename: writes <out>.json and <out>.png")
    ap.add_argument("--no-openverse", action="store_true")
    ap.add_argument("--sheet-only", action="store_true", help="no table on stdout")
    args = ap.parse_args()
    cands, subcats = find(args.query, args.category, args.min_width, args.limit, args.no_openverse, args.club, args.since)
    if subcats:
        print("subcategories walked:", ", ".join(s.replace("Category:", "") for s in subcats[:12]))
    if not args.sheet_only:
        for i, c in enumerate(cands):
            flag = "" if c["wide"] else " (narrow)"
            flag += " CLUB" if c.get("club") else ""
            print(f"#{i + 1:<3}{c['width']}x{c['height']}{flag} | {c.get('date') or '-'} | {c['licence']} | {c['author'][:28]} | "
                  f"{c['source']} | {c['title'][:60]}")
            if c.get("description"):
                print(f"      {c['description'][:110]}")
    nclub = sum(1 for c in cands if c.get("club"))
    print(f"{len(cands)} free candidates (>= {args.min_width}px first)"
          + (f", {nclub} tagged as {args.club} photos (listed first)" if args.club else ""))
    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump(cands, f, ensure_ascii=False, indent=1)
        contact_sheet(cands, args.out + ".png")
        print(f"→ {args.out}.json  {args.out}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
