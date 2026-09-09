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


def main():
    args = sys.argv[1:]
    be = store.backend()
    print(f"backend: {be}")
    WRITERS = ("--init", "--migrate", "--export", "--verify", "--warehouse")
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
