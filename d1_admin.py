"""Maintenance CLI for the D1 state store.

Runs where the credentials are: on the GitHub runner, via
.github/workflows/d1-admin.yml (workflow_dispatch). It is never run locally,
because the three secrets deliberately live only in GitHub — nothing about this
migration should put a Cloudflare token on a laptop.

Tasks
  --status    which backend is active + a row count per table
  --init      create the tables (idempotent, every statement IF NOT EXISTS)
  --migrate   init + load the existing data/*.json into D1 + report counts
  --export    dump D1 back to data/*.json (the git-tracked audit log)
  --verify    compare the D1 row counts against what the json files hold
  --articles-backfill  load data/articles.json INTO D1 (one-time / rollback)
  --warehouse reload the analytics facts: the competitions/teams/matches
              layer AND the in-match layer (lineups, ratings, goals, cards,
              subs, leaderboards)
  --sample    run the read-only analytics queries and print them (a smoke test
              for the warehouse, and a copy-paste starting point for the D1
              console)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402


def _json_counts():
    """What the json files hold, for the migration sanity check."""
    st = store._fb_json()
    return {"articles": len(st.get("articles") or {}),
            "cards": len(st.get("posted") or {}),
            "failed": len(st.get("failed") or {}),
            "seen": len(st.get("seen") or {}),
            "predictions": len(store._jload(store.PRED_JSON, {}))}


SAMPLES = [
    ("the model's inputs for the next five matches",
     """SELECT kickoff, koff_time, comp_ar, home_ar, away_ar,
               home_elo, away_elo, home_attack, away_defence, mu_home,
               ph, model_score
          FROM v_upcoming
         WHERE kickoff >= date('now')
         ORDER BY kickoff, koff_time LIMIT 5"""),
    ("do predictions join to matches? (0 unmatched means the ids line up)",
     """SELECT COUNT(*) AS predictions,
               SUM(CASE WHEN m.match_id IS NULL THEN 1 ELSE 0 END) AS unmatched
          FROM predictions p LEFT JOIN matches m ON m.match_id = p.match_id"""),
    ("Egyptian league, strongest five by Elo",
     """SELECT t.name_ar, s.elo, s.played, s.form, s.attack, s.defence
          FROM team_strength s
          JOIN teams        t ON t.team_id = s.team_id AND t.comp_id = s.comp_id
          JOIN competitions c ON c.comp_id = s.comp_id
         WHERE c.slug = 'egypt' ORDER BY s.elo DESC LIMIT 5"""),
    ("league goal means the Poisson grid uses",
     """SELECT c.name_ar, p.n, p.mu_home, p.mu_away, p.home_win, p.draw, p.gpm
          FROM league_params p JOIN competitions c ON c.comp_id = p.comp_id
         ORDER BY c.sort_order"""),
    ("the model's track record",
     "SELECT * FROM v_accuracy ORDER BY n DESC"),
    ("best rated performances on record",
     """SELECT kickoff, comp_ar, player, club_ar, opponent_ar, pos, rating
          FROM v_player_ratings
         WHERE rating IS NOT NULL ORDER BY rating DESC, kickoff DESC LIMIT 5"""),
    ("squad quality vs Elo - the feature worth testing",
     """SELECT s.club_ar, s.matches_rated, s.avg_xi_rating, ts.elo
          FROM v_squad_rating s
          JOIN teams t   ON t.name_ar = s.club_ar
          JOIN competitions c ON c.comp_id = t.comp_id AND c.name_ar = s.comp_ar
          JOIN team_strength ts ON ts.team_id = t.team_id AND ts.comp_id = t.comp_id
         WHERE c.slug = 'egypt'
         ORDER BY s.avg_xi_rating DESC LIMIT 6"""),
    ("the official table (Egypt)",
     """SELECT pos, club_ar, played, won, draw, lost, gf, ga, gd, pts
          FROM v_standings WHERE slug = 'egypt' ORDER BY pos"""),
    ("does our Elo agree with the published table? (untied rows only)",
     """SELECT comp_ar, COUNT(*) clubs, ROUND(AVG(ABS(gap)), 2) avg_places_off,
               MAX(ABS(gap)) worst
          FROM v_table_vs_model WHERE tied = 1
         GROUP BY comp_ar ORDER BY avg_places_off"""),
    ("where the model disagrees most with the table",
     """SELECT comp_ar, club_ar, official_pos, model_pos, gap, pts, elo
          FROM v_table_vs_model WHERE tied = 1
         ORDER BY ABS(gap) DESC LIMIT 6"""),
    ("are we covering the clubs we promised to cover?",
     """SELECT name_ar, articles, full_length, avg_words, last_article
          FROM v_club_coverage ORDER BY articles DESC"""),
    ("the upgrade queue (thinnest first)",
     "SELECT article_id, pub_date, words, title FROM v_thin_articles LIMIT 5"),
    # home_score IS NOT NULL = the match has actually been played, so a missing
    # report is a gap rather than a match that simply has not kicked off yet
    ("played matches we previewed but never reported on",
     """SELECT home_ar, away_ar, kickoff,
               MAX(CASE WHEN kind = 'report' THEN 1 ELSE 0 END) report
          FROM v_articles
         WHERE match_id IS NOT NULL AND home_score IS NOT NULL
         GROUP BY match_id HAVING report = 0 ORDER BY kickoff DESC LIMIT 5"""),
    ("top scorers as published",
     """SELECT comp_ar, rank, name, team, value FROM v_top_players
         WHERE kind = 'goals' ORDER BY comp_ar, rank LIMIT 6"""),
]


def _sample():
    for title, q in SAMPLES:
        print("")
        print(f"--- {title}")
        try:
            rows = store.sql(q)
        except Exception as e:                          # noqa: BLE001
            print(f"    FAILED: {e}")
            continue
        if not rows:
            print("    (no rows)")
            continue
        for r in rows:
            print("    " + "  ".join(f"{k}={r[k]}" for k in r))


def main():
    args = sys.argv[1:]
    be = store.backend()
    print(f"backend: {be}")
    WRITERS = ("--init", "--migrate", "--export", "--verify", "--warehouse", "--sample")
    if be == "json" and any(a in args for a in WRITERS):
        print("!! D1 is NOT configured (CF_API_TOKEN / CF_ACCOUNT_ID / CF_D1_ID missing).")
        print("   Nothing was written. Add the three secrets and re-run.")
        return 1

    if "--init" in args or "--migrate" in args:
        n = store.init_schema()
        print(f"schema: {n} statements applied")

    if "--migrate" in args:
        before = _json_counts()
        print("json files hold:", json.dumps(before, ensure_ascii=False))
        n = store.import_json()
        print(f"migrated: {n} new rows inserted (rows already present are skipped)")

    if "--warehouse" in args:
        import warehouse                      # imports build_site: only load it when asked
        warehouse.refresh()
        warehouse.refresh_details()           # needs matches/teams to exist first
        warehouse.refresh_articles()

    if "--articles-backfill" in args:
        import warehouse
        warehouse.refresh_articles(source="json")   # json -> D1, the one-time load

    if "--export" in args:
        ok = store.export_json()
        print("exported D1 -> data/*.json" if ok else "export skipped")
        n = store.article_export()
        print(f"exported D1 -> data/articles.json ({n} articles)")

    if "--sample" in args:
        _sample()

    after = store.counts()
    print("d1 counts:", json.dumps(after, ensure_ascii=False))
    # the warehouse tables are newer than the state tables, so a store that has
    # not had --init since they landed simply has no rows to report
    try:
        print("warehouse counts:", json.dumps(store.warehouse_counts(), ensure_ascii=False))
    except Exception as e:                     # noqa: BLE001
        print(f"warehouse counts unavailable ({e}) - run --init")

    if "--verify" in args or "--migrate" in args:
        j = _json_counts()
        bad = []
        for k in ("articles", "cards", "predictions"):
            if after.get(k, 0) < j.get(k, 0):
                bad.append(f"{k}: d1 has {after.get(k)} but json has {j.get(k)}")
        if bad:
            print("!! MISMATCH: " + "; ".join(bad))
            return 1
        print("verify: D1 holds at least everything the json files do ✓")
    return 0


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
