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
import json, os, re, html, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FD_TOKEN = os.environ.get("FD_TOKEN", "").strip()
CAIRO = ZoneInfo("Africa/Cairo")
UA = "Mozilla/5.0 (YallaScore static-site builder)"
FD_COMPS = ["WC", "PL", "PD", "SA", "BL1", "FL1"]  # World Cup, PL, La Liga, Serie A, Bundesliga, Ligue 1

def http_get(url, headers=None, timeout=40):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def write_items(name, items):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump({"results": [{"items": items}]}, f, ensure_ascii=False)

def _unescape(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    return html.unescape(s).strip()

# ------------------------------------------------------------------ news
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
    return items[:30]

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

if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    news = fetch_news()
    write_items("headlines.json", news)
    print(f"headlines: {len(news)}")
    matches = fetch_matches()
    if matches is not None:
        write_items("matches.json", matches)
        print(f"matches: {len(matches)}")
