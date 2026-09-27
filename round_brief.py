#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yalla Score - the facts pack for a «الجولة بالأرقام» article (2026-09-27).

WHY: Search Console (2026-09-27) showed Google crawling our rewritten news and
declining to index it - 17 of 18 «Crawled - currently not indexed» were
articles, all 500-630 words WITH sources. What it DID index is what only we
have: standings readings, predictions, analysis. So this article type is built
from our own data - the round's results, the table, the Elo movement and how
OUR model's frozen predictions did - numbers no other site publishes together.

THE RULE (same as the match readings): numbers are COMPUTED, never generated.
This tool computes every number; the writer only chooses and phrases.
`allowed_numbers` lists them all, and article_put.py --data-brief refuses an
article that contains a number the pack does not.

Usage (from this folder):
  python round_brief.py --list                       # completed rounds + whether covered
  python round_brief.py --pick                       # ONE uncovered round as JSON {"comp":..,"round":..} or {}
  python round_brief.py --brief "Egyptian Premier League" 5 [--out /tmp/brief.json]
  python round_brief.py --check /tmp/draft.json /tmp/brief.json   # the numbers guard, standalone

A round is "completed" when every match in it is FINISHED (a postponed match
keeps the round open - its table would be half a round), and "recent" when its
last match ended within RECENT_DAYS. Covered = an article whose sources carry
this round's key (see round_key) - the dedup survives a retitled article.
"""
import argparse, datetime, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analysis as AN                      # noqa: E402
import results_archive as RA               # noqa: E402
from site_lib.config import load, SITE_BASE, REF_TODAY   # noqa: E402
from site_lib.names import ar_team, comp_label           # noqa: E402
from site_lib.competitions import COMP_SLUG              # noqa: E402

RECENT_DAYS = 4          # a round review older than this is history, not news
# the leagues this runs for, in the order --pick prefers them (Egyptian first)
LEAGUES = ["Egyptian Premier League", "Premier League", "Primera Division", "Serie A",
           "Bundesliga", "Ligue 1", "Saudi Pro League", "Turkish Super Lig"]
DATA_SOURCE_NAME = "بيانات يلا سكور"


def round_key(comp, rnd):
    """The dedup key, carried in the article's data source `note`."""
    return f"round:{COMP_SLUG.get(comp, comp)}:{rnd}"


def _pool():
    fixtures = load("fixtures.json")
    archive = load("matches_archive.json")
    by_comp = AN.season_matches(fixtures, RA.season_rows(RA.load()) + archive)
    return fixtures, by_comp


def completed_rounds(fixtures, today=None):
    """[(comp, round, first_day, last_day, matches)] for rounds whose every match is FINISHED."""
    out = []
    for f in fixtures:
        comp = f.get("competition")
        if comp not in LEAGUES:
            continue
        for rd in f.get("rounds", []):
            ms = rd.get("matches") or []
            if not ms or any(m.get("status") != "FINISHED" or m.get("home_score") is None for m in ms):
                continue
            days = sorted(m.get("kickoff") or "" for m in ms)
            out.append((comp, rd.get("round"), days[0], days[-1], ms))
    return out


def covered_keys(articles):
    keys = set()
    for a in articles:
        for s in a.get("sources") or []:
            if isinstance(s, dict) and (s.get("note") or "").startswith("round:"):
                keys.add(s["note"])
    return keys


def _pred_log():
    try:
        import store
        if store.backend() != "json":
            return store.pred_all()
    except Exception:                                   # noqa: BLE001
        pass
    return AN.load_log()


def _pct(x):
    return round(x * 100)


def build_brief(comp, rnd):
    fixtures, by_comp = _pool()
    rounds = {(c, r): (d0, d1, ms) for c, r, d0, d1, ms in completed_rounds(fixtures)}
    if (comp, rnd) not in rounds:
        raise SystemExit(f"{comp} round {rnd} is not a completed round in fixtures.json")
    d0, d1, ms = rounds[(comp, rnd)]
    ids = {str(m["match_id"]) for m in ms}
    season = by_comp.get(comp, [])
    seeds = AN.load_elo_seeds()

    # ---- results
    results = []
    for m in sorted(ms, key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or "")):
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        results.append({"match_id": str(m["match_id"]), "home": ar_team(m["home"]), "away": ar_team(m["away"]),
                        "home_score": hs, "away_score": as_, "kickoff": m.get("kickoff"),
                        "url": f"{SITE_BASE}/m/{m['match_id']}"})
    goals = sum(r["home_score"] + r["away_score"] for r in results)
    totals = {"matches": len(results), "goals": goals,
              "goals_per_match": round(goals / len(results), 1) if results else 0,
              "home_wins": sum(1 for r in results if r["home_score"] > r["away_score"]),
              "draws": sum(1 for r in results if r["home_score"] == r["away_score"]),
              "away_wins": sum(1 for r in results if r["home_score"] < r["away_score"])}
    big = max(results, key=lambda r: (abs(r["home_score"] - r["away_score"]), r["home_score"] + r["away_score"]))
    totals["biggest_margin"] = {k: big[k] for k in ("home", "away", "home_score", "away_score")}

    # ---- Elo before / after the round (the site's own model, same seeds)
    last_ts = max((m.get("kickoff") or "") for m in ms)
    upto = [m for m in season if (m.get("kickoff") or "") <= last_ts]
    before = [m for m in upto if str(m.get("match_id")) not in ids]
    e0 = AN.team_stats({comp: before}, seeds).get(comp, {})
    e1 = AN.team_stats({comp: upto}, seeds).get(comp, {})
    moves = []
    for team, r1 in e1.items():
        if team in e0 and any(team in (m["home"], m["away"]) for m in ms):
            moves.append({"team": ar_team(team), "before": round(e0[team]["elo"]), "after": round(r1["elo"]),
                          "delta": round(r1["elo"]) - round(e0[team]["elo"])})
    moves.sort(key=lambda x: -x["delta"])
    elo_rank = sorted(e1.values(), key=lambda r: -r["elo"])
    elo = {"risers": [x for x in moves[:3] if x["delta"] > 0],
           "fallers": [x for x in moves[::-1][:3] if x["delta"] < 0],
           "top5": [{"rank": i + 1, "team": ar_team(r["team"]), "elo": round(r["elo"])}
                    for i, r in enumerate(elo_rank[:5])]}

    # ---- the official table - only when it is the table AFTER this round
    table = None
    st = next((s for s in load("standings.json") if s.get("competition") == comp and s.get("table")), None)
    if st and not st.get("zeroed"):
        played = {}
        for m in upto:
            for side in (m["home"], m["away"]):
                played[ar_team(side)] = played.get(ar_team(side), 0) + 1
        rows = st["table"]
        consistent = all(played.get(ar_team(r["team"])) == r.get("played") for r in rows)
        if consistent:
            in_round = {x for r in results for x in (r["home"], r["away"])}
            def row(r):
                return {"pos": r["pos"], "team": ar_team(r["team"]), "played": r["played"], "won": r["won"],
                        "draw": r["draw"], "lost": r["lost"], "gf": r["gf"], "ga": r["ga"], "gd": r["gd"],
                        "pts": r["pts"]}
            top = [row(r) for r in rows[:5]]
            table = {"after_round": rnd, "season": st.get("season_label"), "top": top, "bottom": [row(r) for r in rows[-3:]],
                     "teams": len(rows),
                     "leader": top[0]["team"], "leader_pts": top[0]["pts"],
                     "gap_1_2": top[0]["pts"] - top[1]["pts"] if len(top) > 1 else None,
                     "unbeaten": [ar_team(r["team"]) for r in rows if r["lost"] == 0 and r["played"] > 0],
                     "winless": [ar_team(r["team"]) for r in rows if r["won"] == 0 and r["played"] > 0],
                     "all_played_this_round": all(ar_team(r["team"]) in in_round for r in rows)}

    # ---- how OUR frozen predictions did (the log never changes after kickoff)
    log = _pred_log()
    preds = []
    for r in results:
        e = log.get(r["match_id"])
        if not e or e.get("hit") is None:
            continue
        preds.append({"match_id": r["match_id"], "home": r["home"], "away": r["away"],
                      "p_home": _pct(e["ph"]), "p_draw": _pct(e["pd"]), "p_away": _pct(e["pa"]),
                      "pick": {"H": "home", "D": "draw", "A": "away"}.get(e.get("pick")),
                      "likeliest_score": e.get("score"), "hit": bool(e.get("hit")),
                      "exact_score": bool(e.get("score_hit")),
                      "actual": f'{r["home_score"]}-{r["away_score"]}'})
    pred = None
    if preds:
        def p_of_outcome(p):
            hs, as_ = map(int, p["actual"].split("-"))
            return p["p_home"] if hs > as_ else p["p_draw"] if hs == as_ else p["p_away"]
        hits = [p for p in preds if p["hit"]]
        pred = {"n": len(preds), "hits": len(hits), "exact": sum(p["exact_score"] for p in preds),
                "matches": preds,
                "best_call": max(hits, key=lambda p: max(p["p_home"], p["p_draw"], p["p_away"])) if hits else None,
                "biggest_surprise": min(preds, key=p_of_outcome) | {"p_of_what_happened": p_of_outcome(min(preds, key=p_of_outcome))},
                "record_url": f"{SITE_BASE}/predictions"}

    # ---- the next round: fixtures only (its predictions freeze near kickoff)
    nxt = None
    for f in fixtures:
        if f.get("competition") != comp:
            continue
        cand = [rd for rd in f.get("rounds", []) if (rd.get("round") or 0) > rnd
                and any(m.get("status") == "UPCOMING" for m in rd.get("matches") or [])]
        if cand:
            rd = min(cand, key=lambda rd: rd["round"])
            mm = sorted(rd["matches"], key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
            nxt = {"round": rd["round"], "first_day": mm[0].get("kickoff"), "last_day": mm[-1].get("kickoff"),
                   "matches": [{"home": ar_team(m["home"]), "away": ar_team(m["away"]), "kickoff": m.get("kickoff"),
                                "time": m.get("koff_time"), "url": f"{SITE_BASE}/m/{m['match_id']}"} for m in mm]}

    # ---- scorers (the league's current chart)
    sc = next((s for s in load("scorers.json") if s.get("competition") == comp), None)
    scorers = [{"name": s.get("name"), "team": ar_team(s.get("team") or ""), "goals": s.get("goals")}
               for s in (sc or {}).get("scorers", [])[:5] if s.get("name") and s.get("goals")]

    slug = COMP_SLUG.get(comp, "")
    brief = {
        "kind": "round-review", "competition": comp, "competition_ar": comp_label(comp), "round": rnd,
        "first_day": d0, "last_day": d1, "as_of": REF_TODAY, "round_key": round_key(comp, rnd),
        "results": results, "totals": totals, "table": table, "elo": elo, "predictions": pred,
        "next_round": nxt, "scorers": scorers,
        "links": {"standings": f"{SITE_BASE}/standings/{slug}", "fixtures": f"{SITE_BASE}/fixtures/{slug}",
                  "analysis": f"{SITE_BASE}/analysis/{slug}", "predictions": f"{SITE_BASE}/predictions"},
        "data_source": {"name": DATA_SOURCE_NAME, "url": f"{SITE_BASE}/fixtures/{slug}",
                        "note": round_key(comp, rnd)},
    }
    brief["allowed_numbers"] = sorted(numbers_in(json.dumps(brief, ensure_ascii=False)), key=float)
    return brief


# ---------------------------------------------------------------- the guard
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text):
    """Every number in a text, normalised (Arabic-Indic digits, '1.50' == '1.5')."""
    out = set()
    for n in _NUM.findall((text or "").translate(_AR_DIGITS)):
        out.add(str(float(n)).rstrip("0").rstrip(".") if "." in n else str(int(n)))
    return out


_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "إبريل": 4, "مايو": 5,
           "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
           "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}
_DATE = re.compile(r"(\d{1,2})\s+(" + "|".join(_MONTHS) + r")(?:\s+(\d{4}))?")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def pack_dates(brief):
    """{(day, month)} and {year} of every date the facts pack carries."""
    days, years = set(), set()
    for y, m, d in _ISO.findall(json.dumps(brief, ensure_ascii=False)):
        days.add((int(d), int(m)))
        years.add(str(int(y)))
    return days, years


def unknown_numbers(draft, brief):
    """Numbers in the article's text that the facts pack does not contain.

    Checked: title, summary, body (tags stripped - an href's /m/<id> is a link,
    not a claim) and the FAQ. A DATE is its own claim: «11 أكتوبر» passes only
    when that day is one of the pack's dates (a result, the next round, the
    as-of day) - otherwise it is reported whole. The years of the pack's dates
    pass on their own."""
    allowed = set(brief.get("allowed_numbers") or [])
    days, years = pack_dates(brief)
    allowed |= years
    text = " ".join([draft.get("title") or "", draft.get("summary") or "",
                     re.sub(r"<[^>]+>", " ", draft.get("body") or "")]
                    + [f"{q.get('q', '')} {q.get('a', '')}" for q in draft.get("faq") or [] if isinstance(q, dict)])
    text = text.translate(_AR_DIGITS)
    bad = []
    def date(m):
        if (int(m.group(1)), _MONTHS[m.group(2)]) not in days:
            bad.append(f"{m.group(1)} {m.group(2)}")
        return " "
    text = _DATE.sub(date, text)
    return bad + sorted(numbers_in(text) - allowed, key=float)


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--brief", nargs=2, metavar=("COMP", "ROUND"))
    ap.add_argument("--check", nargs=2, metavar=("DRAFT", "BRIEF"))
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.check:
        draft = json.load(open(args.check[0], encoding="utf-8"))
        brief = json.load(open(args.check[1], encoding="utf-8"))
        bad = unknown_numbers(draft, brief)
        print(json.dumps({"ok": not bad, "unknown_numbers": bad}, ensure_ascii=False))
        return 1 if bad else 0

    if args.list or args.pick:
        fixtures = load("fixtures.json")
        done = covered_keys(load("articles.json"))
        cut = (datetime.date.fromisoformat(REF_TODAY) - datetime.timedelta(days=RECENT_DAYS)).isoformat()
        rows = sorted(completed_rounds(fixtures), key=lambda t: (LEAGUES.index(t[0]), -(t[1] or 0)))
        if args.list:
            for comp, rnd, d0, d1, _ in rows:
                k = round_key(comp, rnd)
                print(f"{comp:26s} round {rnd:>2}  {d0}..{d1}  "
                      f"{'COVERED' if k in done else ('recent' if d1 >= cut else 'old')}")
            return 0
        pick = next(({"comp": c, "round": r} for c, r, d0, d1, _ in rows
                     if d1 >= cut and round_key(c, r) not in done), {})
        print(json.dumps(pick, ensure_ascii=False))
        return 0

    if args.brief:
        brief = build_brief(args.brief[0], int(args.brief[1]))
        text = json.dumps(brief, ensure_ascii=False, indent=1)
        if args.out:
            open(args.out, "w", encoding="utf-8").write(text)
            print(f"wrote {args.out}: {len(brief['results'])} results, "
                  f"table={'yes' if brief['table'] else 'NO'}, "
                  f"predictions={brief['predictions']['n'] if brief['predictions'] else 0}, "
                  f"{len(brief['allowed_numbers'])} allowed numbers")
        else:
            print(text)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
