#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elgoon - facts packs for the articles ONLY WE can write (writer review,
2026-11-19: 37 of the last 40 pieces were news every site carried in the same
shape; the pieces built on our own numbers had fallen from half the output to
3 of 40).

Four packs, each COMPUTED from the data files - the writer chooses and
phrases, he never produces a number (the same rule as round_brief.py, and the
same guard: `allowed_numbers`, checked by `article_put.py --data-brief`):

  standing <club>   where the side stands: its row, the rows around it, the
                    gap to the top and to the side above, its next matches
                    -> «منتخب السودان في المركز الرابع بمجموعته: 3 نقاط من 4 مباريات»
  number <league>   what sets a side apart in its league: the best defence,
                    the best attack, the most wins, the only unbeaten side -
                    a fact is listed only when ONE side holds it alone
                    -> «طرابزون سبور يملك أقوى دفاع في الدوري التركي»
  h2h <pair>        the meetings we hold between two sides, game by game,
                    and their count. NOT an all-time record: only what is
                    saved (the pack says how far back it goes)
                    -> «الأهلي وبيراميدز: آخر المواجهات مباراة بمباراة»
  minutes <club>    when the side scores and concedes this season, in
                    quarter-hours, from the goal minutes of its league matches
                    -> «متى يسجل الزمالك أهدافه؟»

Usage (from this folder):
  python data_brief.py --list                       # what can be asked for, and what is already covered
  python data_brief.py standing sudan --out /tmp/brief.json
  python data_brief.py number turkey --out /tmp/brief.json
  python data_brief.py h2h al-ahly-pyramids --out /tmp/brief.json
  python data_brief.py minutes zamalek --out /tmp/brief.json
  python article_put.py --check --data-brief /tmp/brief.json /tmp/draft.json

Each pack carries `data_source` (our own page + a key in `note`): the article
must list it in `sources`, and the key is how --list knows the pack was
already written about. The key changes when the numbers do (a match more), so
the same subject can be written again after the next round - never twice on
the same numbers. A pack that cannot be computed safely is NOT written: the
tool says why and exits 1.
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analysis as AN                      # noqa: E402
import results_archive as RA               # noqa: E402
import round_brief as RB                   # noqa: E402
from site_lib.clubs import TEAM_PAGES      # noqa: E402
from site_lib.competitions import COMP_SLUG              # noqa: E402
from site_lib.config import REF_TODAY, SITE_BASE, load   # noqa: E402
from site_lib.names import _team_match, ar_team, comp_label   # noqa: E402

KINDS = ("standing", "number", "h2h", "minutes")
NEXT_N = 3
MIN_PLAYED = 5            # a table of two rounds says nothing about a side
MIN_MINUTES_MATCHES = 6
MIN_MEETINGS = 4
BANDS = ((1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90))


class NoPack(Exception):
    """The pack cannot be computed safely; the message says why."""


def _club(slug):
    tp = next((t for t in TEAM_PAGES if t["slug"] == slug), None)
    if not tp:
        raise NoPack(f"no club page «{slug}» (see --list)")
    return tp


def _comp_of(slug):
    comp = next((c for c, s in COMP_SLUG.items() if s == slug), None)
    if not comp:
        raise NoPack(f"no league «{slug}» (see --list)")
    return comp


def _tables():
    """[(competition, group name or None, rows)] - every table we hold."""
    out = []
    for st in load("standings.json") or []:
        if st.get("zeroed"):
            continue
        if st.get("table"):
            out.append((st["competition"], None, st["table"]))
        for g in st.get("groups") or []:
            if g.get("table"):
                out.append((st["competition"], g.get("name"), g["table"]))
    return out


def _row(r):
    return {"pos": int(r.get("pos") or 0), "team": ar_team(r.get("team") or ""), "played": int(r.get("played") or 0),
            "won": int(r.get("won") or 0), "draw": int(r.get("draw") or 0), "lost": int(r.get("lost") or 0),
            "gf": int(r.get("gf") or 0), "ga": int(r.get("ga") or 0), "pts": int(r.get("pts") or 0)}


def _finish(brief, key, url):
    brief["as_of"] = REF_TODAY
    brief["data_source"] = {"name": RB.DATA_SOURCE_NAME, "url": url, "note": key}
    brief["allowed_numbers"] = sorted(RB.numbers_in(json.dumps(brief, ensure_ascii=False)), key=float)
    return brief


def _upcoming(tp, comp=None, n=NEXT_N):
    rows = []
    for f in load("fixtures.json") or []:
        if comp and f.get("competition") != comp:
            continue
        for rd in f.get("rounds") or []:
            for m in rd.get("matches") or []:
                if (m.get("status") or "").upper() == "UPCOMING" and (m.get("kickoff") or "") >= REF_TODAY \
                        and _team_match(tp, m):
                    rows.append(m)
    seen, out = set(), []
    for m in sorted(rows, key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or "")):
        if m.get("match_id") in seen:
            continue
        seen.add(m.get("match_id"))
        out.append({"home": ar_team(m["home"]), "away": ar_team(m["away"]), "kickoff": m.get("kickoff"),
                    "time": m.get("koff_time"), "competition_ar": comp_label(m.get("competition")),
                    "url": f"{SITE_BASE}/m/{m['match_id']}"})
    return out[:n]


# ---------------------------------------------------------------- (أ) where the side stands
def standing(slug):
    tp = _club(slug)
    comp = tp["league"]
    hit = None
    for c, gname, rows in _tables():
        if c != comp:
            continue
        mine = [r for r in rows if _team_match(tp, {"home": r.get("team"), "away": "", "competition": c})]
        if len(mine) == 1:
            hit = (gname, sorted(rows, key=lambda r: int(r.get("pos") or 0)), mine[0])
            break
    if not hit:
        raise NoPack(f"{tp['name']} has no row in the {comp} table we hold")
    gname, rows, me = hit
    table = [_row(r) for r in rows]
    mine = _row(me)
    if mine["played"] < (3 if gname else MIN_PLAYED):
        raise NoPack(f"{tp['name']} has played {mine['played']} - too early for a standing piece")
    top = table[0]
    above = next((r for r in table if r["pos"] == mine["pos"] - 1), None)
    below = next((r for r in table if r["pos"] == mine["pos"] + 1), None)
    cslug = COMP_SLUG.get(comp, "")
    calc = os.path.exists(os.path.join(HERE, "dist", "calc", f"{cslug}.html"))
    brief = {
        "kind": "data-standing", "club": tp["name"], "club_slug": slug,
        "competition": comp, "competition_ar": comp_label(comp), "group": gname,
        "row": mine, "sides_in_table": len(table), "goal_difference": mine["gf"] - mine["ga"],
        "leader": top if top["team"] != mine["team"] else None,
        "points_behind_leader": top["pts"] - mine["pts"] if top["team"] != mine["team"] else 0,
        "above": above, "points_behind_above": (above["pts"] - mine["pts"]) if above else None,
        "below": below, "points_ahead_of_below": (mine["pts"] - below["pts"]) if below else None,
        "table": table if len(table) <= 6 else [r for r in table if abs(r["pos"] - mine["pos"]) <= 2 or r["pos"] == 1],
        "next_matches": _upcoming(tp, comp),
        "links": {"club": f"{SITE_BASE}/team/{slug}",
                  "table": f"{SITE_BASE}/{'fixtures' if gname else 'standings'}/{cslug}",
                  **({"calc": f"{SITE_BASE}/calc/{cslug}"} if calc else {})},
        "note": "الترتيب من جدول البطولة كما هو في بياناتنا اليوم. لا تكتب ما يحتاجه الفريق للتأهل أو اللقب إلا إن كان مذكورًا هنا.",
    }
    return _finish(brief, f"data:standing:{slug}:{mine['played']}", brief["links"]["table"])


# ---------------------------------------------------------------- (ب) what sets a side apart
def number(league_slug):
    comp = _comp_of(league_slug)
    rows = next((r for c, g, r in _tables() if c == comp and g is None), None)
    if not rows:
        raise NoPack(f"no league table for {comp}")
    table = [_row(r) for r in rows]
    if min(r["played"] for r in table) < MIN_PLAYED:
        raise NoPack(f"{comp}: a side has played fewer than {MIN_PLAYED} matches")

    def alone(key, best, label):
        """The fact only when ONE side holds it; the next two for contrast."""
        order = sorted(table, key=lambda r: (key(r) if best == "min" else -key(r), r["pos"]))
        if key(order[0]) == key(order[1]):
            return None
        return {"fact": label, "team": order[0]["team"], "value": key(order[0]), "played": order[0]["played"],
                "pos": order[0]["pos"],
                "next": [{"team": r["team"], "value": key(r), "played": r["played"]} for r in order[1:3]]}
    facts = [f for f in (
        alone(lambda r: r["ga"], "min", "أقوى دفاع (أقل أهداف في مرماه)"),
        alone(lambda r: r["gf"], "max", "أقوى هجوم (أكثر أهداف)"),
        alone(lambda r: r["won"], "max", "أكثر الفرق فوزًا"),
        alone(lambda r: r["draw"], "max", "أكثر الفرق تعادلًا"),
        alone(lambda r: r["ga"], "max", "أضعف دفاع (أكثر أهداف في مرماه)"),
        alone(lambda r: r["gf"], "min", "أضعف هجوم (أقل أهداف)"),
    ) if f]
    unbeaten = [r for r in table if r["lost"] == 0]
    winless = [r for r in table if r["won"] == 0]
    if len(unbeaten) == 1:
        facts.append({"fact": "الفريق الوحيد بلا هزيمة", "team": unbeaten[0]["team"], "value": 0,
                      "played": unbeaten[0]["played"], "pos": unbeaten[0]["pos"], "next": []})
    if len(winless) == 1:
        facts.append({"fact": "الفريق الوحيد بلا فوز", "team": winless[0]["team"], "value": 0,
                      "played": winless[0]["played"], "pos": winless[0]["pos"], "next": []})
    if not facts:
        raise NoPack(f"{comp}: no number held by one side alone today")
    brief = {
        "kind": "data-number", "competition": comp, "competition_ar": comp_label(comp),
        "sides": len(table), "max_played": max(r["played"] for r in table),
        "facts": facts,
        "rows": {f["team"]: next(r for r in table if r["team"] == f["team"]) for f in facts},
        "links": {"standings": f"{SITE_BASE}/standings/{league_slug}", "fixtures": f"{SITE_BASE}/fixtures/{league_slug}"},
        "note": "اختر حقيقة واحدة وابنِ عليها المقال. الأرقام من جدول الترتيب، وعدد المباريات يختلف بين الفرق: اذكره مع الرقم.",
    }
    return _finish(brief, f"data:number:{league_slug}:{brief['max_played']}", brief["links"]["standings"])


# ---------------------------------------------------------------- (ج) the meetings we hold
def h2h(pair_slug):
    from site_lib import h2h as H
    pair = next((p for p in H.PAIRS if p["slug"] == pair_slug), None)
    if not pair:
        raise NoPack(f"no pair «{pair_slug}» (see --list)")
    history = H.load_history(pair)
    notes = H.notes_for(pair, history)
    pool = {}
    for m in (load("matches.json") or []) + RA.season_rows(RA.load()):
        if m.get("match_id") and str(m["match_id"]) not in pool:
            pool[str(m["match_id"])] = dict(m, status=m.get("status") or "FINISHED")
    games = H.meetings(pair, history, pool)
    if len(games) < MIN_MEETINGS:
        raise NoPack(f"{pair_slug}: {len(games)} meeting(s) on record, {MIN_MEETINGS} needed")
    t = H.tally(games, pair, notes)
    a, b = pair["a"], pair["b"]
    brief = {
        "kind": "data-h2h", "pair": pair_slug, "a": a, "b": b,
        "meetings_on_record": len(games), "first_on_record": games[-1]["date"], "last_on_record": games[0]["date"],
        "wins": {a: t["wins"][a], b: t["wins"][b]}, "draws": t["draws"],
        "goals": {a: t["goals"][a], b: t["goals"][b]}, "awarded_results": t["awarded"],
        "games": [{"date": g["date"], "competition_ar": g["comp"], "home": g["home"], "away": g["away"],
                   "home_goals": g["hg"], "away_goals": g["ag"],
                   "note": (notes.get(g["date"]) or {}).get("note") or ""} for g in games[:10]],
        "next_matches": [m for m in _upcoming(_club(pair["a_slug"]), n=20)
                         if {m["home"], m["away"]} == {a, b}][:1] if pair.get("a_slug") else [],
        "links": {"h2h": f"{SITE_BASE}/h2h/{pair_slug}"},
        "note": ("هذه المباريات المحفوظة عندنا فقط، وليست السجل التاريخي الكامل: اكتب «في آخر N مواجهة» أو "
                 "«منذ <التاريخ>»، ولا تكتب «في تاريخ المواجهات». نتيجة بقرار إداري تُحسب نتيجةً ولا تُحسب أهدافها."),
    }
    return _finish(brief, f"data:h2h:{pair_slug}:{len(games)}", brief["links"]["h2h"])


# ---------------------------------------------------------------- (د) when the side scores
def _band(mn):
    try:
        n = int(str(mn).split("+")[0].strip())
    except (TypeError, ValueError):
        return None
    for lo, hi in BANDS:
        if lo <= n <= hi:
            return f"{lo}-{hi}"
    return f"{BANDS[-1][0]}-{BANDS[-1][1]}" if n > 90 else None


def minutes(slug):
    from site_lib.matchdata import _side_of, match_details_for, match_details_index, merge_details
    tp = _club(slug)
    comp = tp["league"]
    by_comp = AN.season_matches(load("fixtures.json"), RA.season_rows(RA.load()) + load("matches_archive.json"))
    idx = match_details_index(merge_details(load("match_details.json"), load("details_archive.json")))
    games = [m for m in by_comp.get(comp) or [] if _team_match(tp, m)]
    bands_f = {f"{lo}-{hi}": 0 for lo, hi in BANDS}
    bands_a = dict(bands_f)
    used = gf = ga = 0
    for m in games:
        m = dict(m, status="FINISHED")
        got = match_details_for(idx, m)
        hs, as_ = int(m.get("home_score") or 0), int(m.get("away_score") or 0)
        if not got:
            continue
        e, flipped = got
        goals = e.get("goals") or []
        if len(goals) != hs + as_:
            continue                       # a goal missing: the match would understate a quarter-hour
        mine = "h" if _team_match(tp, {"home": m.get("home"), "away": "", "competition": comp}) else "a"
        sd = _side_of(flipped)
        bands = [(sd(g.get("side")), _band(g.get("minute"))) for g in goals]
        if any(b is None for _, b in bands):
            continue
        used += 1
        for side, b in bands:
            if side == mine:
                bands_f[b] += 1; gf += 1
            else:
                bands_a[b] += 1; ga += 1
    if used < MIN_MINUTES_MATCHES or used < 0.8 * len(games):
        raise NoPack(f"{tp['name']}: goal minutes for {used} of {len(games)} league matches - not enough")

    def peak(b):
        top = max(b.values())
        ks = [k for k, v in b.items() if v == top]
        return ks[0] if top and len(ks) == 1 else None
    brief = {
        "kind": "data-minutes", "club": tp["name"], "club_slug": slug,
        "competition": comp, "competition_ar": comp_label(comp),
        "matches_counted": used, "matches_played": len(games),
        "goals_for": gf, "goals_against": ga,
        "scored_by_quarter_hour": bands_f, "conceded_by_quarter_hour": bands_a,
        "scored_first_half": sum(bands_f[f"{lo}-{hi}"] for lo, hi in BANDS[:3]),
        "scored_second_half": sum(bands_f[f"{lo}-{hi}"] for lo, hi in BANDS[3:]),
        "conceded_first_half": sum(bands_a[f"{lo}-{hi}"] for lo, hi in BANDS[:3]),
        "conceded_second_half": sum(bands_a[f"{lo}-{hi}"] for lo, hi in BANDS[3:]),
        "most_scoring_quarter_hour": peak(bands_f), "most_conceding_quarter_hour": peak(bands_a),
        "links": {"club": f"{SITE_BASE}/team/{slug}", "numbers": f"{SITE_BASE}/numbers/{COMP_SLUG.get(comp, '')}"},
        "note": ("الوقت بدل الضائع يُحسب مع ربع الساعة الذي قبله (45+2 في 31-45، و90+3 في 76-90). "
                 "الهدف العكسي يُحسب للفريق الذي استفاد منه. اذكر عدد المباريات المحسوبة."),
    }
    return _finish(brief, f"data:minutes:{slug}:{used}", brief["links"]["club"])


BUILD = {"standing": standing, "number": number, "h2h": h2h, "minutes": minutes}


def covered_keys(articles):
    return {s["note"] for a in articles or [] for s in a.get("sources") or []
            if isinstance(s, dict) and (s.get("note") or "").startswith("data:")}


def catalogue():
    """[(kind, subject, key or None, why not)] - everything that can be asked for today."""
    from site_lib import h2h as H
    out = []
    for kind, subjects in (("standing", [t["slug"] for t in TEAM_PAGES]),
                           ("number", sorted({COMP_SLUG[c] for c, g, _ in _tables() if g is None and c in COMP_SLUG})),
                           ("h2h", [p["slug"] for p in H.PAIRS]),
                           ("minutes", [t["slug"] for t in TEAM_PAGES])):
        for s in subjects:
            try:
                out.append((kind, s, BUILD[kind](s)["data_source"]["note"], ""))
            except NoPack as e:
                out.append((kind, s, None, str(e)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", nargs="?", choices=KINDS)
    ap.add_argument("subject", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.list:
        done = covered_keys(load("articles.json"))
        for kind, s, key, why in catalogue():
            state = ("covered" if key in done else "open") if key else f"no pack: {why}"
            print(f"{kind:9} {s:22} {state}")
        return 0
    if not args.kind or not args.subject:
        ap.error("a kind and a subject, or --list")
    try:
        brief = BUILD[args.kind](args.subject)
    except NoPack as e:
        print(f"no pack: {e}")
        return 1
    text = json.dumps(brief, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}: {brief['kind']} / {brief['data_source']['note']}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
