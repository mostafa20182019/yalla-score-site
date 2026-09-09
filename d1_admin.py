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
  --warehouse reload the analytics facts (competitions/teams/matches/strength)
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

    if "--export" in args:
        ok = store.export_json()
        print("exported D1 -> data/*.json" if ok else "export skipped")

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
