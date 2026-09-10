"""State store for Yalla Score — Cloudflare D1, with a JSON fallback.

The one small module the whole D1 decision rests on: every caller talks to the
functions here, so swapping the backend later is a change in ONE file.

Three backends, picked automatically:

  D1     when CF_API_TOKEN + CF_ACCOUNT_ID + CF_D1_ID are all in the env.
         Real backend. HTTP, stdlib only - no new dependency on the runner.
  sqlite when D1_SQLITE points at a file (tests, local development).
         Same SQL dialect as D1, so the logic is genuinely exercised.
  json   when neither is configured: reads/writes data/fb_posted.json and
         data/predictions.json exactly as before.

The json fallback is not a nicety, it is the rollout plan: this module can be
merged and deployed while the secrets do not exist yet and the pipeline behaves
exactly as it does today. Adding the three secrets is what flips it on, and
removing them rolls it back.

WHY ANY OF THIS EXISTS — the duplicate-post bug (2026-09-07): article 422 was
posted twice because two overlapping publish runs each read the dedup state
from their own ~5-minute-old git checkout, and neither had recorded its post
yet. `claim()` below replaces every workaround we built for that: it INSERTs
first, and a concurrent loser fails on the primary key instead of posting.
"""
import datetime
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FB_JSON = os.path.join(HERE, "data", "fb_posted.json")
PRED_JSON = os.path.join(HERE, "data", "predictions.json")
SCHEMA = os.path.join(HERE, "d1_schema.sql")

# A claim with no post_id older than this is considered abandoned (the run died
# between claiming and posting) and may be taken over. Long enough to cover a
# slow post + Facebook's preview retries, short enough that one crash does not
# silence an article for a whole day.
CLAIM_TTL_SEC = 15 * 60

API = "https://api.cloudflare.com/client/v4/accounts/{acct}/d1/database/{db}/query"
_sqlite_conn = None


# ---------------------------------------------------------------- backend
def backend():
    """'d1' | 'sqlite' | 'json' — which store the process is actually using."""
    if all(os.environ.get(k) for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID")):
        return "d1"
    if os.environ.get("D1_SQLITE"):
        return "sqlite"
    return "json"


# D1 rejects a statement with more than 100 bound parameters ("too many SQL
# variables"), well below SQLite's own default of 999. Batch sizes derive from
# this, see upsert_many.
MAX_BIND_VARS = 100


class Conflict(Exception):
    """A UNIQUE / PRIMARY KEY violation: someone else already holds this row."""


def _sqlite():
    global _sqlite_conn
    if _sqlite_conn is None:
        _sqlite_conn = sqlite3.connect(os.environ["D1_SQLITE"])
        _sqlite_conn.row_factory = sqlite3.Row
        _sqlite_conn.execute("PRAGMA journal_mode=WAL")
    return _sqlite_conn


def sql(statement, params=None):
    """Run one statement. Returns a list of dict rows ([] for writes).
    Raises Conflict on a primary-key clash, RuntimeError on anything else."""
    params = list(params or [])
    if backend() == "sqlite":
        try:
            cur = _sqlite().execute(statement, params)
            # fetch BEFORE commit: a statement with RETURNING still has rows
            # pending, and committing first raises "SQL statements in progress"
            rows = [dict(r) for r in cur.fetchall()]
            _sqlite_conn.commit()
            return rows
        except sqlite3.IntegrityError as e:
            raise Conflict(str(e)) from e
    body = json.dumps({"sql": statement, "params": params}).encode()
    url = API.format(acct=os.environ["CF_ACCOUNT_ID"], db=os.environ["CF_D1_ID"])
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + os.environ["CF_API_TOKEN"],
        "Content-Type": "application/json",
        "User-Agent": "yalla-score-store/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if "UNIQUE constraint failed" in detail or "PRIMARY KEY" in detail:
            raise Conflict(detail) from e
        raise RuntimeError(f"D1 HTTP {e.code}: {detail}") from e
    if not out.get("success"):
        errs = json.dumps(out.get("errors"), ensure_ascii=False)[:400]
        if "UNIQUE constraint failed" in errs or "PRIMARY KEY" in errs:
            raise Conflict(errs)
        raise RuntimeError(f"D1 error: {errs}")
    res = (out.get("result") or [{}])[0]
    return res.get("results") or []


def upsert_many(table, columns, rows, key_cols, update_cols=None, chunk=None):
    """Batched INSERT ... ON CONFLICT DO UPDATE. Returns the number of rows sent.

    One HTTP call per chunk, not per row: the first analytics refresh writes
    ~2600 rows and doing that one statement at a time would be ~2600 round
    trips.

    The chunk size is derived, not fixed: **D1 allows at most 100 bound
    parameters per statement** (much lower than SQLite's own 999 default, which
    is why a fixed chunk=60 passed locally and then failed on D1 with
    "too many SQL variables"). So a 4-column table batches 25 rows at a time
    and a 23-column one batches 4.

    Returns 0 on the json backend: the warehouse is a QUERY surface, nothing in
    the site reads it, so there is no json equivalent to keep in step.
    """
    rows = list(rows)
    if not rows:
        return 0
    if backend() == "json":
        return 0
    chunk = chunk or max(1, MAX_BIND_VARS // max(1, len(columns)))
    update_cols = [c for c in (update_cols or columns) if c not in key_cols]
    cols = ", ".join(columns)
    one = "(" + ", ".join("?" for _ in columns) + ")"
    setter = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    tail = (f" ON CONFLICT({', '.join(key_cols)}) DO UPDATE SET {setter}"
            if setter else f" ON CONFLICT({', '.join(key_cols)}) DO NOTHING")
    sent = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i:i + chunk]
        params = [v for r in batch for v in (r[c] for c in columns)]
        sql(f"INSERT INTO {table} ({cols}) VALUES " + ", ".join(one for _ in batch) + tail,
            params)
        sent += len(batch)
    return sent


def init_schema():
    """Create the tables. Safe to re-run (every statement is IF NOT EXISTS)."""
    with open(SCHEMA, encoding="utf-8") as f:
        script = f.read()
    n = 0
    for chunk in _statements(script):
        sql(chunk)
        n += 1
    return n


def _statements(script):
    """Split a .sql script into statements, comments removed FIRST.

    Order matters, and both orders have now been wrong once:
      * testing chunk.startswith("--") AFTER splitting skipped every statement
        that had a comment block above it (CREATE TABLE predictions vanished
        until test_store.py caught it);
      * splitting on ";" BEFORE removing comments tears apart any comment that
        CONTAINS a semicolon, and the leftover prose then looks like SQL
        ("near 'the': syntax error", hit while adding the phase-B tables).
    So cut each line at its first `--` outside a quoted string, then split.
    """
    out = []
    for line in script.splitlines():
        quote = None
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'" + '"':
                quote = ch
            elif ch == "-" and line[i + 1:i + 2] == "-":
                line = line[:i]
                break
        out.append(line)
    return [c.strip() for c in chr(10).join(out).split(";") if c.strip()]


# ---------------------------------------------------------------- json fallback
def _jload(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else default
    except Exception:
        return default


def _jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def _fb_json():
    st = _jload(FB_JSON, {})
    for k in ("posted", "failed", "articles", "seen"):
        st.setdefault(k, {})
    return st


def _bucket(kind):
    """Which json key holds this kind (the file predates the kind column)."""
    return "articles" if kind == "article" else "posted"


# ---------------------------------------------------------------- facebook state
def claim(kind, ref_id, title=None, score=None):
    """Try to take ownership of posting (kind, ref_id).

    True  -> this process owns it and MUST post (or call release on failure).
    False -> already posted, or another live run holds the claim. Do not post.

    This is the whole duplicate fix: the INSERT is the lock.
    """
    ref_id, now = str(ref_id), int(time.time())
    if backend() == "json":
        # The json backend cannot be atomic - that is the whole reason we are
        # leaving it - so it deliberately does NOT write a claim. It reproduces
        # today's behaviour exactly: check, then let the caller post, then
        # record. Writing a placeholder here instead would add a failure mode
        # the current code does not have (a crashed run leaving a phantom claim
        # that silences the article forever, with no TTL to clear it).
        return ref_id not in _fb_json()[_bucket(kind)]
    try:
        sql("INSERT INTO fb_posted (kind, ref_id, title, score, claimed_at) "
            "VALUES (?, ?, ?, ?, ?)", [kind, ref_id, title, score, now])
        return True
    except Conflict:
        pass
    # A row exists. Take it over ONLY if it is an abandoned claim: no post_id
    # and older than the TTL. The WHERE clause is what keeps this atomic - two
    # runs racing to reclaim, only one UPDATE reports a change.
    rows = sql("UPDATE fb_posted SET claimed_at = ?, title = COALESCE(?, title) "
               "WHERE kind = ? AND ref_id = ? AND post_id IS NULL AND claimed_at < ? "
               "RETURNING ref_id", [now, title, kind, ref_id, now - CLAIM_TTL_SEC])
    return bool(rows)


def record_post(kind, ref_id, post_id, title=None, score=None, og_ok=False):
    """Mark a claim as actually published."""
    ref_id, now = str(ref_id), int(time.time())
    if backend() == "json":
        st = _fb_json()
        rec = {"ts": time.time(), "post_id": post_id}
        if title:
            rec["title"] = title
        if score:
            rec["s"] = score
        if og_ok:
            rec["og_ok"] = True
        st[_bucket(kind)][ref_id] = rec
        _jsave(FB_JSON, st)
        return
    # UPSERT, not a bare UPDATE: auto() always claims first, but the legacy
    # positional mode and any manual/repair call do not, and an UPDATE that
    # matches no row would record the post NOWHERE - silently, which is the
    # worst possible outcome for a dedup record. Caught by test_fb_post case 7.
    sql("INSERT INTO fb_posted (kind, ref_id, post_id, title, score, og_ok, "
        "                       claimed_at, posted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(kind, ref_id) DO UPDATE SET "
        "  post_id   = excluded.post_id, "
        "  posted_at = excluded.posted_at, "
        "  og_ok     = excluded.og_ok, "
        "  title     = COALESCE(excluded.title, fb_posted.title), "
        "  score     = COALESCE(excluded.score, fb_posted.score)",
        [kind, ref_id, post_id, title, score, 1 if og_ok else 0, now, now])


def release(kind, ref_id):
    """Give up a claim that never became a post, so a later run can retry."""
    ref_id = str(ref_id)
    if backend() == "json":
        return          # nothing was claimed in json mode, so nothing to release
    sql("DELETE FROM fb_posted WHERE kind = ? AND ref_id = ? AND post_id IS NULL",
        [kind, ref_id])


def posted_ids(kind):
    """Everything already published for this kind (open claims excluded)."""
    if backend() == "json":
        st = _fb_json()
        return {k for k, v in st[_bucket(kind)].items() if (v or {}).get("post_id")}
    rows = sql("SELECT ref_id FROM fb_posted WHERE kind = ? AND post_id IS NOT NULL",
               [kind])
    return {r["ref_id"] for r in rows}


def get_post(kind, ref_id):
    """The stored record, or None."""
    ref_id = str(ref_id)
    if backend() == "json":
        return _fb_json()[_bucket(kind)].get(ref_id)
    rows = sql("SELECT * FROM fb_posted WHERE kind = ? AND ref_id = ?", [kind, ref_id])
    return rows[0] if rows else None


def set_og_ok(kind, ref_id):
    ref_id = str(ref_id)
    if backend() == "json":
        st = _fb_json()
        rec = st[_bucket(kind)].get(ref_id)
        if rec:
            rec["og_ok"] = True
            _jsave(FB_JSON, st)
        return
    sql("UPDATE fb_posted SET og_ok = 1 WHERE kind = ? AND ref_id = ?", [kind, ref_id])


def unconfirmed(kind, within_hours):
    """Recent posts whose Facebook preview was never confirmed — the heal pass."""
    cut = int(time.time()) - int(within_hours * 3600)
    if backend() == "json":
        st = _fb_json()
        return [{"ref_id": k, "post_id": (v or {}).get("post_id")}
                for k, v in st[_bucket(kind)].items()
                if (v or {}).get("post_id") and not (v or {}).get("og_ok")
                and (v or {}).get("ts", 0) >= cut]
    return sql("SELECT ref_id, post_id FROM fb_posted WHERE kind = ? AND og_ok = 0 "
               "AND post_id IS NOT NULL AND posted_at >= ?", [kind, cut])


def failed_count(kind, ref_id):
    ref_id = str(ref_id)
    if backend() == "json":
        v = _fb_json()["failed"].get(ref_id, 0)
        return v if isinstance(v, int) else (v or {}).get("attempts", 0)
    rows = sql("SELECT attempts FROM fb_failed WHERE kind = ? AND ref_id = ?",
               [kind, ref_id])
    return rows[0]["attempts"] if rows else 0


def bump_failed(kind, ref_id, error=None):
    ref_id, now = str(ref_id), int(time.time())
    if backend() == "json":
        st = _fb_json()
        st["failed"][ref_id] = failed_count(kind, ref_id) + 1
        _jsave(FB_JSON, st)
        return
    sql("INSERT INTO fb_failed (kind, ref_id, attempts, last_error, last_at) "
        "VALUES (?, ?, 1, ?, ?) ON CONFLICT (kind, ref_id) DO UPDATE SET "
        "attempts = attempts + 1, last_error = excluded.last_error, "
        "last_at = excluded.last_at", [kind, ref_id, (error or "")[:400], now])


def clear_failed(kind, ref_id):
    ref_id = str(ref_id)
    if backend() == "json":
        st = _fb_json()
        st["failed"].pop(ref_id, None)
        _jsave(FB_JSON, st)
        return
    sql("DELETE FROM fb_failed WHERE kind = ? AND ref_id = ?", [kind, ref_id])


def seen_get(match_id):
    """(score, first_at) for a score awaiting stability, or (None, None)."""
    match_id = str(match_id)
    if backend() == "json":
        v = _fb_json()["seen"].get(match_id) or {}
        return v.get("s"), v.get("ts")
    rows = sql("SELECT score, first_at FROM fb_seen WHERE match_id = ?", [match_id])
    return (rows[0]["score"], rows[0]["first_at"]) if rows else (None, None)


def seen_set(match_id, score, now=None):
    """Start (or restart) the stability clock for this score. `now` is
    injectable so a test can drive the STABLE_MIN window without waiting -
    without it the timer could only ever be tested against the real clock."""
    match_id, now = str(match_id), int(now if now is not None else time.time())
    if backend() == "json":
        st = _fb_json()
        st["seen"][match_id] = {"s": score, "ts": now}
        _jsave(FB_JSON, st)
        return
    sql("INSERT INTO fb_seen (match_id, score, first_at) VALUES (?, ?, ?) "
        "ON CONFLICT (match_id) DO UPDATE SET score = excluded.score, "
        "first_at = excluded.first_at", [match_id, score, now])


def seen_clear(match_id):
    match_id = str(match_id)
    if backend() == "json":
        st = _fb_json()
        st["seen"].pop(match_id, None)
        _jsave(FB_JSON, st)
        return
    sql("DELETE FROM fb_seen WHERE match_id = ?", [match_id])


def fb_prune(keep_days=7):
    """Drop old card rows + stale stability entries. Articles are kept: they are
    the dedup record for /a/ pages that stay online."""
    if backend() == "json":
        return 0
    cut = int(time.time()) - keep_days * 86400
    sql("DELETE FROM fb_posted WHERE kind = 'card' AND COALESCE(posted_at, claimed_at) < ?",
        [cut])
    sql("DELETE FROM fb_seen WHERE first_at < ?", [cut])
    return 1


# ---------------------------------------------------------------- predictions
_PRED_COLS = ["comp", "home", "away", "kickoff", "koff_time", "ph", "pd", "pa",
              "lh", "la", "score", "conf", "predicted_on"]


def pred_all():
    """{match_id: {...}} in the same shape analysis.py has always used
    ('as' is the away score, matching the old JSON key)."""
    if backend() == "json":
        return _jload(PRED_JSON, {})
    out = {}
    for r in sql("SELECT * FROM predictions", []):
        d = dict(r)
        mid = d.pop("match_id")
        d["as"] = d.pop("away_score", None)
        d["ts"] = d.pop("predicted_on", None)
        out[mid] = d
    return out


def pred_freeze(match_id, rec):
    """Write a prediction ONCE. A row that already exists is never overwritten —
    that immutability is what makes the published accuracy trustworthy."""
    match_id = str(match_id)
    if backend() == "json":
        d = _jload(PRED_JSON, {})
        if match_id in d and d[match_id].get("hs") is not None:
            return False
        d[match_id] = rec
        _jsave(PRED_JSON, d)
        return True
    vals = [rec.get("comp"), rec.get("home"), rec.get("away"), rec.get("kickoff"),
            rec.get("koff_time"), rec.get("ph"), rec.get("pd"), rec.get("pa"),
            rec.get("lh"), rec.get("la"), rec.get("score"), rec.get("conf"),
            rec.get("ts")]
    try:
        sql("INSERT INTO predictions (match_id, " + ", ".join(_PRED_COLS) + ") "
            "VALUES (?" + ", ?" * len(_PRED_COLS) + ")", [match_id] + vals)
        return True
    except Conflict:
        # refresh only while the match is still unplayed; never touch a scored row
        rows = sql("UPDATE predictions SET " +
                   ", ".join(f"{c} = ?" for c in _PRED_COLS) +
                   " WHERE match_id = ? AND hs IS NULL RETURNING match_id",
                   vals + [match_id])
        return bool(rows)


def pred_score(match_id, hs, away_score, outcome, pick, hit, brier, score_hit):
    """Grade a frozen prediction against the real result. Scored rows are final."""
    match_id = str(match_id)
    if backend() == "json":
        d = _jload(PRED_JSON, {})
        e = d.get(match_id)
        if not e or e.get("hs") is not None:
            return False
        e.update({"hs": hs, "as": away_score, "outcome": outcome, "pick": pick,
                  "hit": hit, "brier": brier, "score_hit": score_hit})
        _jsave(PRED_JSON, d)
        return True
    rows = sql("UPDATE predictions SET hs = ?, away_score = ?, outcome = ?, pick = ?, "
               "hit = ?, brier = ?, score_hit = ? WHERE match_id = ? AND hs IS NULL "
               "RETURNING match_id",
               [hs, away_score, outcome, pick, 1 if hit else 0, brier,
                1 if score_hit else 0, match_id])
    return bool(rows)


def pred_prune(keep_days=150):
    if backend() == "json":
        return 0
    import datetime
    cut = (datetime.date.today() - datetime.timedelta(days=keep_days)).isoformat()
    sql("DELETE FROM predictions WHERE kickoff < ?", [cut])
    return 1


# ---------------------------------------------------------------- export
def export_json():
    """Dump both tables back into data/*.json.

    NOT for the build - nothing reads these once D1 is on. They are the
    git-tracked audit log and the backup: walking 79 historical versions of
    fb_posted.json is how the duplicate-post bug was found in the first place,
    and that forensic ability is worth one commit per cycle.
    """
    if backend() == "json":
        return False
    fb = {"posted": {}, "failed": {}, "articles": {}, "seen": {}}
    for r in sql("SELECT * FROM fb_posted", []):
        rec = {"ts": r.get("posted_at") or r.get("claimed_at"),
               "post_id": r.get("post_id")}
        if r.get("title"):
            rec["title"] = r["title"]
        if r.get("score"):
            rec["s"] = r["score"]
        if r.get("og_ok"):
            rec["og_ok"] = True
        fb[_bucket(r["kind"])][r["ref_id"]] = rec
    for r in sql("SELECT * FROM fb_failed", []):
        fb["failed"][r["ref_id"]] = r["attempts"]
    for r in sql("SELECT * FROM fb_seen", []):
        fb["seen"][r["match_id"]] = {"s": r["score"], "ts": r["first_at"]}
    _jsave(FB_JSON, fb)
    _jsave(PRED_JSON, pred_all())
    return True


def import_json():
    """One-time migration: existing JSON state -> D1. Idempotent (skips rows
    that are already there), so it is safe to re-run after a partial failure."""
    st = _fb_json()
    n = 0
    for kind, bucket in (("article", "articles"), ("card", "posted")):
        for ref_id, v in (st.get(bucket) or {}).items():
            v = v or {}
            ts = int(v.get("ts") or time.time())
            try:
                sql("INSERT INTO fb_posted (kind, ref_id, post_id, title, score, "
                    "og_ok, claimed_at, posted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [kind, str(ref_id), v.get("post_id"), v.get("title"),
                     v.get("s"), 1 if v.get("og_ok") else 0, ts, ts])
                n += 1
            except Conflict:
                pass
    for ref_id, v in (st.get("failed") or {}).items():
        attempts = v if isinstance(v, int) else (v or {}).get("attempts", 0)
        try:
            sql("INSERT INTO fb_failed (kind, ref_id, attempts) VALUES ('card', ?, ?)",
                [str(ref_id), attempts])
            n += 1
        except Conflict:
            pass
    for ref_id, v in (st.get("seen") or {}).items():
        try:
            sql("INSERT INTO fb_seen (match_id, score, first_at) VALUES (?, ?, ?)",
                [str(ref_id), (v or {}).get("s"), int((v or {}).get("ts") or 0)])
            n += 1
        except Conflict:
            pass
    for mid, e in _jload(PRED_JSON, {}).items():
        e = e or {}
        try:
            sql("INSERT INTO predictions (match_id, comp, home, away, kickoff, "
                "koff_time, ph, pd, pa, lh, la, score, conf, predicted_on, hs, "
                "away_score, outcome, pick, hit, brier, score_hit) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [str(mid), e.get("comp"), e.get("home"), e.get("away"),
                 e.get("kickoff"), e.get("koff_time"), e.get("ph"), e.get("pd"),
                 e.get("pa"), e.get("lh"), e.get("la"), e.get("score"),
                 e.get("conf"), e.get("ts"), e.get("hs"), e.get("as"),
                 e.get("outcome"), e.get("pick"),
                 None if e.get("hit") is None else (1 if e["hit"] else 0),
                 e.get("brier"),
                 None if e.get("score_hit") is None else (1 if e["score_hit"] else 0)])
            n += 1
        except Conflict:
            pass
    return n


def counts():
    """Row counts per table — the health check after migration and in CI."""
    if backend() == "json":
        st = _fb_json()
        return {"articles": len(st["articles"]), "cards": len(st["posted"]),
                "failed": len(st["failed"]), "seen": len(st["seen"]),
                "predictions": len(_jload(PRED_JSON, {}))}
    def one(q, p=None):
        return (sql(q, p) or [{"n": 0}])[0]["n"]
    return {"articles": one("SELECT COUNT(*) n FROM fb_posted WHERE kind='article'"),
            "cards": one("SELECT COUNT(*) n FROM fb_posted WHERE kind='card'"),
            "open_claims": one("SELECT COUNT(*) n FROM fb_posted WHERE post_id IS NULL"),
            "failed": one("SELECT COUNT(*) n FROM fb_failed"),
            "seen": one("SELECT COUNT(*) n FROM fb_seen"),
            "predictions": one("SELECT COUNT(*) n FROM predictions"),
            "pred_scored": one("SELECT COUNT(*) n FROM predictions WHERE hs IS NOT NULL")}


def warehouse_counts():
    """Row counts for the analytics warehouse (see warehouse.py).

    Kept apart from counts() because these tables arrived later: a store that
    has not run --init since then has the state tables but not these, and the
    health check for the state store should not start failing because of it.
    """
    if backend() == "json":
        return {}
    out = {}
    for t in ("competitions", "teams", "matches", "team_strength", "league_params",
              "players", "match_lineups", "match_goals", "match_cards",
              "match_subs", "top_players", "standings", "standings_meta",
              "articles", "article_sources", "article_faq", "article_clubs"):
        out[t] = (sql(f"SELECT COUNT(*) n FROM {t}") or [{"n": 0}])[0]["n"]
    return out

# ==================================================================== articles
# D1 is the writer for articles as of 2026-09-10. data/articles.json is now the
# EXPORT: still committed on every publish (it is the build's fallback and the
# forensic log), but no longer the thing that decides what exists.
#
# The json field order used to be whatever each AI run happened to produce - 18
# distinct orders across 403 articles - so the export normalises it. That is a
# one-off reshuffle of the file and deterministic diffs from then on.

ARTICLE_FIELDS = ["article_id", "title", "summary", "body", "author",
                  "pub_date", "pub_ts", "match_id", "kind", "image_url",
                  "image_credit", "sources", "faq", "fb_post",
                  "updated_ts", "upgraded_ts"]

# columns the caller owns; words/thin are editorial, computed by the caller
ARTICLE_COLS = ["title", "summary", "body", "author", "pub_date", "pub_ts",
                "match_id", "kind", "image_url", "image_credit", "fb_post",
                "updated_ts", "upgraded_ts", "words", "thin", "has_sources",
                "has_faq", "body_hash"]


class DuplicateArticle(Exception):
    """A second preview/report for a match the site already covered."""


def _is_conflict(e):
    m = str(e).lower()
    return "unique" in m or "constraint" in m


def article_all(with_body=True):
    """Every article, newest id first, shaped like data/articles.json items.

    One query for the articles and one each for sources and FAQ - not one per
    article. 403 articles must not become 1209 HTTP calls.
    """
    if backend() == "json":
        return _jload(ARTICLES_JSON,
                      {"results": [{"items": []}]})["results"][0]["items"]
    cols = ", ".join(c for c in ARTICLE_COLS if with_body or c != "body")
    rows = sql(f"SELECT article_id, {cols} FROM articles "
               f"ORDER BY CAST(article_id AS INTEGER) DESC")
    kids = {}
    for r in sql("SELECT article_id, seq, name, url, note FROM article_sources "
                 "ORDER BY article_id, seq"):
        kids.setdefault(r["article_id"], {}).setdefault("sources", []).append(
            {"name": r["name"], "url": r["url"], "note": r["note"]})
    for r in sql("SELECT article_id, seq, q, a FROM article_faq "
                 "ORDER BY article_id, seq"):
        kids.setdefault(r["article_id"], {}).setdefault("faq", []).append(
            {"q": r["q"], "a": r["a"]})
    out = []
    for r in rows:
        a = dict(r)
        a.update(kids.get(r["article_id"], {}))
        # NULL means "the field was never there" - emitting it as null would
        # add 400 meaningless keys to the export
        out.append({k: a[k] for k in ARTICLE_FIELDS
                    if a.get(k) is not None and a.get(k) != []})
    return out


def article_doc():
    """data/articles.json as a document, ready for _jsave."""
    return {"results": [{"items": article_all()}]}


ARTICLES_JSON = os.path.join(HERE, "data", "articles.json")


def article_export(path=None):
    """Rewrite data/articles.json from D1. Returns the article count.

    `path` exists so a test can prove the export without overwriting the
    repository's own article file - which it did, once.
    """
    if backend() == "json":
        return 0
    doc = article_doc()
    _jsave(path or ARTICLES_JSON, doc)
    return len(doc["results"][0]["items"])


def _article_children(aid, sources, faq, clubs):
    for i, s in enumerate(sources or []):
        sql("INSERT INTO article_sources (article_id, seq, name, url, note) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(article_id, seq) DO UPDATE SET "
            "name = excluded.name, url = excluded.url, note = excluded.note",
            [aid, i, s.get("name"), s.get("url"), s.get("note")])
    sql("DELETE FROM article_sources WHERE article_id = ? AND seq >= ?",
        [aid, len(sources or [])])
    for i, q in enumerate(faq or []):
        sql("INSERT INTO article_faq (article_id, seq, q, a) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(article_id, seq) DO UPDATE SET q = excluded.q, a = excluded.a",
            [aid, i, q.get("q"), q.get("a")])
    sql("DELETE FROM article_faq WHERE article_id = ? AND seq >= ?",
        [aid, len(faq or [])])
    if clubs is not None:
        sql("DELETE FROM article_clubs WHERE article_id = ?", [aid])
        for slug in clubs:
            sql("INSERT INTO article_clubs (article_id, slug) VALUES (?, ?) "
                "ON CONFLICT(article_id, slug) DO NOTHING", [aid, slug])


def article_add(rec, clubs=None):
    """Insert an article, allocating its id INSIDE the statement.

    `rec` carries the json fields plus the caller's computed words/thin. The id
    comes from `SELECT MAX(...) + 1` in the same INSERT, so two runs publishing
    at the same second get different ids instead of the same one. Returns the
    new article_id.

    Raises DuplicateArticle when the match already has a piece of that kind.
    """
    if backend() == "json":
        raise RuntimeError("article_add needs D1 - refusing to write to json")
    cols = [c for c in ARTICLE_COLS if c != "body_hash"]
    vals = [rec.get(c) for c in cols]
    stmt = ("INSERT INTO articles (article_id, " + ", ".join(cols) +
            ", body_hash, as_of) SELECT CAST(COALESCE(MAX(CAST(article_id AS "
            "INTEGER)), 0) + 1 AS TEXT), " + ", ".join("?" * len(cols)) +
            ", ?, ? FROM articles RETURNING article_id")
    body_hash = _body_hash(rec.get("body") or "")
    try:
        got = sql(stmt, vals + [body_hash, datetime.date.today().isoformat()])
    except Exception as e:                                     # noqa: BLE001
        if _is_conflict(e):
            raise DuplicateArticle(
                f"match {rec.get('match_id')} already has a {rec.get('kind')}")
        raise
    aid = str(got[0]["article_id"])
    _article_children(aid, rec.get("sources"), rec.get("faq"), clubs or [])
    return aid


def article_update(aid, rec, clubs=None):
    """Replace an existing article's fields (the upgrade path). Only the keys
    present in `rec` are touched, so a partial rewrite cannot blank a column
    it did not mean to."""
    if backend() == "json":
        raise RuntimeError("article_update needs D1 - refusing to write to json")
    aid = str(aid)
    if not sql("SELECT article_id FROM articles WHERE article_id = ?", [aid]):
        raise KeyError(f"article {aid} does not exist")
    sets = [c for c in ARTICLE_COLS if c in rec and c != "body_hash"]
    params = [rec[c] for c in sets]
    if "body" in rec:
        sets.append("body_hash")
        params.append(_body_hash(rec.get("body") or ""))
    if not sets:
        return aid
    sql(f"UPDATE articles SET {', '.join(c + ' = ?' for c in sets)} "
        f"WHERE article_id = ?", params + [aid])
    if "sources" in rec or "faq" in rec or clubs is not None:
        _article_children(aid, rec.get("sources"), rec.get("faq"), clubs)
    return aid


def article_get(aid):
    rows = [a for a in article_all() if str(a["article_id"]) == str(aid)]
    return rows[0] if rows else None


def _body_hash(body):
    return hashlib.sha1((body or "").encode("utf-8")).hexdigest()[:16]
