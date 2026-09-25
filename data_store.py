# -*- coding: utf-8 -*-
"""The site's working data in Workers KV instead of git (2026-09-24, step 3).

    python data_store.py push      # publish.yml, after the fetch + archive + build
    python data_store.py pull      # every job that needs data/, before it reads it
    python data_store.py verify    # remote bundle vs the local files, file by file
    python data_store.py status

WHY. 1,128 of 1,309 commits in a week were "data refresh" commits and .git had
reached 469 MB. Worse than the size: every data commit MOVED main, and most of
this pipeline's incidents were races around that - the deploy guard skipping a
green run's deploy, the commit-back rebasing 75% of the time, the stale repo
copy that once put July's headlines live in August. Code belongs in git;
working data does not.

WHERE. Workers KV, one key holding a gzip bundle of the STORE_FILES below:
  * not D1 - the D1 quota wall hit twice (09-15, 09-16); putting the build's
    input behind the same quota would turn a quota day into a no-build day;
  * not R2 - enabling it needs a card on file, which this account cannot add;
  * KV is free with no card, has its OWN quota (1,000 writes / 100,000 reads
    a day) and the Worker binds it directly (/data/<file> for the laptop and
    the secret-less test job). One bundle per publish run = ~100 writes a day.

SAFETY, the three rules this file exists to enforce:
  1. A job whose pull FAILED must not build from what it has - the checkout
     no longer carries fresh data, so that would be the July-headlines trap.
     `pull` exits non-zero; the workflow stops before fetch/build/deploy.
  2. Only a job that PULLED may push (data/.store_state.json proves it) - a
     run that started from nothing would otherwise overwrite the accumulating
     archives with a truncated fresh fetch.
  3. An accumulating file that shrinks hard (results_archive, matches_archive,
     match_details) is refused - it is a bug, never a real change.
If someone pushed since our pull, the accumulating files are MERGED by key
(ours wins, a frozen result always survives) instead of last-writer-wins.

TRANSPORT. The Cloudflare REST API with CLOUDFLARE_API_TOKEN (the deploy
token; its "Edit Workers" template includes Workers KV) and CF_ACCOUNT_ID.
Without a token, `pull` reads the Worker's public /data/bundle instead - how
the laptop, the tests job and a local checkout get data.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
STATE = os.path.join(DATA, ".store_state.json")
NAMESPACE_TITLE = "yallascore-data"
KEY = "bundle-v1"
PUBLIC = "https://yallascore.site/data/bundle"
API = "https://api.cloudflare.com/client/v4/accounts/{acct}/storage/kv/namespaces"

# What fetch_data.py and results_archive.py produce every run. Hand-curated
# files (elo_seeds, image_fixes, media_credits, reels, videos) and the D1
# exports (articles, fb_posted, predictions, live_goals) stay in git.
STORE_FILES = [
    "matches.json", "matches_archive.json", "fixtures.json", "standings.json",
    "scorers.json", "assists.json", "goal_events.json", "match_details.json",
    "headlines.json", "fetch_debug.json", "results_archive.json", "reels_auto.json",
]

# accumulating files: key function per item, for the merge and the shrink guard
def _items(doc):
    """The item list of a file, whatever its shape: {results:[{items:[..]}]}
    (write_items), {results:[...]} (results_archive) or a bare list."""
    if isinstance(doc, list):
        return doc
    res = (doc or {}).get("results")
    if isinstance(res, list) and res and isinstance(res[0], dict) and "items" in res[0]:
        return res[0]["items"]
    return res if isinstance(res, list) else []


def _set_items(doc, items):
    if isinstance(doc, list):
        return items
    res = doc.get("results")
    if isinstance(res, list) and res and isinstance(res[0], dict) and "items" in res[0]:
        doc["results"][0]["items"] = items
    else:
        doc["results"] = items
    return doc


ACCUMULATING = {
    "results_archive.json": lambda e: str(e.get("match_id")),
    "matches_archive.json": lambda e: str(e.get("match_id")),
    "match_details.json": lambda e: f'{e.get("date")}|{e.get("home")}|{e.get("away")}',
}
SHRINK_LIMIT = 0.90        # refuse a push that loses >10% of an archive's entries


# ------------------------------------------------------------------ bundle
def _sha(b):
    return hashlib.sha1(b).hexdigest()[:16]


def read_local():
    """{name: bytes} for every STORE_FILE present locally."""
    out = {}
    for n in STORE_FILES:
        p = os.path.join(DATA, n)
        if os.path.exists(p):
            with open(p, "rb") as f:
                out[n] = f.read()
    return out


def pack(files, meta):
    body = {"meta": meta, "files": {n: base64.b64encode(b).decode("ascii") for n, b in files.items()}}
    return gzip.compress(json.dumps(body).encode("utf-8"), 6)


def unpack(blob):
    body = json.loads(gzip.decompress(blob).decode("utf-8"))
    return body["meta"], {n: base64.b64decode(s) for n, s in body["files"].items()}


# ------------------------------------------------------------------ transport
def _token():
    return os.environ.get("CLOUDFLARE_API_TOKEN") or os.environ.get("CF_API_TOKEN")


def _req(method, url, data=None, ctype=None, token=None, timeout=60):
    h = {"User-Agent": "yalla-data-store/1.0"}
    if token:
        h["Authorization"] = "Bearer " + token
    if ctype:
        h["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def namespace_id(create=False):
    """The KV namespace's id, found by title; created once when asked."""
    acct, tok = os.environ["CF_ACCOUNT_ID"], _token()
    base = API.format(acct=acct)
    _, body = _req("GET", base + "?per_page=100", token=tok)
    for ns in json.loads(body).get("result") or []:
        if ns.get("title") == NAMESPACE_TITLE:
            return ns["id"]
    if not create:
        return None
    _, body = _req("POST", base, json.dumps({"title": NAMESPACE_TITLE}).encode(), "application/json", tok)
    return json.loads(body)["result"]["id"]


def remote_get():
    """(meta, files) of the remote bundle, or (None, {}) when it does not exist
    yet. Raises on a transport failure - the caller decides what that means."""
    if _token() and os.environ.get("CF_ACCOUNT_ID"):
        ns = namespace_id()
        if ns is None:
            return None, {}
        url = f"{API.format(acct=os.environ['CF_ACCOUNT_ID'])}/{ns}/values/{KEY}"
        try:
            _, blob = _req("GET", url, token=_token())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, {}
            raise
    else:
        try:
            _, blob = _req("GET", PUBLIC + f"?b={int(time.time() // 60)}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, {}
            raise
    return unpack(blob)


def remote_put(blob):
    ns = namespace_id(create=True)
    url = f"{API.format(acct=os.environ['CF_ACCOUNT_ID'])}/{ns}/values/{KEY}"
    _req("PUT", url, blob, "application/octet-stream", _token())


# ------------------------------------------------------------------ the rules
def merge(name, ours, theirs):
    """Union by key for an accumulating file (ours wins; a frozen result from
    either side survives). Anything else: ours, as before (newest fetch wins)."""
    kf = ACCUMULATING.get(name)
    if not kf:
        return ours
    a, b = json.loads(ours), json.loads(theirs)
    merged = {kf(e): e for e in _items(b)}
    for e in _items(a):
        k, old = kf(e), merged.get(kf(e))
        if old and old.get("frozen") and not e.get("frozen"):
            continue
        merged[k] = e
    return json.dumps(_set_items(a, list(merged.values())), ensure_ascii=False).encode("utf-8")


def shrink_problems(local, remote):
    out = []
    for name in ACCUMULATING:
        if name in local and name in remote:
            n_l, n_r = len(_items(json.loads(local[name]))), len(_items(json.loads(remote[name])))
            if n_r >= 20 and n_l < n_r * SHRINK_LIMIT:
                out.append(f"{name}: {n_l} entries vs {n_r} remote")
    return out


# ------------------------------------------------------------------ commands
def pull():
    meta, files = remote_get()
    if meta is None:
        print("::error::the data store is empty - nothing to pull (seed it with a push first)")
        return 2
    missing = [n for n in ("matches.json", "fixtures.json", "results_archive.json") if n not in files]
    if missing:
        print(f"::error::the remote bundle lacks {missing} - refusing to build from it")
        return 2
    os.makedirs(DATA, exist_ok=True)
    for n, b in files.items():
        with open(os.path.join(DATA, n), "wb") as f:
            f.write(b)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"pulled_at": int(time.time()), "remote_ver": meta.get("ver"),
                   "sha": {n: _sha(b) for n, b in files.items()}}, f)
    age = (time.time() - (meta.get("ts") or 0)) / 60
    print(f"pulled {len(files)} files from the data store (bundle written {age:.0f} min ago by {meta.get('by')})")
    return 0


def push(seed=False, by=None):
    local = read_local()
    if not local:
        print("::error::no data files to push")
        return 2
    state = None
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)
    if state is None and not seed:
        print("::error::this job never pulled the data store - refusing to push "
              "(it would overwrite the archives with whatever this checkout has)")
        return 2
    meta, remote = remote_get()
    if meta is not None:
        probs = shrink_problems(local, remote)
        if probs:
            print("::error::refusing to push - an accumulating file shrank: " + "; ".join(probs))
            return 3
        # a random version per push, NOT the timestamp: two pushes inside the
        # same second compared equal by time and the merge never ran (caught
        # by test_data_store 5b)
        if state and meta.get("ver") != state.get("remote_ver"):
            # someone pushed since we pulled: merge the archives instead of
            # silently dropping what that run added
            for name in ACCUMULATING:
                if name in local and name in remote:
                    local[name] = merge(name, local[name], remote[name])
            print("  another run pushed since our pull - archives merged by key")
    elif not seed:
        print("::error::the data store is empty but this is not a --seed push")
        return 2
    new_meta = {"ts": int(time.time()), "ver": secrets.token_hex(8),
                "by": by or os.environ.get("GITHUB_RUN_ID") or "local",
                "sha": {n: _sha(b) for n, b in local.items()}}
    if meta and meta.get("sha") == new_meta["sha"]:
        print("data store already holds these exact files - nothing written")
        return 0
    blob = pack(local, new_meta)
    remote_put(blob)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"pulled_at": int(time.time()), "remote_ver": new_meta["ver"], "sha": new_meta["sha"]}, f)
    print(f"pushed {len(local)} files to the data store ({len(blob) // 1024} KB gzip)")
    return 0


def verify():
    meta, remote = remote_get()
    if meta is None:
        print("the data store is empty")
        return 1
    local = read_local()
    bad = 0
    for n in STORE_FILES:
        l, r = local.get(n), remote.get(n)
        if l is None and r is None:
            continue
        same = (l is not None and r is not None and _sha(l) == _sha(r))
        bad += 0 if same else 1
        print(f"  {'same' if same else 'DIFF'}  {n:24} local {len(l or b''):>9}  remote {len(r or b''):>9}")
    print(f"{'identical' if not bad else f'{bad} file(s) differ'} (bundle by {meta.get('by')}, "
          f"{(time.time() - meta.get('ts', 0)) / 60:.0f} min old)")
    return 0 if not bad else 1


def nsid():
    """For the deploy step: the namespace id (created on first use), or nothing."""
    print(namespace_id(create=True) or "")
    return 0


def status():
    meta, remote = remote_get()
    if meta is None:
        print("the data store is empty")
        return 0
    print(f"bundle by {meta.get('by')}, {(time.time() - meta.get('ts', 0)) / 60:.0f} min old, "
          f"{len(remote)} files, {sum(len(b) for b in remote.values()) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["push", "pull", "verify", "status", "nsid"])
    ap.add_argument("--seed", action="store_true", help="first push into an empty store")
    a = ap.parse_args()
    try:
        rc = {"push": lambda: push(seed=a.seed), "pull": pull, "verify": verify,
              "status": status, "nsid": nsid}[a.cmd]()
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(f"::error::data store {a.cmd} failed: {e!r}")
        rc = 4
    sys.exit(rc)
