#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch Yalla Score content DIRECTLY from the sources (no Oracle), so the site can
be rebuilt anywhere (e.g. GitHub Actions) 24/7 without the local PC.

Writes data/headlines.json and data/matches.json in the SAME
{"results":[{"items":[...]}]} shape that build_site.py already reads.
Does NOT touch data/articles.json (editorial content is kept in the repo).

Env:
  FD_TOKEN  - football-data.org API token (for matches). If missing, matches
              are left as-is (keeps the last matches.json).
"""
import json, os, re, html, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FD_TOKEN = os.environ.get("FD_TOKEN", "").strip()
CAIRO = ZoneInfo("Africa/Cairo")
UA = "Mozilla/5.0 (YallaScore static-site builder)"
FD_COMPS = ["WC", "PL", "PD", "SA", "BL1", "FL1"]  # World Cup, PL, La Liga, Serie A, Bundesliga, Ligue 1

def http_get(url, headers=None, timeout=40, retries=2):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
    raise last

def write_items(name, items):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump({"results": [{"items": items}]}, f, ensure_ascii=False)

def _unescape(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    return html.unescape(s).strip()

# ------------------------------------------------------------------ news
_AR_TRANS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي",
                           "ؤ": "و", "ئ": "ي"})

def _title_tokens(title, source):
    """Normalized word set of a headline (for near-duplicate detection)."""
    t = (title or "").strip()
    if source and t.endswith(" - " + source):          # drop the " - المصدر" suffix
        t = t[: -(len(source) + 3)]
    t = t.translate(_AR_TRANS)
    t = re.sub(r"[ً-ْ]", "", t)              # tashkeel
    t = re.sub(r"[^\wء-ي ]+", " ", t)        # punctuation -> space
    return {w for w in t.split() if len(w) >= 3}

def _same_story(a, b):
    """Same story from another outlet: high Jaccard overlap, OR one headline
    (near-)contained in the other (short rewrites of the same news)."""
    if not a or not b:
        return False
    inter = len(a & b)
    if inter / (len(a) + len(b) - inter) >= 0.5:
        return True
    return inter / min(len(a), len(b)) >= 0.7

def _dedup_stories(items):
    kept, seen = [], []
    for it in items:                                    # items arrive newest-first
        tok = _title_tokens(it.get("title"), it.get("source"))
        if any(_same_story(tok, s) for s in seen):
            continue
        kept.append(it)
        seen.append(tok)
    return kept

def fetch_news():
    q = urllib.parse.quote("كرة القدم")
    url = f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"
    xml = http_get(url)
    items = []
    for m in re.finditer(r"<item\b[^>]*>(.*?)</item>", xml, re.S):
        block = m.group(1)
        def tag(t):
            mm = re.search(rf"<{t}\b[^>]*>(.*?)</{t}>", block, re.S)
            return _unescape(mm.group(1)) if mm else ""
        link = tag("link")
        title = tag("title")
        if not link or not title:
            continue
        pub_iso, pub_date = "", ""
        praw = tag("pubDate")
        if praw:
            try:
                dtu = parsedate_to_datetime(praw).astimezone(timezone.utc)
                pub_iso = dtu.strftime("%Y-%m-%dT%H:%M:%SZ")
                pub_date = dtu.strftime("%Y-%m-%d")
            except Exception:
                pass
        items.append({"title": title, "link": link, "source": tag("source"),
                      "pub_date": pub_date, "pub_iso": pub_iso})
    items.sort(key=lambda x: x.get("pub_iso") or "", reverse=True)
    items = _dedup_stories(items)   # one card per story, not per outlet
    return items[:60]               # home shows 9; /headlines.html shows all

# ----------------------------------------------------------------- reels
# Auto-pull the newest uploads of chosen SHORTS-ONLY channels into
# data/reels_auto.json (merged after the hand-picked data/reels.json).
# Empty list = feature off (nothing is written). Add channel ids like:
#   REEL_CHANNELS = ["UCxxxxxxxxxxxxxxxxxxxxxx", ...]
# NOTE: pick channels that post ONLY vertical shorts - the RSS feed can't
# tell a short from a long video.
REEL_CHANNELS = []
REELS_PER_CHANNEL = 4

def fetch_reels_auto():
    if not REEL_CHANNELS:
        return None
    out = []
    for ch in REEL_CHANNELS:
        try:
            xml = http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch}")
        except Exception as e:
            print(f"  ! reels RSS failed ({ch}): {e}")
            continue
        n = 0
        for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.S):
            block = m.group(1)
            vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", block)
            tit = re.search(r"<title>([^<]*)</title>", block)
            pub = re.search(r"<published>(\d{4}-\d{2}-\d{2})", block)
            if not vid:
                continue
            out.append({"video_id": _unescape(vid.group(1)),
                        "title": _unescape(tit.group(1)) if tit else "",
                        "pub_date": pub.group(1) if pub else ""})
            n += 1
            if n >= REELS_PER_CHANNEL:
                break
    out.sort(key=lambda x: x.get("pub_date") or "", reverse=True)
    return out

# --------------------------------------------------------------- matches
def _norm_status(s):
    s = (s or "").upper()
    if s in ("IN_PLAY", "PAUSED"):
        return "LIVE"
    if s == "FINISHED":
        return "FINISHED"
    return "UPCOMING"

def fetch_matches():
    if not FD_TOKEN:
        print("  ! FD_TOKEN not set - skipping matches (keeping existing matches.json)")
        return None
    hdr = {"X-Auth-Token": FD_TOKEN}
    raw = {}
    def pull(url):
        try:
            j = json.loads(http_get(url, hdr))
            for mm in j.get("matches", []):
                raw[mm["id"]] = mm
        except Exception as e:
            print(f"  ! FD call failed ({url.split('?')[0]}): {e}")
    for comp in FD_COMPS:
        pull(f"https://api.football-data.org/v4/competitions/{comp}/matches?status=SCHEDULED")
    today = datetime.now(CAIRO).date()
    frm = (today - timedelta(days=7)).isoformat()
    to = (today + timedelta(days=1)).isoformat()
    pull(f"https://api.football-data.org/v4/matches?status=FINISHED&dateFrom={frm}&dateTo={to}")
    pull("https://api.football-data.org/v4/matches?status=LIVE")

    cutoff = today - timedelta(days=5)
    out = []
    for m in raw.values():
        utc = m.get("utcDate")
        if not utc:
            continue
        try:
            dt = datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(CAIRO)
        except Exception:
            continue
        if dt.date() < cutoff:
            continue
        comp = m.get("competition") or {}
        if (comp.get("code") or "") not in FD_COMPS:
            continue  # keep only our 6 competitions
        ht = m.get("homeTeam") or {}
        at = m.get("awayTeam") or {}
        ft = (m.get("score") or {}).get("fullTime") or {}
        out.append({
            "match_id": m.get("id"),
            "competition": comp.get("name"),
            "home": ht.get("name"), "away": at.get("name"),
            "home_badge": ht.get("crest"), "away_badge": at.get("crest"),
            "kickoff": dt.strftime("%Y-%m-%d"),
            "koff_time": dt.strftime("%H:%M"),
            "status": _norm_status(m.get("status")),
            "home_score": ft.get("home"), "away_score": ft.get("away"),
            "channel": None,
        })
    out.sort(key=lambda x: (x["kickoff"], x["koff_time"] or ""))
    return out[:60]

# -------------------------------------------------------------- standings
# league tables for the 5 domestic leagues (World Cup has groups, not a table)
FD_TABLE_COMPS = ["PL", "PD", "SA", "BL1", "FL1"]

def fetch_standings():
    if not FD_TOKEN:
        print("  ! FD_TOKEN not set - skipping standings")
        return None
    hdr = {"X-Auth-Token": FD_TOKEN}
    out = []
    got_any = False
    today = datetime.now(CAIRO).strftime("%Y-%m-%d")
    # fetch_matches just burned ~8 of the 10-req/min budget; let the window clear
    # before the standings batch, then space each call out.
    print("  … waiting 60s for the rate-limit window before standings")
    time.sleep(60)
    for i, comp in enumerate(FD_TABLE_COMPS):
        if i:
            time.sleep(7)
        try:
            j = json.loads(http_get(
                f"https://api.football-data.org/v4/competitions/{comp}/standings", hdr))
        except Exception as e:
            print(f"  ! standings {comp} failed: {e}")
            continue
        got_any = True
        table = None
        for s in j.get("standings", []):
            if s.get("type") == "TOTAL":
                table = s.get("table")
                break
        if not table:
            continue
        # Before kickoff football-data still serves LAST season's FINAL table
        # under the new season id. Show it (more useful than an empty table),
        # but label it as last season so nobody mistakes it for the new one.
        start = (j.get("season") or {}).get("startDate") or ""
        started = bool(start) and start[:10] <= today
        maxplayed = max((r.get("playedGames") or 0) for r in table)
        past = (not started) and maxplayed > 0
        season_label = ""
        if past:
            try:
                y = int(start[:4])
                season_label = f"{y-1}/{y}"      # e.g. season starting 2026 -> last = 2025/2026
            except Exception:
                season_label = "الموسم الماضي"
            print(f"  · standings {comp}: showing last season ({season_label})")
        name = (j.get("competition") or {}).get("name") or comp
        rows = []
        for r in table:
            t = r.get("team") or {}
            rows.append({
                "pos": r.get("position"), "team": t.get("name"), "crest": t.get("crest"),
                "played": r.get("playedGames"), "won": r.get("won"),
                "draw": r.get("draw"), "lost": r.get("lost"),
                "gf": r.get("goalsFor"), "ga": r.get("goalsAgainst"),
                "gd": r.get("goalDifference"), "pts": r.get("points"),
            })
        out.append({"competition": name, "table": rows,
                    "past": past, "season_label": season_label})
    # any real response -> write the result. ALL calls failed (network) ->
    # None -> keep the last file.
    return out if got_any else None

if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    # a transient upstream failure must NOT kill the whole deploy -
    # keep the last committed data file and continue.
    try:
        news = fetch_news()
    except Exception as e:
        print(f"  ! news fetch failed ({e}) - keeping existing headlines.json")
        news = None
    if news:
        write_items("headlines.json", news)
        print(f"headlines: {len(news)}")
    try:
        matches = fetch_matches()
    except Exception as e:
        print(f"  ! matches fetch failed ({e}) - keeping existing matches.json")
        matches = None
    if matches is not None:
        write_items("matches.json", matches)
        print(f"matches: {len(matches)}")
    try:
        reels_auto = fetch_reels_auto()
    except Exception as e:
        print(f"  ! reels fetch failed ({e}) - keeping existing reels_auto.json")
        reels_auto = None
    if reels_auto is not None:
        write_items("reels_auto.json", reels_auto)
        print(f"reels (auto): {len(reels_auto)}")
    try:
        standings = fetch_standings()
    except Exception as e:
        print(f"  ! standings fetch failed ({e}) - keeping existing standings.json")
        standings = None
    if standings is not None:   # empty list is valid -> clears last-season tables
        write_items("standings.json", standings)
        print(f"standings: {len(standings)} leagues")
