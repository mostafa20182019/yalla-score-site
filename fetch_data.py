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
FD_COMPS = ["CL", "PL", "PD", "SA", "BL1", "FL1"]  # UCL, PL, La Liga, Serie A, Bundesliga, Ligue 1 (WC removed 2026-08-12: tournament over)

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

# Outlets blocked inside Egypt (user request 2026-08-08): their pages don't
# open for Egyptian visitors, so a headline linking there is a dead card.
# Matched against the RSS <source> name AND the decoded publisher domain.
BLOCKED_SOURCE_NAMES = ("الجزيرة", "العربي الجديد", "عربي21", "عربي بوست",
                        "TRT", "مدى مصر", "نون بوست", "ساسة بوست", "رصد")
BLOCKED_DOMAINS = ("aljazeera.", "alaraby.", "arabi21.", "arabicpost.",
                   "trtarabi.", "madamasr.", "noonpost.", "sasapost.", "rassd.")

def _blocked_in_egypt(item):
    src = item.get("source") or ""
    if any(b in src for b in BLOCKED_SOURCE_NAMES):
        return True
    host = urllib.parse.urlparse(item.get("source_url") or "").netloc.lower()
    return any(b in host for b in BLOCKED_DOMAINS)

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
    items = [it for it in items if not _blocked_in_egypt(it)]   # by source name
    items.sort(key=lambda x: x.get("pub_iso") or "", reverse=True)
    items = _dedup_stories(items)   # one card per story, not per outlet
    items = items[:60]              # home shows 15; /headlines.html shows all
    _attach_images(items)           # best-effort og:image per headline
    # second pass: _attach_images decoded google links -> real publisher
    # domains, so blocked outlets hiding behind a different RSS name drop here
    items = [it for it in items if not _blocked_in_egypt(it)]
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
        # NO status filter: ?status=SCHEDULED silently dropped matches whose
        # kickoff got officially confirmed (football-data flips them to
        # TIMED) - La Liga rounds 1-4 vanished from the rounds panel that
        # way (2026-08-10). Unfiltered = full season, every status.
        pull(f"https://api.football-data.org/v4/competitions/{comp}/matches")
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
        # FD's competition endpoint can lag the status while the live score
        # is already flowing (seen 2026-08-16: kicked-off match still TIMED
        # but carrying 1-0) - a "scheduled" match with a score whose kickoff
        # has passed is actually LIVE
        if (row["status"] == "UPCOMING" and row["home_score"] is not None
                and dt <= datetime.now(CAIRO)):
            row["status"] = "LIVE"
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
# leagues served from 365scores (football-data's free tier lacks them):
# (competition id, data-comp key used across the site)
S365_LEAGUES = [
    (552, "Egyptian Premier League"),   # الدوري المصري
    (78,  "Turkish Super Lig"),         # الدوري التركي (Salah's Trabzonspor)
    (649, "Saudi Pro League"),          # الدوري السعودي
]
EGY_ENABLED = True                      # master switch for the 365scores leagues

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

def fetch_s365_league(matches_out, lid, comp_name):
    """Append one 365scores league's rows to matches_out, add its rounds
    panel to _FIXTURES, and return a standings entry (or None)."""
    q = f"competitions={lid}&langId=27&timezoneName=Africa/Cairo"
    comp = (_s365(f"competitions/?{q}").get("competitions") or [{}])[0]
    season_num = comp.get("currentSeasonNum")   # e.g. 74 = 2026/27

    def game_row(g):
        st = g.get("statusGroup")               # 2 scheduled, 3 live, 4 ended
        status = "LIVE" if st == 3 else ("FINISHED" if st == 4 else "UPCOMING")
        # a POSTPONED game arrives as statusGroup 4 with no scores (بترول
        # اسيوط x بتروجت 22/08 rendered as "انتهت -") - ended without a
        # result isn't finished, it never happened
        h0, a0 = (g.get("homeCompetitor") or {}).get("score"), (g.get("awayCompetitor") or {}).get("score")
        if status == "FINISHED" and ((h0 is None or h0 < 0) or (a0 is None or a0 < 0)):
            status = "POSTPONED"
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
            "match_id": g.get("id"), "competition": comp_name,
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
    # current/ FIRST: a match that is IN PLAY is in NEITHER fixtures nor
    # results (it vanished from the day view for 90 minutes - user caught
    # it twice, 2026-08-16); listing current first also makes the live
    # version win the match_id dedup
    for path in (f"games/current/?{q}&showOdds=false",
                 f"games/fixtures/?{q}&showOdds=false",
                 f"games/results/?{q}&showOdds=false"):
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
        _FIXTURES.append({"competition": comp_name, "current": current, "rounds": rlist})

    # standings
    entry = None
    try:
        time.sleep(1)
        srows = (_s365(f"standings/?{q}&live=false").get("standings")
                 or [{}])[0].get("rows") or []
    except Exception as e:
        print(f"  ! 365scores standings failed: {e}")
        srows = []
    n = lambda v: int(v or 0)
    if srows:
        played = max(n(r.get("gamePlayed")) for r in srows)
        entry = {"competition": comp_name, "zeroed": played == 0,
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
    print(f"  + {comp_name} (365scores): {len(day_rows)} matches, "
          f"{len(rounds)} rounds, table: {'yes' if entry else 'no'}")
    return entry

# ------------------------------------------- Top transfers (365scores)
# FotMob-style "أبرز الانتقالات" widget on the home page. Confirmed moves
# only (no rumors, no contract extensions), newest first, Arabic native.
# Only these clubs' deals appear (user pick 2026-08-08) — 365scores
# competitor ids, matched by id (names like "الأهلي" collide across leagues):
# Real Madrid 131, Barcelona 132, Man United 105, Man City 110, Arsenal 104,
# Chelsea 106, Liverpool 108, Al Ahly 8200, Zamalek 8201, Trabzonspor 950.
# ---------------------------------------------------------------- goal events
# Who scored, per match — 365scores game detail (Arabic player names). Shown
# under the match rows on /matches.html. Only games that can still be on the
# page need details: LIVE ones and FINISHED ones from the last few days, and
# only when at least one goal was scored. The game/ endpoint shape follows the
# other web/ endpoints; a raw sample of the first response is reported through
# fetch_debug.json so a wrong field guess is diagnosable from the runner.
GOAL_DAYS_BACK = 4          # matches this recent keep their scorer lines
GOAL_DETAIL_CAP = 45        # per-run ceiling on game/ detail calls
S365_ALL_COMPS = "552,78,649,7,11,17,25,35,572"

def _goal_rows(game, fallback_home_id):
    """game detail -> (goals list, health) — tolerant of field-name drift."""
    members = {m.get("id"): m.get("name") for m in (game.get("members") or [])}
    home = game.get("homeCompetitor") or {}
    home_id = home.get("id") or fallback_home_id
    goals = []
    for ev in (game.get("events") or []):
        et = ev.get("eventType") or ev.get("type") or {}
        nm = (et.get("name") or "") if isinstance(et, dict) else str(et)
        if "هدف" not in nm:
            continue
        # a goal DISALLOWED by VAR is still named "هدف ..." — it must not be
        # listed (it inflated counts vs the scoreboard in 3 games on 18-08)
        if "ملغ" in nm or "ألغي" in nm or "الغي" in nm:
            continue
        cid = ev.get("competitorId")
        if cid is None:                     # some payloads carry num 1/2 instead
            cid = home_id if ev.get("num") == 1 else -1
        side = "h" if cid == home_id else "a"
        player = members.get(ev.get("playerId"))
        if not player and isinstance(ev.get("player"), dict):
            player = ev["player"].get("name")
        if not player:
            player = ev.get("playerName")
        if not player:
            continue
        minute = ""
        try:
            gt = int(float(ev.get("gameTime")))
            if gt > 0:
                add = ev.get("addedTime")
                minute = f"{gt}+{int(add)}" if add and int(add) > 0 else str(gt)
        except (TypeError, ValueError):
            pass
        tag = ""
        sub = f'{nm} {ev.get("subTypeName") or ""}'
        if "عكس" in sub:
            tag = "عكسية"
        elif "جزاء" in sub:
            tag = "ج"
        goals.append({"side": side, "player": player, "minute": minute, "tag": tag})
    # sanity: per-side counts must match the scoreboard. A mismatch that own
    # goals explain means 365scores credited them to the scorer's own team —
    # flip those to the benefiting side. Still wrong after that -> drop the
    # match entirely rather than publish miscredited scorers.
    hs = int(home.get("score") or 0)
    as_ = int((game.get("awayCompetitor") or {}).get("score") or 0)
    def counts():
        return (sum(1 for g in goals if g["side"] == "h"),
                sum(1 for g in goals if g["side"] == "a"))
    if counts() != (hs, as_):
        for g in goals:
            if g["tag"] == "عكسية":
                g["side"] = "a" if g["side"] == "h" else "h"
        if counts() != (hs, as_):
            # name every counted event so the next mismatch diagnoses itself
            evs = "/".join(f'{g["side"]}:{g.get("tag") or "g"}@{g.get("minute")}'
                           for g in goals)
            return [], f"count-mismatch {counts()} vs {hs}-{as_} [{evs}]"
    return goals, "ok"

def fetch_goal_events():
    """[{home, away, date, goals:[{side,player,minute,tag}]}] + a debug dict."""
    today = datetime.now(CAIRO).date()
    cutoff = (today - timedelta(days=GOAL_DAYS_BACK)).isoformat()
    q = f"competitions={S365_ALL_COMPS}&langId=27&timezoneName=Africa/Cairo"
    cands = {}
    for path in (f"games/current/?{q}&showOdds=false",
                 f"games/results/?{q}&showOdds=false"):
        try:
            time.sleep(1)
            for g in (_s365(path).get("games") or []):
                if g.get("statusGroup") not in (3, 4):
                    continue
                h, a = g.get("homeCompetitor") or {}, g.get("awayCompetitor") or {}
                if not ((h.get("score") or 0) > 0 or (a.get("score") or 0) > 0):
                    continue                # goalless — no scorer line to show
                try:
                    dt = datetime.fromisoformat(g.get("startTime") or "").astimezone(CAIRO)
                    date = dt.strftime("%Y-%m-%d")
                except Exception:
                    date = (g.get("startTime") or "")[:10]
                if g.get("statusGroup") == 4 and (not date or date < cutoff):
                    continue
                cands[g.get("id")] = (g, date)
        except Exception as e:
            print(f"  ! goal-events {path.split('?')[0]} failed: {e}")
    out, dbg = [], {"candidates": len(cands), "detail_fails": 0, "skipped": []}
    for gid, (g0, date) in list(cands.items())[:GOAL_DETAIL_CAP]:
        try:
            time.sleep(0.6)
            j = _s365(f"game/?appTypeId=5&langId=27&gameId={gid}")
        except Exception as e:
            dbg["detail_fails"] += 1
            continue
        game = j.get("game") or {}
        if "sample" not in dbg:             # one raw sample for diagnosis
            dbg["sample"] = {
                "game_keys": list(game)[:24],
                "event0": json.dumps((game.get("events") or [None])[0],
                                     ensure_ascii=False, default=str)[:700],
                "member0": json.dumps((game.get("members") or [None])[0],
                                      ensure_ascii=False, default=str)[:250]}
        goals, health = _goal_rows(game, (g0.get("homeCompetitor") or {}).get("id"))
        if not goals:
            if health != "ok":
                dbg["skipped"].append(f"{gid}:{health}")
            continue
        h = game.get("homeCompetitor") or g0.get("homeCompetitor") or {}
        a = game.get("awayCompetitor") or g0.get("awayCompetitor") or {}
        out.append({"home": h.get("name"), "away": a.get("name"),
                    "date": date, "goals": goals})
    dbg["skipped"] = dbg["skipped"][:6]
    return out, dbg

# ---------------------------------------------------------------- top scorers
# 365scores is the source: Arabic player names for EVERY league, including the
# Egyptian/Turkish/Saudi ones football-data's free tier doesn't carry.
# Endpoint (found by probing on the runner - the host is DNS-blocked on the
# office network): stats/?appTypeId=5&langId=27&competitions=<ids>
#   {"stats":{"athletesStats":[{"id":1,"name":"الأهداف","competitionId":552,
#      "rows":[{"entity":{"id":,"name":,"competitorId":,"imageVersion":},
#               "stats":[{"typeId":1,"value":"13"},{"typeId":10,...}]}]}]},
#    "competitors":[...]}   <- lookup array for the club names
# Category id 1 = goals; typeId 1 = the goal count; typeId 10 = penalties.
# NOTE the feed carries LAST season's list until a new season produces goals,
# so build_site sanity-checks the totals before rendering anything.
SCORERS_TOP = 5

# competition id -> the name matches/standings/fixtures already use, so
# build_site can key scorers by competition like every other section
S365_SCORER_COMPS = [
    (552, "Egyptian Premier League"), (78, "Turkish Super Lig"),
    (649, "Saudi Pro League"), (7, "Premier League"),
    (11, "Primera Division"), (17, "Serie A"), (25, "Bundesliga"),
    (35, "Ligue 1"), (572, "UEFA Champions League"),
]

# the response carries several athlete charts per competition; these are the
# two we render. cat_id is 365scores' category id (1 = goals, confirmed by the
# probe), names = the Arabic titles to fall back on when the id differs.
# ids are stable across leagues (verified on all 9 via fetch_debug):
#   1 الأهداف · 2 أهداف متوقعة · 3 صناعة · 4 صناعة أهداف متوقعة
#   5 أهداف + صناعة · 11/12 بطاقات · 13 شباك نظيفة …
# Titles are matched EXACTLY, never as a substring: "صناعة" appears inside
# "صناعة أهداف متوقعة" (expected assists) too, and a later match would win.
S365_CHARTS = [
    ("goals",   1, ("الأهداف",)),
    ("assists", 3, ("صناعة",)),
]

def s365_chart_names(j):
    """The available charts as "id:title" - reported in data/fetch_debug.json so
    a renamed or missing chart is visible instead of failing silently. The list
    is identical for every league, so one competition's copy is enough."""
    for cat in ((j.get("stats") or {}).get("athletesStats") or []):
        cid = cat.get("competitionId")
        return {cid: [f'{c.get("id")}:{c.get("name")}'
                      for c in ((j.get("stats") or {}).get("athletesStats") or [])
                      if c.get("competitionId") == cid]}
    return {}

def _s365_stat_rows(j, want, cat_id=1, cat_names=("الأهداف",)):
    """Parse one athlete chart -> {competition_id: [row, ...]}."""
    clubs = {c.get("id"): c for c in (j.get("competitors") or [])}
    out = {}
    for cat in ((j.get("stats") or {}).get("athletesStats") or []):
        cid = cat.get("competitionId")
        if cid not in want:
            continue
        nm = (cat.get("name") or "").strip()
        if not ((cat_id is not None and cat.get("id") == cat_id)
                or nm in cat_names):
            continue                      # not the chart we want
        rows = []
        for r in (cat.get("rows") or []):
            e = r.get("entity") or {}
            val = next((st.get("value") for st in (r.get("stats") or [])
                        if st.get("typeId") == 1), None)
            if val is None and r.get("stats"):
                val = (r["stats"][0] or {}).get("value")
            try:
                goals = int(float(val))
            except (TypeError, ValueError):
                continue
            if goals <= 0 or not e.get("name"):
                continue
            club = clubs.get(e.get("competitorId")) or {}
            rows.append({"name": e["name"], "team": club.get("name") or "",
                         "crest": _s365_badge(club) if club.get("id") else "",
                         "photo": _s365_face(e), "value": goals, "goals": goals,
                         "played": 0})    # the feed carries no matches-played
            if len(rows) >= SCORERS_TOP:
                break
        if rows:
            out[cid] = rows
    return out

def fetch_player_charts():
    """Top scorers + top assisters per league, from ONE response per request.
    Returns ({chart_key: [{competition, scorers|assists}]}, chart_names)."""
    want = {lid: name for lid, name in S365_SCORER_COMPS}
    charts = {key: {} for key, _, _ in S365_CHARTS}
    names = {}

    def harvest(j, subset):
        names.update(s365_chart_names(j))
        for key, cid, titles in S365_CHARTS:
            charts[key].update(_s365_stat_rows(j, subset, cid, titles))

    try:
        ids = ",".join(str(i) for i in want)
        harvest(_s365(f"stats/?appTypeId=5&langId=27&competitions={ids}"), want)
    except Exception as e:
        print(f"  ! player charts combined call failed ({e}) - per league")
    # goals decides coverage: a league missing from it got no usable response
    missing = [i for i in want if i not in charts["goals"]]
    if missing and len(missing) < len(want):
        print(f"  · player charts: combined call covered "
              f"{len(want) - len(missing)}/{len(want)} leagues")
    for lid in missing:
        try:
            harvest(_s365(f"stats/?appTypeId=5&langId=27&competitions={lid}"),
                    {lid: want[lid]})
        except Exception as e:
            print(f"  ! player charts {want[lid]} failed: {e}")
    field = {"goals": "scorers", "assists": "assists"}
    out = {key: [{"competition": want[lid], field[key]: rows}
                 for lid, rows in got.items() if rows]
           for key, got in charts.items()}
    return out, names

TRANSFER_CLUBS = "131,132,105,110,104,106,108,8200,8201,950"

def _s365_face(a):
    return ("https://imagecache.365scores.com/image/upload/"
            "f_png,w_64,h_64,c_limit,q_auto:eco,dpr_2,d_Athletes:default.png/"
            f"v{a.get('imageVersion', 1)}/Athletes/{a.get('id')}")

def fetch_transfers():
    d = _s365(f"transfers/?langId=27&appTypeId=5&competitors={TRANSFER_CLUBS}")
    comps = {c["id"]: c for c in d.get("competitors") or []}
    aths = {a["id"]: a for a in d.get("athletes") or []}
    out = []
    for t in d.get("transfers") or []:
        if t.get("statusName") != "انتقالات تمت":   # confirmed only - no rumors
            continue
        if t.get("type") == 8:                      # contract extension, not a move
            continue
        a = aths.get(t.get("athleteId"))
        o = comps.get(t.get("origin")) or {}
        g = comps.get(t.get("target")) or {}
        if not a or not o.get("id") or not g.get("id"):
            continue
        if g.get("name") == "بدون نادي":
            continue    # released into the void - not a signing
        # (origin "بدون نادي" is KEPT: a free-agent ARRIVAL is a real deal -
        #  e.g. Salah -> Trabzonspor after terminating his Liverpool contract)
        out.append({
            "player": a.get("name"),
            "img": _s365_face(a),
            "from": o.get("name"),
            "from_crest": _s365_badge(o),
            "to": g.get("name"),
            "to_crest": _s365_badge(g),
            "price": "" if (t.get("price") or "").strip() in ("", "-")
                     else t["price"].strip(),
            # free-agent signing INTO one of our curated clubs = notable even
            # with no fee (ranked like a mid-size transfer below)
            "free_in": (t.get("price") or "").strip() == "انتقال حر"
                       and str(g.get("id")) in TRANSFER_CLUBS.split(","),
            "time": (t.get("time") or "")[:10],
        })
    def _fee(t):
        m = re.match(r"€([\d.]+)([MK])", t.get("price") or "")
        if m:
            return float(m.group(1)) * (1_000_000 if m.group(2) == "M" else 1_000)
        return 10_000_000.0 if t.get("free_in") else 0.0

    # "أبرز" = hybrid: the last 14 days' deals sorted by fee (big money on
    # top) so the list stays both fresh and notable; when the window is
    # quiet (<4 deals) fall back to plain newest-first so it never empties.
    out.sort(key=lambda x: x["time"] or "", reverse=True)
    cutoff = (datetime.now(CAIRO) - timedelta(days=14)).strftime("%Y-%m-%d")
    recent = [t for t in out if (t["time"] or "") >= cutoff]
    if len(recent) >= 4:
        recent.sort(key=lambda x: (_fee(x), x["time"] or ""), reverse=True)
        return recent[:12]
    return out[:12]

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
    s365_standings = []
    if matches is not None and EGY_ENABLED:
        for _lid, _lname in S365_LEAGUES:
            try:
                _st = fetch_s365_league(matches, _lid, _lname)
                _DBG[_lname] = (f"ok (table {len(_st['table'])} teams)"
                                if _st else "ok (no table)")
                if _st:
                    s365_standings.append(_st)
            except Exception as e:
                print(f"  ! {_lname} fetch failed ({e})")
                _DBG[_lname] = f"FAIL: {e!r}"
        matches.sort(key=lambda x: (x["kickoff"], x["koff_time"] or ""))
        matches = matches[:90]
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
        standings.extend(s365_standings)
        write_items("standings.json", standings)
        print(f"standings: {len(standings)} leagues")
    try:
        transfers = fetch_transfers()
        _DBG["transfers"] = f"ok ({len(transfers)})"
    except Exception as e:
        print(f"  ! transfers fetch failed ({e}) - keeping existing transfers.json")
        _DBG["transfers"] = f"FAIL: {e!r}"
        transfers = None
    if transfers:
        write_items("transfers.json", transfers)
        print(f"transfers: {len(transfers)}")
    try:
        charts, chart_names = fetch_player_charts()
        for key, field, fname in (("goals", "scorers", "scorers.json"),
                                  ("assists", "assists", "assists.json")):
            rows = charts[key]
            _DBG[key] = "ok (" + ", ".join(
                f"{r['competition']}:{len(r[field])}" for r in rows) + ")"
            if rows:
                write_items(fname, rows)
                print(f"{key}: {len(rows)} leagues")
        _DBG["s365_charts"] = chart_names
    except Exception as e:
        print(f"  ! player charts failed ({e}) - keeping existing files")
        _DBG["goals"] = _DBG["assists"] = f"FAIL: {e!r}"
    try:
        goal_events, ge_dbg = fetch_goal_events()
        _DBG["goal_events"] = f"ok ({len(goal_events)} games)"
        _DBG["goal_events_dbg"] = ge_dbg
        write_items("goal_events.json", goal_events)
        print(f"goal events: {len(goal_events)} games")
    except Exception as e:
        print(f"  ! goal events failed ({e}) - keeping existing goal_events.json")
        _DBG["goal_events"] = f"FAIL: {e!r}"
    _DBG["utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(os.path.join(DATA, "fetch_debug.json"), "w", encoding="utf-8") as f:
        json.dump(_DBG, f, ensure_ascii=False, indent=1)
