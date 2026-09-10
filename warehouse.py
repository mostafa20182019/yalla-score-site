"""Load the analytics facts into the D1 warehouse.

The user's ask (2026-09-09): "كل الداتا التى تخص صفحة التحليلات تكون موجودة فى
الداتابيز ... عايز اروح على الداتا واعرف اتوقع عن طريق الداتا". So this is not
about storing the model's answers - `predictions` already holds those. It is
about storing the FACTS the model reasons over, linked, so the same question can
be asked in SQL and the answer compared against ours.

Run through d1_admin.py (`--warehouse`), which the d1-admin workflow calls on an
hourly cron. Deliberately NOT part of build_site:

  * the build must keep working when the store is unreachable, and adding
    ~1200 writes to it would make that promise harder to keep;
  * D1's free tier allows 100k row-writes/day. A full refresh is ~1200 rows;
    hourly is ~29k/day, comfortable. Doing it on every 15-minute publish would
    be ~115k/day - over the limit for data nobody reads during a build.

Hourly is far fresher than any analysis needs, and `predictions` (the part that
must be per-build, because a prediction is frozen before kick-off) is written by
build_site as before.
"""
import datetime
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analysis as AN     # noqa: E402
import build_site as b    # noqa: E402  - data loaders, ar_team, COMP_SLUG/ORDER
import store              # noqa: E402


def _changed_only(table, key_cols, columns, rows):
    """Drop rows already stored identically. Returns (to_write, unchanged).

    D1's free tier gives 100k row-WRITES a day but 5M row-READS, so reading the
    table back once (one query) and writing only what moved is ~50x cheaper than
    blind upserts. A full match refresh is 2113 rows; on an hour when nothing
    was played, this makes it zero. That is the difference between fitting the
    quota with headroom and living at 62k/day.
    """
    if store.backend() == "json":
        return [], 0
    sel = ", ".join(dict.fromkeys(list(key_cols) + list(columns)))
    have = {}
    for r in store.sql(f"SELECT {sel} FROM {table}"):
        have[tuple(str(r[k]) for k in key_cols)] = r
    out, same = [], 0
    for row in rows:
        cur = have.get(tuple(str(row[k]) for k in key_cols))
        if cur is not None and all(cur.get(c) == row.get(c) for c in columns):
            same += 1
            continue
        out.append(row)
    return out, same



def _standings_rows(standings, ids, known_comps, today):
    """The official table -> (rows, meta rows, unresolved club count).

    The club name in standings.json is the same source name `teams.name`
    holds - the teams table is partly built FROM these rows - so the join is
    exact rather than fuzzy. A club that still does not resolve is counted and
    skipped: a table row with no club is worse than a missing row.
    """
    rows, meta, lost = [], [], 0
    for s in standings or []:
        comp = s.get("competition")
        if comp not in known_comps:
            continue
        table = s.get("table") or []
        for r in table:
            tid = ids.get((comp, r.get("team")))
            if tid is None:
                lost += 1
                continue
            rows.append({"comp_id": comp, "team_id": tid, "pos": r.get("pos"),
                         "played": r.get("played"), "won": r.get("won"),
                         "draw": r.get("draw"), "lost": r.get("lost"),
                         "gf": r.get("gf"), "ga": r.get("ga"), "gd": r.get("gd"),
                         "pts": r.get("pts"), "as_of": today})
        meta.append({"comp_id": comp,
                     "season_label": (s.get("season_label") or "").strip() or None,
                     "zeroed": 1 if s.get("zeroed") else 0,
                     "rows": len(table), "as_of": today})
    return rows, meta, lost

def _comp_rows():
    rows = []
    for i, comp in enumerate(b.COMP_ORDER):
        rows.append({"comp_id": comp, "slug": b.COMP_SLUG.get(comp),
                     "name_ar": b.comp_label(comp), "sort_order": i})
    known = {r["comp_id"] for r in rows}
    return rows, known


def _collect_teams(all_matches, standings):
    """(comp, source_name) -> {name_ar, crest}. Crests come from whatever the
    data offers: the standings row first (cleanest), else a match badge."""
    out = {}
    for s in standings or []:
        comp = s.get("competition")
        for r in s.get("table") or []:
            if comp and r.get("team"):
                out[(comp, r["team"])] = {"name_ar": b.ar_team(r["team"]),
                                          "crest": r.get("crest")}
    for m in all_matches:
        comp = m.get("competition")
        if not comp:
            continue
        for side in ("home", "away"):
            nm = m.get(side)
            if not nm:
                continue
            rec = out.setdefault((comp, nm), {"name_ar": b.ar_team(nm), "crest": None})
            rec["crest"] = rec["crest"] or m.get(side + "_badge")
    return out


def refresh(verbose=True):
    """Rebuild competitions / teams / matches / team_strength / league_params.
    Returns a dict of row counts."""
    today = datetime.date.today().isoformat()
    matches = b.load("matches.json")
    archive = b.load("matches_archive.json")
    fixtures = b.load("fixtures.json")
    standings = b.load("standings.json")

    # every match we know of, deduped the same way the model dedupes
    pool, seen = [], set()
    for m in list(matches) + list(archive) + [
            mm for f in fixtures for rd in f.get("rounds", []) for mm in rd.get("matches", [])]:
        mid = m.get("match_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        pool.append(m)

    comp_rows, known_comps = _comp_rows()
    n_comp = store.upsert_many("competitions",
                               ["comp_id", "slug", "name_ar", "sort_order"],
                               comp_rows, ["comp_id"])

    team_map = _collect_teams([m for m in pool if m.get("competition") in known_comps],
                              standings)
    trows = [{"comp_id": c, "name": n, "name_ar": v["name_ar"], "crest": v["crest"]}
             for (c, n), v in team_map.items()]
    t_write, t_same = _changed_only("teams", ["comp_id", "name"],
                                    ["comp_id", "name", "name_ar", "crest"], trows)
    n_team = store.upsert_many("teams", ["comp_id", "name", "name_ar", "crest"],
                               t_write, ["comp_id", "name"],
                               update_cols=["name_ar", "crest"])
    # read the ids back: they are generated, and matches need them as FKs
    ids = {(r["comp_id"], r["name"]): r["team_id"]
           for r in store.sql("SELECT team_id, comp_id, name FROM teams")}

    # the official table, now that the club ids exist
    st_rows, st_meta, st_lost = _standings_rows(standings, ids, known_comps, today)
    STCOLS = ["comp_id", "team_id", "pos", "played", "won", "draw", "lost",
              "gf", "ga", "gd", "pts"]
    st_write, st_same = _changed_only("standings", ["comp_id", "team_id"],
                                      STCOLS, st_rows)
    n_st = store.upsert_many("standings", STCOLS + ["as_of"], st_write,
                             ["comp_id", "team_id"])
    n_stm = store.upsert_many(
        "standings_meta", ["comp_id", "season_label", "zeroed", "rows", "as_of"],
        st_meta, ["comp_id"])

    mrows = []
    for m in pool:
        comp = m.get("competition")
        if comp not in known_comps:
            continue
        h, a = ids.get((comp, m.get("home"))), ids.get((comp, m.get("away")))
        mrows.append({"match_id": str(m["match_id"]), "comp_id": comp,
                      "home_id": h, "away_id": a,
                      "kickoff": m.get("kickoff"), "koff_time": m.get("koff_time"),
                      "status": (m.get("status") or "").upper() or None,
                      "home_score": m.get("home_score"), "away_score": m.get("away_score"),
                      "round": m.get("round")})
    MCOLS = ["match_id", "comp_id", "home_id", "away_id", "kickoff", "koff_time",
             "status", "home_score", "away_score", "round"]
    to_write, unchanged = _changed_only("matches", ["match_id"], MCOLS, mrows)
    n_match = store.upsert_many("matches", MCOLS, to_write, ["match_id"])

    # the model's own view of each club, so its numbers can be checked
    bycomp = AN.season_matches(fixtures, archive)
    tstats = AN.team_stats(bycomp)
    srows, prows = [], []
    for comp, ms in bycomp.items():
        if comp not in known_comps:
            continue
        params = AN.league_params(ms)
        prows.append({"comp_id": comp, "as_of": today, "n": params["n"],
                      "mu_home": round(params["mu_home"], 4),
                      "mu_away": round(params["mu_away"], 4),
                      "mu": round(params["mu"], 4),
                      "home_win": params["home_win"], "draw": params["draw"],
                      "gpm": params["gpm"]})
        for name, ts in tstats.get(comp, {}).items():
            tid = ids.get((comp, name))
            if tid is None:
                continue          # a club with results but no row: skip, don't invent
            att, dfc = AN.strength(ts, params["mu"])
            srows.append({"comp_id": comp, "team_id": tid, "as_of": today,
                          "elo": round(ts["elo"], 2), "played": ts["played"],
                          "won": ts["won"], "draw": ts["draw"], "lost": ts["lost"],
                          "gf": ts["gf"], "ga": ts["ga"], "pts": ts["pts"], "cs": ts["cs"],
                          "h_played": ts["h_played"], "h_gf": ts["h_gf"],
                          "h_ga": ts["h_ga"], "h_pts": ts["h_pts"],
                          "a_played": ts["a_played"], "a_gf": ts["a_gf"],
                          "a_ga": ts["a_ga"], "a_pts": ts["a_pts"],
                          "form": "".join(ts["form"]),
                          "attack": round(att, 4), "defence": round(dfc, 4)})
    SCOLS = ["comp_id", "team_id", "elo", "played", "won", "draw", "lost",
             "gf", "ga", "pts", "cs", "h_played", "h_gf", "h_ga", "h_pts",
             "a_played", "a_gf", "a_ga", "a_pts", "form", "attack", "defence"]
    # as_of is excluded from the comparison on purpose: it changes every day and
    # would make every row look dirty, defeating the whole point
    s_write, s_same = _changed_only("team_strength", ["comp_id", "team_id"], SCOLS, srows)
    n_str = store.upsert_many("team_strength", SCOLS + ["as_of"], s_write,
                              ["comp_id", "team_id"])
    n_par = store.upsert_many(
        "league_params",
        ["comp_id", "as_of", "n", "mu_home", "mu_away", "mu", "home_win", "draw", "gpm"],
        prows, ["comp_id"])

    counts = {"competitions": n_comp, "teams_written": n_team, "teams_same": t_same,
              "standings_written": n_st, "standings_same": st_same,
              "standings_meta": n_stm, "standings_unresolved": st_lost,
              "matches_written": n_match, "matches_same": unchanged,
              "strength_written": n_str, "strength_same": s_same,
              "league_params": n_par}
    if verbose:
        print("warehouse:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        print(f"  rows written this refresh: "
              f"{n_comp + n_team + n_match + n_str + n_par + n_st + n_stm} "
              f"(D1 free tier allows 100k/day)")
        if st_lost:
            print(f"  ! {st_lost} table rows name a club with no id - skipped")
    return counts

# =========================================================== phase B: in-match
# Who started, how they were rated, who scored, who was booked, who came on.
# The source for all of it is data/match_details.json (a 45-day accumulator)
# plus data/goal_events.json (the fresher rolling window), and the two
# leaderboard files.


def _detail_pool():
    """Every detail record we hold, keyed by (home, away, date).

    goal_events is normally a subset of match_details (update_match_details
    merges it in on every fetch), but it is read second so that a stale
    accumulator can never win over the fresh window.
    """
    pool = {}
    for src in ("match_details.json", "goal_events.json"):
        for e in b.load(src):
            pool[(e.get("home"), e.get("away"), e.get("date"))] = e
    return pool


def _resolve_matches(pool):
    """key -> match_id, plus a report of how each one was resolved.

    Detail records written after 2026-09-09 carry the 365scores game id, so
    they join exactly. Older ones only have Arabic club names and a date, and
    that is genuinely ambiguous: the source sometimes keeps a stale fixture row
    for a match it has already played, so the same (home, away, date) hits two
    match_ids with different statuses. A post-match record (it has goals, or
    no `pre` flag) resolves to the FINISHED row, a pre-match one to the other.
    """
    known = {r["match_id"] for r in store.sql("SELECT match_id FROM matches")}
    rows = store.sql("""SELECT m.match_id, m.kickoff, m.status,
                               th.name_ar AS h, ta.name_ar AS a
                          FROM matches m
                          JOIN teams th ON th.team_id = m.home_id
                          JOIN teams ta ON ta.team_id = m.away_id""")
    by = {}
    for r in rows:
        by.setdefault((r["h"], r["a"], r["kickoff"]), []).append(r)

    out, rep = {}, {"by_id": 0, "by_name": 0, "by_name_offset": 0,
                    "ambiguous": 0, "unmatched": 0}
    for key, e in pool.items():
        mid = e.get("match_id")
        if mid is not None and str(mid) in known:
            out[key] = str(mid)
            rep["by_id"] += 1
            continue
        pre = bool(e.get("pre")) and not e.get("goals")
        hits, offset = by.get(key, []), False
        if not hits:
            day = e.get("date") or ""
            for delta in (-1, 1):
                try:
                    alt = (datetime.date.fromisoformat(day)
                           + datetime.timedelta(days=delta)).isoformat()
                except ValueError:
                    continue
                hits = hits or by.get((key[0], key[1], alt), [])
            offset = bool(hits)
        if not hits:
            rep["unmatched"] += 1
            continue
        if len(hits) > 1:
            want = [h for h in hits
                    if (h["status"] != "FINISHED") == pre] or hits
            if len(want) > 1:
                rep["ambiguous"] += 1
                continue
            hits = want
        out[key] = hits[0]["match_id"]
        rep["by_name_offset" if offset else "by_name"] += 1
    return out, rep


def _xi(entry, side):
    return ((entry.get("lineups") or {}).get(side) or {})


def _rating(p):
    """The source sends -1 for "not rated". Storing that as a number would
    poison every AVG(rating) - so it becomes NULL."""
    rt = p.get("rt")
    try:
        rt = float(rt)
    except (TypeError, ValueError):
        return None
    return rt if rt > 0 else None


def _athlete_id(photo):
    """Recover the athlete id from a 365scores photo URL (.../Athletes/87904).
    Same id space as a lineup's `aid`, which is what links a leaderboard row
    to a player."""
    if not isinstance(photo, str) or "/Athletes/" not in photo:
        return None
    tail = photo.rsplit("/Athletes/", 1)[1].split(".")[0].split("?")[0]
    return int(tail) if tail.isdigit() else None


def _trim(table, counts):
    """Delete rows left behind when a match's event list SHRANK.

    seq is positional, so a list that goes from 4 goals to 3 would otherwise
    keep a phantom 4th row for ever. One DELETE per affected match, and in a
    normal refresh there are none.
    """
    if not counts:
        return 0
    gone = 0
    have = {r["match_id"]: r["n"] for r in
            store.sql(f"SELECT match_id, COUNT(*) AS n FROM {table} GROUP BY match_id")}
    for mid, n in counts.items():
        if have.get(mid, 0) > n:
            store.sql(f"DELETE FROM {table} WHERE match_id = ? AND seq >= ?", [mid, n])
            gone += have[mid] - n
    return gone


def refresh_details(verbose=True):
    """Load players, lineups, goals, cards, subs and the leaderboards.

    Runs after refresh() - it needs `matches` and `teams` to already be there,
    since every row here hangs off a match_id.
    """
    today = datetime.date.today().isoformat()
    pool = _detail_pool()
    ids, rep = _resolve_matches(pool)

    players, lineups = {}, []
    goals, cards, subs = [], [], []
    gc, cc, sc = {}, {}, {}
    for key, e in pool.items():
        mid = ids.get(key)
        if not mid:
            continue
        # name -> player_id, per side, so an event can be attributed
        byname = {}
        for side in ("h", "a"):
            L = _xi(e, side)
            formation = L.get("formation")
            for p in L.get("xi") or []:
                aid = p.get("aid")
                if not aid:
                    continue
                prev = players.get(aid)
                if prev is None or (e.get("date") or "") >= prev["seen_at"]:
                    players[aid] = {"player_id": aid, "name": p.get("name"),
                                    "pos": p.get("pos"),
                                    "seen_at": e.get("date") or today}
                byname[(side, p.get("name"))] = aid
                lineups.append({"match_id": mid, "side": side, "player_id": aid,
                                "shirt": p.get("num"), "pos": p.get("pos"),
                                "line": p.get("ln"), "side_pos": p.get("sd"),
                                "rating": _rating(p), "formation": formation})
        for i, g in enumerate(e.get("goals") or []):
            goals.append({"match_id": mid, "seq": i, "side": g.get("side"),
                          "minute": g.get("minute"), "player_name": g.get("player"),
                          "player_id": byname.get((g.get("side"), g.get("player"))),
                          "tag": g.get("tag") or None})
        for i, c in enumerate(e.get("cards") or []):
            cards.append({"match_id": mid, "seq": i, "side": c.get("side"),
                          "minute": c.get("minute"), "player_name": c.get("player"),
                          "player_id": byname.get((c.get("side"), c.get("player"))),
                          "color": c.get("color")})
        for i, u in enumerate(e.get("subs") or []):
            subs.append({"match_id": mid, "seq": i, "side": u.get("side"),
                         "minute": u.get("minute"), "in_name": u.get("in"),
                         "out_name": u.get("out"),
                         "out_id": byname.get((u.get("side"), u.get("out")))})
        gc[mid] = len(e.get("goals") or [])
        cc[mid] = len(e.get("cards") or [])
        sc[mid] = len(e.get("subs") or [])

    PCOLS = ["player_id", "name", "pos", "seen_at"]
    p_write, p_same = _changed_only("players", ["player_id"], PCOLS, list(players.values()))
    n_pl = store.upsert_many("players", PCOLS, p_write, ["player_id"])

    LCOLS = ["match_id", "side", "player_id", "shirt", "pos", "line",
             "side_pos", "rating", "formation"]
    l_write, l_same = _changed_only("match_lineups", ["match_id", "side", "player_id"],
                                    LCOLS, lineups)
    n_lu = store.upsert_many("match_lineups", LCOLS, l_write,
                             ["match_id", "side", "player_id"])

    GCOLS = ["match_id", "seq", "side", "minute", "player_name", "player_id", "tag"]
    g_write, g_same = _changed_only("match_goals", ["match_id", "seq"], GCOLS, goals)
    n_go = store.upsert_many("match_goals", GCOLS, g_write, ["match_id", "seq"])

    CCOLS = ["match_id", "seq", "side", "minute", "player_name", "player_id", "color"]
    c_write, c_same = _changed_only("match_cards", ["match_id", "seq"], CCOLS, cards)
    n_ca = store.upsert_many("match_cards", CCOLS, c_write, ["match_id", "seq"])

    SCOLS = ["match_id", "seq", "side", "minute", "in_name", "out_name", "out_id"]
    s_write, s_same = _changed_only("match_subs", ["match_id", "seq"], SCOLS, subs)
    n_su = store.upsert_many("match_subs", SCOLS, s_write, ["match_id", "seq"])

    trimmed = (_trim("match_goals", gc) + _trim("match_cards", cc)
               + _trim("match_subs", sc))

    # leaderboards
    known_comps = {r["comp_id"] for r in store.sql("SELECT comp_id FROM competitions")}
    tops = []
    for src, field, kind in (("scorers.json", "scorers", "goals"),
                             ("assists.json", "assists", "assists")):
        for item in b.load(src):
            comp = item.get("competition")
            if comp not in known_comps:
                continue
            for rank, row in enumerate(item.get(field) or [], start=1):
                played = row.get("played") or None
                tops.append({"comp_id": comp, "kind": kind, "rank": rank,
                             "name": row.get("name"), "team": row.get("team"),
                             "player_id": _athlete_id(row.get("photo")),
                             "value": row.get("value"), "played": played,
                             "as_of": today})
    TCOLS = ["comp_id", "kind", "rank", "name", "team", "player_id", "value", "played"]
    t_write, t_same = _changed_only("top_players", ["comp_id", "kind", "rank"],
                                    TCOLS, tops)
    n_tp = store.upsert_many("top_players", TCOLS + ["as_of"], t_write,
                             ["comp_id", "kind", "rank"])

    counts = {"details_seen": len(pool), **rep,
              "players_written": n_pl, "players_same": p_same,
              "lineups_written": n_lu, "lineups_same": l_same,
              "goals_written": n_go, "goals_same": g_same,
              "cards_written": n_ca, "cards_same": c_same,
              "subs_written": n_su, "subs_same": s_same,
              "top_written": n_tp, "top_same": t_same,
              "trimmed": trimmed}
    if verbose:
        print("details:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        written = n_pl + n_lu + n_go + n_ca + n_su + n_tp
        print(f"  rows written this refresh: {written}")
        if rep["unmatched"] or rep["ambiguous"]:
            print(f"  ! {rep['unmatched']} detail records could not be matched to a "
                  f"fixture and {rep['ambiguous']} were ambiguous - they are skipped, "
                  f"not guessed")
    return counts

# ============================================================ phase C: articles
# A read-only mirror of data/articles.json. The build still reads the json;
# this exists so the editorial questions can be asked in SQL.


def refresh_articles(verbose=True):
    """Load articles, their sources, their FAQ, and the clubs they cover."""
    today = datetime.date.today().isoformat()
    arts = b.load("articles.json")

    # the curated clubs first - article_clubs points at them
    clubs = [{"slug": tp["slug"], "name_ar": tp["name"], "league": tp.get("league")}
             for tp in b.TEAM_PAGES]
    n_cl = store.upsert_many("clubs", ["slug", "name_ar", "league"], clubs, ["slug"])

    rows, srcs, faqs, links = [], [], [], []
    for a in arts:
        aid = str(a.get("article_id"))
        body = a.get("body") or ""
        words = b.article_words(a)
        rows.append({
            "article_id": aid, "title": a.get("title"), "summary": a.get("summary"),
            "author": a.get("author"), "kind": a.get("kind"),
            "match_id": str(a["match_id"]) if a.get("match_id") else None,
            "pub_date": a.get("pub_date"), "pub_ts": a.get("pub_ts"),
            "updated_ts": a.get("updated_ts"), "upgraded_ts": a.get("upgraded_ts"),
            "image_url": a.get("image_url"), "image_credit": a.get("image_credit"),
            "words": words, "thin": 1 if words < b.ARTICLE_MIN_WORDS else 0,
            "has_sources": 1 if a.get("sources") else 0,
            "has_faq": 1 if a.get("faq") else 0,
            "fb_post": a.get("fb_post"), "body": body,
            # the diff runs on the hash: pulling 800KB of bodies back every hour
            # to compare them would be the expensive way to learn nothing
            "body_hash": hashlib.sha1(body.encode("utf-8")).hexdigest()[:16],
        })
        for i, s in enumerate(a.get("sources") or []):
            srcs.append({"article_id": aid, "seq": i, "name": s.get("name"),
                         "url": s.get("url"), "note": s.get("note")})
        for i, q in enumerate(a.get("faq") or []):
            faqs.append({"article_id": aid, "seq": i, "q": q.get("q"), "a": q.get("a")})
        for tp in b.article_clubs(a):
            links.append({"article_id": aid, "slug": tp["slug"]})

    ACOLS = ["article_id", "title", "summary", "author", "kind", "match_id",
             "pub_date", "pub_ts", "updated_ts", "upgraded_ts", "image_url",
             "image_credit", "words", "thin", "has_sources", "has_faq",
             "fb_post", "body_hash"]
    a_write, a_same = _changed_only("articles", ["article_id"], ACOLS, rows)
    n_art = store.upsert_many("articles", ACOLS + ["body", "as_of"],
                              [dict(r, as_of=today) for r in a_write], ["article_id"])

    SCOLS = ["article_id", "seq", "name", "url", "note"]
    s_write, s_same = _changed_only("article_sources", ["article_id", "seq"], SCOLS, srcs)
    n_src = store.upsert_many("article_sources", SCOLS, s_write, ["article_id", "seq"])

    QCOLS = ["article_id", "seq", "q", "a"]
    q_write, q_same = _changed_only("article_faq", ["article_id", "seq"], QCOLS, faqs)
    n_faq = store.upsert_many("article_faq", QCOLS, q_write, ["article_id", "seq"])

    LCOLS = ["article_id", "slug"]
    l_write, l_same = _changed_only("article_clubs", LCOLS, LCOLS, links)
    n_lnk = store.upsert_many("article_clubs", LCOLS, l_write, LCOLS)

    # a source or FAQ list can shrink when an upgrade rewrites an article.
    # Every article gets an entry, zeros included - see _trim_by.
    def _by_article(items):
        out = {r["article_id"]: 0 for r in rows}
        for it in items:
            out[it["article_id"]] = out.get(it["article_id"], 0) + 1
        return out
    trimmed = (_trim_by("article_sources", "article_id", _by_article(srcs))
               + _trim_by("article_faq", "article_id", _by_article(faqs)))

    # a club link can disappear when an upgrade rewrites the text
    stale = 0
    if store.backend() != "json":
        want = {(r["article_id"], r["slug"]) for r in links}
        for r in store.sql("SELECT article_id, slug FROM article_clubs"):
            if (r["article_id"], r["slug"]) not in want:
                store.sql("DELETE FROM article_clubs WHERE article_id = ? AND slug = ?",
                          [r["article_id"], r["slug"]])
                stale += 1

    counts = {"clubs": n_cl, "articles_written": n_art, "articles_same": a_same,
              "sources_written": n_src, "sources_same": s_same,
              "faq_written": n_faq, "faq_same": q_same,
              "club_links_written": n_lnk, "club_links_same": l_same,
              "trimmed": trimmed, "stale_links_removed": stale}
    if verbose:
        print("articles:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        print(f"  rows written this refresh: "
              f"{n_cl + n_art + n_src + n_faq + n_lnk}")
        lost = store.sql("SELECT COUNT(*) n FROM articles a LEFT JOIN matches m "
                         "ON m.match_id = a.match_id "
                         "WHERE a.match_id IS NOT NULL AND m.match_id IS NULL")
        if lost and lost[0]["n"]:
            print(f"  note: {lost[0]['n']} match pieces point at a fixture that has "
                  f"aged out of `matches` - the article keeps its match_id")
    return counts


def _trim_by(table, key_col, counts):
    """Same idea as _trim but for a table keyed on something other than
    match_id: drop rows whose seq is past the current list length.

    It walks `counts`, never the stored keys. An earlier version walked the
    table and treated "absent from counts" as zero, which meant a partial map
    silently deleted every row it did not mention - so the caller must pass a
    count for EVERY key it owns, including the zeros.
    """
    if not counts:
        return 0
    gone = 0
    have = {r[key_col]: r["n"] for r in
            store.sql(f"SELECT {key_col}, COUNT(*) AS n FROM {table} GROUP BY {key_col}")}
    for k, want in counts.items():
        n = have.get(k, 0)
        if n > want:
            store.sql(f"DELETE FROM {table} WHERE {key_col} = ? AND seq >= ?", [k, want])
            gone += n - want
    return gone
