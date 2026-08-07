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
FD_COMPS = ["WC", "CL", "PL", "PD", "SA", "BL1", "FL1"]  # World Cup, UCL, PL, La Liga, Serie A, Bundesliga, Ligue 1

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
    items = items[:60]              # home shows 15; /headlines.html shows all
    _attach_images(items)           # best-effort og:image per headline
    return items

# How many of the newest headlines get an image lookup each run. The home page
# shows 15; a little margin covers dedup shifts between runs.
IMG_ENRICH_TOP = 24

def _attach_images(items):
    """Resolve each Google News link to the publisher page (direct source_url,
    so cards land straight on the outlet like Yahoo does) and hotlink its
    og:image thumbnail (aggregator-style: image stays on the publisher's CDN,
    the card links to the source). Best-effort — any failure just leaves the
    card image-less / on the google link, exactly like before. Results are
    cached in the previous headlines.json so a link is only decoded once."""
    try:
        from googlenewsdecoder import gnewsdecoder
    except Exception as e:
        print(f"  ! googlenewsdecoder not available ({e}) - headline images skipped")
        return
    import ssl
    from concurrent.futures import ThreadPoolExecutor

    # cache from the previous run: link -> (source_url, image)
    cache = {}
    try:
        with open(os.path.join(DATA, "headlines.json"), encoding="utf-8") as f:
            for old in json.load(f)["results"][0]["items"]:
                if old.get("link") and ("image" in old or "source_url" in old):
                    cache[old["link"]] = (old.get("source_url", ""), old.get("image", ""))
    except Exception:
        pass

    lax = ssl.create_default_context()
    lax.check_hostname = False
    lax.verify_mode = ssl.CERT_NONE

    def og_image(page_url):
        req = urllib.request.Request(page_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            body = urllib.request.urlopen(req, timeout=12).read(400000)
        except Exception:
            body = urllib.request.urlopen(req, timeout=12, context=lax).read(400000)
        head = body.decode("utf-8", "replace")
        m = (re.search(r"property=[\"']og:image[\"'][^>]*content=[\"']([^\"']+)", head)
             or re.search(r"content=[\"']([^\"']+)[\"'][^>]*property=[\"']og:image", head))
        url = html.unescape(m.group(1)).strip() if m else ""
        return url if url.startswith("http") else ""

    def decode_link(h):
        cached_url, cached_img = cache.get(h["link"], ("", ""))
        h["image"] = cached_img
        if cached_url:                       # fully cached — done
            h["source_url"] = cached_url
            return
        # not cached, or cached before source_url existed — (re)decode
        try:
            r = gnewsdecoder(h["link"], interval=0)
            h["source_url"] = (r.get("decoded_url") or "") if r.get("status") else ""
        except Exception:
            h["source_url"] = ""

    def fetch_image(h):
        if h.get("image") or not h.get("source_url"):
            return
        try:
            h["image"] = og_image(h["source_url"])
        except Exception:
            h["image"] = ""

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(decode_link, items))                 # direct link for ALL cards
        list(ex.map(fetch_image, items[:IMG_ENRICH_TOP]))  # thumbnails for the top
    direct = sum(1 for h in items if h.get("source_url"))
    got = sum(1 for h in items[:IMG_ENRICH_TOP] if h.get("image"))
    print(f"  + headline direct links: {direct}/{len(items)}, images: {got}/{min(len(items), IMG_ENRICH_TOP)}")

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
_FIXTURES = None   # per-league full-season fixtures by round, set by fetch_matches

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

    def to_row(m, dt):
        comp = m.get("competition") or {}
        ht = m.get("homeTeam") or {}
        at = m.get("awayTeam") or {}
        ft = (m.get("score") or {}).get("fullTime") or {}
        return {
            "match_id": m.get("id"),
            "competition": comp.get("name"),
            "home": ht.get("name"), "away": at.get("name"),
            "home_badge": ht.get("crest"), "away_badge": at.get("crest"),
            "kickoff": dt.strftime("%Y-%m-%d"),
            "koff_time": dt.strftime("%H:%M"),
            "status": _norm_status(m.get("status")),
            "home_score": ft.get("home"), "away_score": ft.get("away"),
            "round": m.get("matchday"),
            "channel": None,
        }

    cutoff = today - timedelta(days=5)
    out = []
    # full-season fixtures grouped by league -> round (for the FotMob rounds view)
    by_league = {}   # comp_name -> {round -> [rows]}
    for m in raw.values():
        utc = m.get("utcDate")
        if not utc:
            continue
        try:
            dt = datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(CAIRO)
        except Exception:
            continue
        comp = m.get("competition") or {}
        if (comp.get("code") or "") not in FD_COMPS:
            continue  # keep only our competitions
        row = to_row(m, dt)
        # rounds view: every fixture, keyed by matchday (skip if no matchday)
        rd = m.get("matchday")
        if rd is not None:
            by_league.setdefault(comp.get("name"), {}).setdefault(int(rd), []).append(row)
        # main day view: recent + upcoming only
        if dt.date() >= cutoff:
            out.append(row)
    out.sort(key=lambda x: (x["kickoff"], x["koff_time"] or ""))

    # build fixtures.json structure: [{competition, current, rounds:[{round,matches}]}]
    global _FIXTURES
    fixtures = []
    today_s = today.isoformat()
    for name, rounds in by_league.items():
        rlist = []
        for rd in sorted(rounds.keys()):
            ms = sorted(rounds[rd], key=lambda x: (x["kickoff"], x["koff_time"] or ""))
            rlist.append({"round": rd, "matches": ms})
        # "current" round = earliest round that still has a match today-or-later
        current = rlist[0]["round"] if rlist else 1
        for r in rlist:
            if any(mm["kickoff"] >= today_s for mm in r["matches"]):
                current = r["round"]
                break
        fixtures.append({"competition": name, "current": current, "rounds": rlist})
    _FIXTURES = fixtures
    return out[:60]

# -------------------------------------------------------------- standings
# league tables for the domestic leagues + UCL league phase
# (World Cup has groups, not a table)
FD_TABLE_COMPS = ["PL", "PD", "SA", "BL1", "FL1", "CL"]

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
        # under the new season id. The site should show the NEW season instead:
        # the new season's team list (incl. promoted clubs) with everything 0.
        start = (j.get("season") or {}).get("startDate") or ""
        started = bool(start) and start[:10] <= today
        maxplayed = max((r.get("playedGames") or 0) for r in table)
        # two pre-season shapes, ONE uniform outcome (badge + alphabetical zeros):
        #  - old_table: API still serves LAST season's final table -> rebuild
        #    from the new season's team list
        #  - fresh_empty: API already serves the new season, nothing played yet
        old_table = (not started) and maxplayed > 0
        fresh_empty = maxplayed == 0
        if maxplayed > 0 and started:
            # the served table may STILL be last edition's (e.g. UCL before the
            # league-phase draw: qualifiers make the season "started" while the
            # 36-team table is last season's). Ground truth: did any match of
            # the MAIN stage finish this season?
            stage = "LEAGUE_STAGE" if comp == "CL" else "REGULAR_SEASON"
            try:
                time.sleep(7)
                fj = json.loads(http_get(
                    f"https://api.football-data.org/v4/competitions/{comp}/matches"
                    f"?status=FINISHED&stage={stage}", hdr))
                n_fin = (fj.get("resultSet") or {}).get("count")
                if n_fin is None:
                    n_fin = len(fj.get("matches") or [])
                if int(n_fin) == 0:
                    old_table = True
                    print(f"  · standings {comp}: table has results but no {stage} "
                          f"match finished this season -> stale, rebuilding")
            except Exception as e:
                print(f"  ! finished-check {comp} failed ({e}) - keeping table as-is")
        name = (j.get("competition") or {}).get("name") or comp
        if (not old_table) and maxplayed > 0 and _FIXTURES is not None:
            # second stale signal: a table with results while the competition
            # has NO fixture rounds at all this season (UCL before the draw)
            # cannot belong to the current season.
            has_rounds = any(f.get("competition") == name and f.get("rounds")
                             for f in _FIXTURES)
            if not has_rounds:
                old_table = True
                print(f"  · standings {comp}: results present but no fixtures "
                      f"exist this season -> stale, rebuilding")
        zeroed = old_table or fresh_empty
        season_label = ""
        if zeroed:
            # season start year; if the API still reports LAST season (stale
            # UCL case) bump to the current football season (starts ~July)
            now_c = datetime.now(CAIRO)
            cur_y = now_c.year if now_c.month >= 7 else now_c.year - 1
            try:
                y = int(start[:4])
            except Exception:
                y = cur_y
            y = max(y, cur_y)
            season_label = f"{y}/{y+1}"          # the season about to start
        if fresh_empty:
            # already the right clubs — just normalize to alphabetical order
            table.sort(key=lambda r: ((r.get("team") or {}).get("name") or ""))
            for i, r in enumerate(table):
                r["position"] = i + 1
            print(f"  · standings {comp}: new season, nothing played -> badge ({season_label})")
        if old_table:
            teams = None
            try:
                time.sleep(7)                    # stay inside 10 req/min
                tj = json.loads(http_get(
                    f"https://api.football-data.org/v4/competitions/{comp}/teams", hdr))
                teams = tj.get("teams") or None
            except Exception as e:
                print(f"  ! teams {comp} failed ({e}) - zeroing last season's team list instead")
            if teams:
                teams.sort(key=lambda t: (t.get("name") or ""))
                table = [{"position": i + 1, "team": t} for i, t in enumerate(teams)]
            else:
                # fallback: same clubs as last season, alphabetical, all zeros
                table.sort(key=lambda r: ((r.get("team") or {}).get("name") or ""))
                table = [{"position": i + 1, "team": r.get("team") or {}}
                         for i, r in enumerate(table)]
            for r in table:
                r.update({"playedGames": 0, "won": 0, "draw": 0, "lost": 0,
                          "goalsFor": 0, "goalsAgainst": 0,
                          "goalDifference": 0, "points": 0})
            print(f"  · standings {comp}: new season not started -> zeroed table ({season_label})")
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
                    "zeroed": zeroed, "season_label": season_label})
    # any real response -> write the result. ALL calls failed (network) ->
    # None -> keep the last file.
    return out if got_any else None

# --------------------------------------- Egyptian Premier League (365scores)
# football-data.org's free tier has no Egyptian league, and TheSportsDB's
# data for it proved stale/wrong (2026-08: old 24-team list, no new-season
# fixtures days after the draw). 365scores' public web API has the full
# fixture list the day the draw happens, native Arabic team names, and
# Cairo kickoff times. Entirely best-effort: any failure just means the
# Egyptian league is absent this run, FD data is untouched.
S365 = "https://webws.365scores.com/web"
EGY_365_ID = 552                        # competition id on 365scores
EGY_NAME = "Egyptian Premier League"    # data-comp key used across the site
EGY_ENABLED = True                      # flip to False to drop the league again
_EGY_Q = f"competitions={EGY_365_ID}&langId=27&timezoneName=Africa/Cairo"

def _s365(path):
    # full browser-ish headers: webws.365scores.com sits behind Cloudflare and
    # a bare python UA from a datacenter IP (GitHub runner) risks a 403
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36",
         "Accept": "application/json, text/plain, */*",
         "Accept-Language": "ar,en;q=0.9",
         "Origin": "https://www.365scores.com",
         "Referer": "https://www.365scores.com/"}
    return json.loads(http_get(f"{S365}/{path}", headers=h, timeout=30, retries=1))

def _s365_badge(c):
    return ("https://imagecache.365scores.com/image/upload/"
            "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,d_Competitors:default1.png/"
            f"v{c.get('imageVersion', 1)}/Competitors/{c.get('id')}")

def _egy_season():
    now = datetime.now(CAIRO)
    y = now.year if now.month >= 7 else now.year - 1
    return f"{y}-{y+1}"

def fetch_egypt(matches_out):
    """Append Egyptian Premier League rows to matches_out, add its rounds
    panel to _FIXTURES, and return a standings entry (or None)."""
    comp = (_s365(f"competitions/?{_EGY_Q}").get("competitions") or [{}])[0]
    season_num = comp.get("currentSeasonNum")   # e.g. 74 = 2026/27

    def game_row(g):
        st = g.get("statusGroup")               # 2 scheduled, 3 live, 4 ended
        status = "LIVE" if st == 3 else ("FINISHED" if st == 4 else "UPCOMING")
        date, tm = "", ""
        try:
            dt = datetime.fromisoformat(g.get("startTime") or "").astimezone(CAIRO)
            date, tm = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
        except Exception:
            s = g.get("startTime") or ""
            date, tm = s[:10], s[11:16]
        h, a = g.get("homeCompetitor") or {}, g.get("awayCompetitor") or {}
        hs, aws = h.get("score"), a.get("score")
        scored = status != "UPCOMING" and (hs or 0) >= 0 and (aws or 0) >= 0
        rd = g.get("roundNum")
        return {
            "match_id": g.get("id"), "competition": EGY_NAME,
            "home": h.get("name"), "away": a.get("name"),
            "home_badge": _s365_badge(h), "away_badge": _s365_badge(a),
            "kickoff": date, "koff_time": tm,
            "status": status,
            "home_score": int(hs) if scored else None,
            "away_score": int(aws) if scored else None,
            "round": int(rd) if rd else None,
            "channel": None,
        }

    rows, seen = [], set()
    for path in (f"games/fixtures/?{_EGY_Q}&showOdds=false",
                 f"games/results/?{_EGY_Q}&showOdds=false"):
        try:
            time.sleep(1)
            for g in (_s365(path).get("games") or []):
                # results/ also returns last season's games - keep current only
                if season_num and g.get("seasonNum") != season_num:
                    continue
                r = game_row(g)
                if r["match_id"] not in seen and r["kickoff"]:
                    seen.add(r["match_id"])
                    rows.append(r)
        except Exception as e:
            print(f"  ! 365scores {path.split('?')[0]} failed: {e}")

    today = datetime.now(CAIRO).date()
    cutoff = (today - timedelta(days=5)).isoformat()
    day_rows = [r for r in rows if r["kickoff"] >= cutoff or r["status"] == "LIVE"]
    matches_out.extend(day_rows)

    # rounds panel
    global _FIXTURES
    rounds = {}
    for r in rows:
        if r.get("round"):
            rounds.setdefault(r["round"], []).append(r)
    if rounds:
        rlist = [{"round": rd,
                  "matches": sorted(ms, key=lambda x: (x["kickoff"], x["koff_time"] or ""))}
                 for rd, ms in sorted(rounds.items())]
        today_s = today.isoformat()
        current = rlist[0]["round"]
        for rr in rlist:
            if any(mm["kickoff"] >= today_s for mm in rr["matches"]):
                current = rr["round"]
                break
        if _FIXTURES is None:
            _FIXTURES = []
        _FIXTURES.append({"competition": EGY_NAME, "current": current, "rounds": rlist})

    # standings
    entry = None
    try:
        time.sleep(1)
        srows = (_s365(f"standings/?{_EGY_Q}&live=false").get("standings")
                 or [{}])[0].get("rows") or []
    except Exception as e:
        print(f"  ! 365scores standings failed: {e}")
        srows = []
    n = lambda v: int(v or 0)
    if srows:
        played = max(n(r.get("gamePlayed")) for r in srows)
        entry = {"competition": EGY_NAME, "zeroed": played == 0,
                 "season_label": _egy_season().replace("-", "/") if played == 0 else "",
                 "table": [{"pos": n(r.get("position")) or i + 1,
                            "team": (r.get("competitor") or {}).get("name"),
                            "crest": _s365_badge(r.get("competitor") or {}),
                            "played": n(r.get("gamePlayed")), "won": n(r.get("gamesWon")),
                            "draw": n(r.get("gamesEven")), "lost": n(r.get("gamesLost")),
                            "gf": n(r.get("for")), "ga": n(r.get("against")),
                            "gd": n(r.get("for")) - n(r.get("against")),
                            "pts": n(r.get("points"))}
                           for i, r in enumerate(srows)]}
    print(f"  + Egyptian league (365scores): {len(day_rows)} matches, "
          f"{len(rounds)} rounds, table: {'yes' if entry else 'no'}")
    return entry

if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    # a transient upstream failure must NOT kill the whole deploy -
    # keep the last committed data file and continue.
    # _DBG lands in data/fetch_debug.json and is committed back by the Action,
    # so runner-side failures are visible without access to the job logs.
    _DBG = {}
    try:
        news = fetch_news()
        _DBG["news"] = f"ok ({len(news)})"
    except Exception as e:
        print(f"  ! news fetch failed ({e}) - keeping existing headlines.json")
        _DBG["news"] = f"FAIL: {e!r}"
        news = None
    if news:
        write_items("headlines.json", news)
        print(f"headlines: {len(news)}")
    try:
        matches = fetch_matches()
        _DBG["matches"] = f"ok ({len(matches)})"
    except Exception as e:
        print(f"  ! matches fetch failed ({e}) - keeping existing matches.json")
        _DBG["matches"] = f"FAIL: {e!r}"
        matches = None
    egy_standing = None
    if matches is not None and EGY_ENABLED:
        try:
            egy_standing = fetch_egypt(matches)
            _DBG["egypt"] = (f"ok (table {len(egy_standing['table'])} teams)"
                             if egy_standing else "ok (no table)")
            matches.sort(key=lambda x: (x["kickoff"], x["koff_time"] or ""))
            matches = matches[:90]
        except Exception as e:
            print(f"  ! Egyptian league fetch failed ({e})")
            _DBG["egypt"] = f"FAIL: {e!r}"
        write_items("matches.json", matches)
        print(f"matches: {len(matches)}")
    if _FIXTURES is not None:
        write_items("fixtures.json", _FIXTURES)
        print(f"fixtures: {len(_FIXTURES)} leagues, "
              f"{sum(len(l['rounds']) for l in _FIXTURES)} rounds")
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
        _DBG["standings"] = f"ok ({len(standings)})"
    except Exception as e:
        print(f"  ! standings fetch failed ({e}) - keeping existing standings.json")
        _DBG["standings"] = f"FAIL: {e!r}"
        standings = None
    if standings is not None:   # empty list is valid -> clears last-season tables
        if egy_standing:
            standings.append(egy_standing)
        write_items("standings.json", standings)
        print(f"standings: {len(standings)} leagues")
    _DBG["utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(os.path.join(DATA, "fetch_debug.json"), "w", encoding="utf-8") as f:
        json.dump(_DBG, f, ensure_ascii=False, indent=1)
