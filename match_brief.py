#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yalla Score - match-analysis brief builder for the curated clubs.

Feeds the AI match articles (.github/prompts/match-article.md) with REAL
numbers only, gathered from data we already carry plus 365scores' head-to-head
endpoint, so the writer never has to invent a statistic:

  * standings row of both clubs (pos, P, W, D, L, GF, GA, pts)
  * season form (last 5) + home/away record, from fixtures.json
  * top scorers / assist makers of both clubs in their league (scorers.json / assists.json)
  * both clubs' recent goals with scorers + minutes (goal_events.json)
  * head-to-head + recent games from 365scores (games/h2h) when the game can be resolved
  * REPORT only: final score, goals timeline, formations, lineups with player
    ratings (best 3 per side), cards, substitutions (match_details.json)

Usage (from this folder):
  python match_brief.py --list                 # candidates: previews + reports for curated clubs
  python match_brief.py --pick                 # ONE candidate as JSON {"match_id":..,"kind":..} or {}
  python match_brief.py --brief 4805134 --kind report [--out /tmp/brief.json]
  python match_brief.py --brief 560569  --kind preview

Candidate rules:
  preview = UPCOMING curated match kicking off in PREVIEW_MIN_H..PREVIEW_MAX_H hours
  report  = FINISHED curated match that ended within REPORT_MAX_H hours and has
            goal events or lineups in our data (no data = nothing to analyse yet)
  dedup   = an article in data/articles.json with the same match_id AND kind
  cap     = at most DAILY_CAP match articles per day (Cairo); Egyptian clubs first,
            reports before previews
"""
import argparse, datetime, json, os, re, sys
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as b

CAIRO = ZoneInfo("Africa/Cairo")
PREVIEW_MIN_H, PREVIEW_MAX_H = 2.0, 30.0
REPORT_MAX_H = 8.0
DAILY_CAP = 8
EGY_FIRST = ("الأهلي", "الزمالك", "بيراميدز")

S365_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ar,en;q=0.9",
    "Origin": "https://www.365scores.com",
    "Referer": "https://www.365scores.com/",
}
S365_ALL = "552,78,649,7,11,17,25,35,572,624"


# ---------------------------------------------------------------- helpers
def _now():
    return datetime.datetime.now(CAIRO)

def _kick(m):
    try:
        return datetime.datetime.fromisoformat(
            f"{m['kickoff']}T{m.get('koff_time') or '00:00'}:00").replace(tzinfo=CAIRO)
    except Exception:
        return None

def _norm(s):
    s = (s or "").strip()
    s = re.sub("[أإآ]", "ا", s).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"[\s\.\-']", "", s).lower()

def curated_club(m):
    """(club page dict) for the FIRST curated club in this match, else None."""
    for tp in b.TEAM_PAGES:
        if b._team_match(tp, m):
            return tp
    return None

def curated_clubs(m):
    return [tp for tp in b.TEAM_PAGES if b._team_match(tp, m)]

def _s365(path):
    import urllib.request
    req = urllib.request.Request("https://webws.365scores.com/web/" + path, headers=S365_HEADERS)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ---------------------------------------------------------------- data
def load_all():
    return {
        "matches": b.load("matches.json"),
        "fixtures": b.load("fixtures.json"),
        "standings": b.load("standings.json"),
        "scorers": b.load("scorers.json"),
        "assists": b.load("assists.json"),
        "goal_events": b.load("goal_events.json"),
        "details": b.load("match_details.json"),
        "articles": b.load("articles.json"),
    }

def existing_kinds(articles):
    """{(match_id, kind)} already published."""
    out = set()
    for a in articles:
        if a.get("match_id") and a.get("kind"):
            out.add((str(a["match_id"]), a["kind"]))
    return out

def today_count(articles):
    today = _now().date().isoformat()
    return sum(1 for a in articles if a.get("kind") in ("preview", "report")
               and (a.get("pub_date") or "") == today)


def candidates(d, now=None):
    now = now or _now()
    done = existing_kinds(d["articles"])
    ge_idx = b.goal_events_index(d["goal_events"])
    md_idx = b.match_details_index(d["details"])
    out = []
    for m in d["matches"]:
        if not m.get("match_id") or not curated_club(m):
            continue
        ko = _kick(m)
        if not ko:
            continue
        mid = str(m["match_id"])
        st = m.get("status")
        if st == "UPCOMING":
            h = (ko - now).total_seconds() / 3600
            if PREVIEW_MIN_H <= h <= PREVIEW_MAX_H and (mid, "preview") not in done:
                out.append({"match_id": mid, "kind": "preview", "hours": round(h, 1), "m": m})
        elif st == "FINISHED" and m.get("home_score") is not None:
            h = (now - ko).total_seconds() / 3600 - 1.75      # ~end of the match
            if 0 <= h <= REPORT_MAX_H and (mid, "report") not in done:
                rich = bool(b.match_goals(ge_idx, m)) or bool(b.match_details_for(md_idx, m))
                if rich:
                    out.append({"match_id": mid, "kind": "report", "hours": round(h, 1), "m": m})
    def prio(c):
        egy = any(t in (c["m"].get("home", "") + c["m"].get("away", "")) for t in EGY_FIRST)
        return (0 if c["kind"] == "report" else 1, 0 if egy else 1, c["hours"])
    out.sort(key=prio)
    return out


# ---------------------------------------------------------------- brief pieces
def standings_row(d, comp, team):
    for s in d["standings"]:
        if s.get("competition") != comp:
            continue
        for r in s.get("table", []):
            if r.get("team") == team:
                return {k: r.get(k) for k in ("pos", "played", "won", "draw", "lost", "gf", "ga", "gd", "pts")}
    return None

def season_record(d, comp, team):
    """From fixtures rounds: last-5 form, home/away W-D-L, goals, biggest win/loss, clean sheets."""
    ms = []
    for f in d["fixtures"]:
        if f.get("competition") != comp:
            continue
        for rd in f.get("rounds", []):
            for m in rd.get("matches", []):
                if m.get("status") == "FINISHED" and m.get("home_score") is not None \
                        and team in (m.get("home"), m.get("away")):
                    ms.append(m)
    ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    rec = {"played": len(ms), "form_last5": "", "home": [0, 0, 0], "away": [0, 0, 0],
           "gf": 0, "ga": 0, "clean_sheets": 0, "failed_to_score": 0, "results": []}
    for m in ms:
        home = m["home"] == team
        gf, ga = (m["home_score"], m["away_score"]) if home else (m["away_score"], m["home_score"])
        r = "W" if gf > ga else "D" if gf == ga else "L"
        side = rec["home"] if home else rec["away"]
        side["WDL".index(r)] += 1
        rec["gf"] += gf; rec["ga"] += ga
        rec["clean_sheets"] += ga == 0
        rec["failed_to_score"] += gf == 0
        opp = b.ar_team(m["away"] if home else m["home"])
        rec["results"].append({"date": m["kickoff"], "opponent": opp, "home": home,
                               "score": f"{gf}-{ga}", "result": r, "round": m.get("round")})
    rec["form_last5"] = "".join(x["result"] for x in rec["results"][-5:])
    rec["results"] = rec["results"][-6:]
    return rec

def club_players(d, comp, team, key):
    """top scorers / assisters of `team` in `comp` (key = 'scorers'|'assists')."""
    for s in d[key]:
        if s.get("competition") != comp:
            continue
        want = _norm(b.ar_team(team))
        rows = [r for r in s.get(key, []) if _norm(r.get("team")) == want]
        return [{"name": r["name"], "value": r.get("value") or r.get("goals"),
                 "played": r.get("played")} for r in rows[:5]]
    return []

def league_leaders(d, comp, key, n=3):
    for s in d[key]:
        if s.get("competition") == comp:
            return [{"name": r["name"], "team": b.ar_team(r.get("team")), "value": r.get("value") or r.get("goals")}
                    for r in s.get(key, [])[:n]]
    return []

def recent_goals(d, team, n=3):
    """last n finished games of `team` with our goal events (scorers + minutes)."""
    out = []
    want = _norm(b.ar_team(team))
    for e in sorted(d["goal_events"], key=lambda e: e.get("date") or "", reverse=True):
        if want not in (_norm(e.get("home")), _norm(e.get("away"))):
            continue
        side = "h" if _norm(e.get("home")) == want else "a"
        goals_for = [f"{g['player']} {g['minute']}'" for g in e.get("goals", []) if g.get("side") == side]
        goals_against = [f"{g['player']} {g['minute']}'" for g in e.get("goals", []) if g.get("side") != side]
        out.append({"date": e.get("date"), "home": b.ar_team(e.get("home")), "away": b.ar_team(e.get("away")),
                    "goals_for": goals_for, "goals_against": goals_against})
        if len(out) >= n:
            break
    return out

def lineup_summary(det, side_key, top=3):
    lu = (det.get("lineups") or {}).get(side_key) or {}
    xi = lu.get("xi") or []
    if not xi:
        return None
    rated = [p for p in xi if isinstance(p.get("rt"), (int, float))]
    rated.sort(key=lambda p: -p["rt"])
    return {
        "formation": lu.get("formation"),
        "xi": [{"name": p.get("name"), "pos": p.get("pos"), "num": p.get("num"), "rating": p.get("rt")} for p in xi],
        "best": [{"name": p["name"], "pos": p.get("pos"), "rating": p["rt"]} for p in rated[:top]],
        "worst": [{"name": p["name"], "pos": p.get("pos"), "rating": p["rt"]} for p in rated[-2:]] if len(rated) > 5 else [],
        "avg_rating": round(sum(p["rt"] for p in rated) / len(rated), 2) if rated else None,
    }

def resolve_s365_game(m):
    """365scores game id for this match: our id when the match came from
    365scores, else look for the same pair on the same date in games/current."""
    comp = m.get("competition") or ""
    if comp in ("Egyptian Premier League", "CAF Champions League", "Turkish Super Lig", "Saudi Pro League"):
        return int(m["match_id"])
    try:
        want = {_norm(b.ar_team(m.get("home"))), _norm(b.ar_team(m.get("away")))}
        for path in (f"games/current/?appTypeId=5&competitions={S365_ALL}&langId=27&timezoneName=Africa/Cairo&showOdds=false",):
            for g in _s365(path).get("games") or []:
                names = {_norm(g["homeCompetitor"]["name"]), _norm(g["awayCompetitor"]["name"])}
                if names == want and (g.get("startTime") or "").startswith(m["kickoff"][:10]) or names == want:
                    return g["id"]
    except Exception:
        pass
    return None

def h2h_block(gid):
    """head-to-head + recent games from 365scores; {} on any failure."""
    try:
        j = _s365(f"games/h2h/?appTypeId=5&langId=27&gameId={gid}")
    except Exception:
        return {}
    g = j.get("game") or {}
    def game_row(x):
        sc = x.get("scores") or []
        return {"date": (x.get("startTime") or "")[:10],
                "competition": x.get("competitionDisplayName"),
                "home": (x.get("homeCompetitor") or {}).get("name"),
                "away": (x.get("awayCompetitor") or {}).get("name"),
                "score": (f"{int(sc[0])}-{int(sc[1])}" if len(sc) >= 2 and sc[0] is not None and sc[0] >= 0 else None)}
    played = lambda xs: [r for r in (game_row(x) for x in xs) if r["score"]]
    out = {"h2h": played(g.get("h2hGames") or [])[:6],
           "recent_home": played((g.get("homeCompetitor") or {}).get("recentGames") or [])[:5],
           "recent_away": played((g.get("awayCompetitor") or {}).get("recentGames") or [])[:5],
           "venue": (g.get("venue") or {}).get("name")}
    tp = g.get("topPerformers")
    if tp:
        out["top_performers_raw"] = tp
    return out

def related_articles(d, names, n=5):
    out = []
    for a in d["articles"]:
        t = a.get("title") or ""
        if any(nm and nm in t for nm in names):
            out.append({"id": a["article_id"], "title": t, "url": f"/a/{a['article_id']}", "date": a.get("pub_date")})
        if len(out) >= n:
            break
    return out


def build_brief(d, m, kind):
    comp = m.get("competition") or ""
    h_raw, a_raw = m.get("home"), m.get("away")
    h_ar, a_ar = b.ar_team(h_raw), b.ar_team(a_raw)
    ko = _kick(m)
    ge_idx = b.goal_events_index(d["goal_events"])
    md_idx = b.match_details_index(d["details"])
    clubs = curated_clubs(m)
    brief = {
        "kind": kind,
        "match": {
            "match_id": m["match_id"], "competition": b.comp_label(comp), "competition_raw": comp,
            "round": m.get("round"), "kickoff_cairo": ko.strftime("%Y-%m-%d %H:%M") if ko else None,
            "weekday_ar": b._AR_DAYS[ko.weekday()] if ko else None,
            "home": h_ar, "away": a_ar, "tv": m.get("channel"),
            "status": m.get("status"), "score": (f"{m.get('home_score')}-{m.get('away_score')}"
                                                if m.get("home_score") is not None else None),
            "url": b.match_url(m),
        },
        "curated_clubs": [{"name": tp["name"], "url": f"/team/{tp['slug']}"} for tp in clubs],
        "home": {"name": h_ar, "standings": standings_row(d, comp, h_raw), "season": season_record(d, comp, h_raw),
                 "top_scorers": club_players(d, comp, h_raw, "scorers"), "top_assists": club_players(d, comp, h_raw, "assists"),
                 "recent_goals": recent_goals(d, h_raw)},
        "away": {"name": a_ar, "standings": standings_row(d, comp, a_raw), "season": season_record(d, comp, a_raw),
                 "top_scorers": club_players(d, comp, a_raw, "scorers"), "top_assists": club_players(d, comp, a_raw, "assists"),
                 "recent_goals": recent_goals(d, a_raw)},
        "league_top_scorers": league_leaders(d, comp, "scorers"),
        "related_articles": related_articles(d, [tp["name"] for tp in clubs] + [h_ar, a_ar]),
        "generated_at_cairo": _now().strftime("%Y-%m-%d %H:%M"),
    }
    # cup / continental match: add each curated club's DOMESTIC league picture
    for tp in clubs:
        if tp["league"] != comp:
            raw = h_raw if _norm(b.ar_team(h_raw)) == _norm(tp["name"]) else a_raw
            brief.setdefault("domestic", {})[tp["name"]] = {
                "league": b.comp_label(tp["league"]),
                "standings": standings_row(d, tp["league"], raw),
                "season": season_record(d, tp["league"], raw),
                "top_scorers": club_players(d, tp["league"], raw, "scorers"),
                "top_assists": club_players(d, tp["league"], raw, "assists"),
            }
    gid = resolve_s365_game(m)
    if gid:
        brief["s365"] = h2h_block(gid)
    if kind == "report":
        goals = b.match_goals(ge_idx, m) or []
        brief["report"] = {"goals": [{"side": g["side"], "player": g["player"], "minute": g["minute"], "tag": g.get("tag", "")} for g in goals]}
        det = b.match_details_for(md_idx, m)
        e, flipped = (det[0], det[1]) if det else (None, False)
        if (not goals or not e) and gid:
            # our 15-min data may not carry this game yet: pull the 365scores
            # detail directly through fetch_data's proven parsers
            try:
                import fetch_data as fd
                game = _s365(f"game/?appTypeId=5&langId=27&gameId={gid}").get("game") or {}
                home_id = (game.get("homeCompetitor") or {}).get("id")
                if not goals:
                    rows = fd._goal_rows(game, home_id)
                    rows = rows[0] if isinstance(rows, tuple) else rows
                    brief["report"]["goals"] = [{"side": g["side"], "player": g["player"], "minute": g["minute"], "tag": g.get("tag", "")} for g in (rows or [])]
                if not e:
                    dr = fd._detail_rows(game, home_id) or {}
                    if dr.get("lineups"):
                        e, flipped = {"lineups": dr.get("lineups"), "cards": dr.get("cards"), "subs": dr.get("subs")}, False
                brief["report"]["source"] = "365scores-detail"
            except Exception as ex:
                brief["report"]["detail_error"] = str(ex)[:120]
        if e:
            hk, ak = ("a", "h") if flipped else ("h", "a")
            brief["report"]["home_lineup"] = lineup_summary(e, hk)
            brief["report"]["away_lineup"] = lineup_summary(e, ak)
            brief["report"]["cards"] = e.get("cards") or []
            brief["report"]["subs"] = e.get("subs") or []
    return brief


def to_markdown(br):
    """Compact Arabic-friendly digest for the prompt (the JSON is attached too)."""
    m = br["match"]
    L = [f"# {m['home']} × {m['away']} — {m['competition']} — {m['weekday_ar']} {m['kickoff_cairo']} (القاهرة)"]
    if m.get("score"): L.append(f"النتيجة النهائية: {m['home']} {m['score']} {m['away']}")
    if m.get("tv"): L.append(f"القناة: {m['tv']}")
    for side in ("home", "away"):
        t = br[side]; L.append(f"\n## {t['name']}")
        if t["standings"]:
            s = t["standings"]; L.append(f"الترتيب: المركز {s['pos']} — لعب {s['played']} ف{s['won']} ت{s['draw']} خ{s['lost']} — أهداف {s['gf']}:{s['ga']} — {s['pts']} نقطة")
        se = t["season"]
        if se["played"]:
            L.append(f"آخر 5: {se['form_last5']} | أرضه {se['home']} خارجها {se['away']} (ف-ت-خ) | شباك نظيفة {se['clean_sheets']} | بلا تسجيل {se['failed_to_score']}")
            for r in se["results"][-4:]:
                L.append(f"  - {r['date']} {'أرضه' if r['home'] else 'خارج'} ضد {r['opponent']}: {r['score']} ({r['result']})")
        if t["top_scorers"]: L.append("الهدافون: " + "، ".join(f"{p['name']} ({p['value']})" for p in t["top_scorers"]))
        if t["top_assists"]: L.append("صناع الأهداف: " + "، ".join(f"{p['name']} ({p['value']})" for p in t["top_assists"]))
        for rg in t["recent_goals"][:2]:
            L.append(f"  أهداف {rg['date']} {rg['home']}×{rg['away']}: له {rg['goals_for']} | عليه {rg['goals_against']}")
    for club, dm in (br.get("domestic") or {}).items():
        L.append(f"\n## {club} في {dm['league']}")
        if dm["standings"]:
            s = dm["standings"]; L.append(f"المركز {s['pos']} — لعب {s['played']} ف{s['won']} ت{s['draw']} خ{s['lost']} — أهداف {s['gf']}:{s['ga']} — {s['pts']} نقطة — آخر 5: {dm['season']['form_last5']}")
        if dm["top_scorers"]: L.append("الهدافون: " + "، ".join(f"{p['name']} ({p['value']})" for p in dm["top_scorers"]))
    s3 = br.get("s365") or {}
    if s3.get("h2h"):
        L.append("\n## المواجهات المباشرة الأخيرة")
        for x in s3["h2h"]:
            L.append(f"  - {x['date']} {x['home']} {x['score']} {x['away']} ({x['competition']})")
    rp = br.get("report")
    if rp:
        L.append("\n## تقرير المباراة")
        if rp["goals"]:
            L.append("الأهداف: " + " | ".join(f"{'أرض' if g['side']=='h' else 'ضيف'} {g['player']} {g['minute']}' {g['tag']}".strip() for g in rp["goals"]))
        else:
            L.append("الأهداف: لا تفاصيل هدافين متاحة لهذه المباراة (لا تخترعها)")
        for side in ("home_lineup", "away_lineup"):
            lu = rp.get(side)
            if lu and lu.get("xi"):
                L.append(f"{'المضيف' if side=='home_lineup' else 'الضيف'}: خطة {lu['formation'] or '؟'} — متوسط التقييم {lu['avg_rating']} — الأفضل: "
                         + "، ".join(f"{p['name']} {p['rating']}" for p in lu["best"]))
        if rp.get("cards"): L.append(f"بطاقات: {len(rp['cards'])}")
        if rp.get("subs"): L.append(f"تبديلات: {len(rp['subs'])}")
    if br["related_articles"]:
        L.append("\n## مقالات ذات صلة على الموقع")
        for a in br["related_articles"]:
            L.append(f"  - {a['title']} → {a['url']}")
    return "\n".join(L)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--brief", type=int)
    ap.add_argument("--kind", choices=("preview", "report"))
    ap.add_argument("--out")
    args = ap.parse_args()
    d = load_all()
    if args.list or args.pick:
        cs = candidates(d)
        if args.pick:
            if today_count(d["articles"]) >= DAILY_CAP:
                print(json.dumps({}))
                return 0
            c = cs[0] if cs else None
            print(json.dumps({"match_id": c["match_id"], "kind": c["kind"]} if c else {}))
            return 0
        for c in cs:
            m = c["m"]
            print(f"{c['kind']:8} {c['match_id']:>9} in/since {c['hours']:>5}h  {b.ar_team(m['home'])} × {b.ar_team(m['away'])}  ({b.comp_label(m['competition'])})")
        if not cs:
            print("no candidates")
        return 0
    if args.brief:
        m = next((x for x in d["matches"] if str(x.get("match_id")) == str(args.brief)), None)
        if not m:
            print(f"match {args.brief} not in data/matches.json"); return 1
        kind = args.kind or ("report" if m.get("status") == "FINISHED" else "preview")
        br = build_brief(d, m, kind)
        out = args.out or os.path.join(HERE, "data", "briefs", f"{args.brief}-{kind}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(br, f, ensure_ascii=False, indent=1)
        print(to_markdown(br))
        print(f"\n[brief json: {out}]")
        return 0
    ap.print_help()
    return 0

if __name__ == "__main__":
    sys.exit(main())
