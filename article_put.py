# -*- coding: utf-8 -*-
"""Publish or rewrite an article. THE way an article enters the site.

D1 is the writer as of 2026-09-10; data/articles.json is the export. Hand-
editing that file is no longer how an article is published, because doing so
re-opens two races we have already been bitten by:

  * "new article_id = max(existing) + 1", computed in Python from a file, gives
    two runs publishing in the same minute the SAME id;
  * two runs each rewriting the whole file means whoever pushes second wins and
    the other article is gone (this is exactly how the duplicate/lost Facebook
    posts happened, one layer down).

Here the id is allocated inside the INSERT and a unique index refuses a second
preview/report for the same match. Then the file is regenerated from D1, so the
commit still carries it and the build keeps its offline fallback.

Usage
    python article_put.py --new draft.json
    python article_put.py --update 54 draft.json     # the upgrade path
    python article_put.py --export                   # rewrite the json from D1
    python article_put.py --check draft.json         # validate, write nothing
    python article_put.py --retry-pending            # publish a rescued draft

draft.json is one article object with the same field names the json uses:
title, summary, body, author, pub_date, pub_ts, image_url, image_credit,
sources, faq, fb_post, and match_id + kind on a match piece.
"""
import glob
import hashlib
import json
import os
import sys
import urllib.parse
import datetime

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as b     # noqa: E402  - words/thin and the club matcher
import store               # noqa: E402

# A draft that passed every check and then lost to the database.
#
# D1's free tier has a daily row-READ limit as well as a write one, and it has
# now run out twice (2026-09-16, 2026-09-19). The second time a run had already
# found the story, written 545 words, cleared `--check` with 3 sources and 3
# FAQ, and vetted an image - and `store.article_add` raised
# «exceeded D1's free tier daily row read limit» on the INSERT. The article was
# thrown away and the next slot started researching from scratch. Checked
# afterwards: nothing partial landed either, so it was simply gone.
#
# Hand-editing data/articles.json is NOT the fallback (that is the race this
# whole file exists to close). Instead the finished draft is parked here, the
# workflow commits it, and the next run publishes it before it goes looking
# for anything new. An outage then costs a DELAY, not an article.
PENDING_DIR = os.path.join(HERE, "drafts")
PENDING_MAX_H = 18      # news, not an archive: a draft older than this is
                        # dropped rather than published stale. The read quota
                        # resets at 00:00 UTC, so a draft parked at the worst
                        # possible moment waits at most a few hours.

REQUIRED = ("title", "summary", "body", "author", "pub_date")
ALLOWED = set(store.ARTICLE_FIELDS) - {"article_id"}


OUR_HOSTS = {"yallascore.site", "old-credit-e926.workers.dev"}


def source_keys(rec):
    """Distinct source identities in a draft.

    The domain when the entry has a url, else the normalised name: two links
    from the same outlet are ONE source, because what /editorial promises is
    two INDEPENDENT ones. Our own pages never count - linking our match page
    is a citation of ourselves.
    """
    keys = set()
    for s in rec.get("sources") or []:
        if not isinstance(s, dict):
            continue
        key = ""
        url = (s.get("url") or "").strip()
        if url:
            host = urllib.parse.urlparse(url).netloc.lower()
            key = host[4:] if host.startswith("www.") else host
        if not key:
            key = " ".join((s.get("name") or "").split()).casefold()
        if key and key not in OUR_HOSTS:
            keys.add(key)
    return keys


def source_problems(rec):
    """The two-source rule, enforced where an article enters the site.

    /editorial says, in Arabic, on a page a reviewer can read: «لا ننشر خبرًا
    إلا بعد تطابقه لدى مصدرين مستقلين على الأقل». 37 news articles published
    on 1-2 September carry no sources at all, and an outside audit of the live
    site (2026-09-16) found the gap by simply comparing the policy page with an
    article. A promise the pipeline cannot keep is worse than no promise, so
    the pipeline keeps it.

    Applies to NEWS only, and only when creating. A match preview/report is not
    a news claim - it is built from our own match data, and one data credit is
    the honest answer there (build_site.match_data_sources guarantees it). On
    --update the draft carries only the changed fields, so `kind` is usually
    absent and we cannot tell news from a match piece without a lookup; the
    upgrade prompt adds sources anyway, and blocking a fix to an image over a
    missing field would be the wrong trade.

    The escape hatch is real editorial practice, not a loophole: a club's or
    federation's OWN announcement is sufficient on its own. Mark it
    {"official": true} and one source is enough.
    """
    out = []
    for s in rec.get("sources") or []:
        if not isinstance(s, dict) or not (s.get("name") or "").strip():
            out.append(f"a source with no name is dropped silently when rendering: {s!r}")
    if any(isinstance(s, dict) and s.get("official") for s in rec.get("sources") or []):
        if not source_keys(rec):
            out.append("a source marked official still needs a name or a url")
        return out
    n = len(source_keys(rec))
    if n < 2:
        out.append(
            f"news with {n} independent source(s). /editorial promises the reader "
            "«لا ننشر خبرًا إلا بعد تطابقه لدى مصدرين مستقلين على الأقل» - add a "
            "second outlet (a different domain), or, when the story IS the club's "
            "or federation's own announcement, mark that source {\"official\": true} "
            "and one is enough."
        )
    return out


def validate(rec, updating=False):
    """Problems worth refusing to publish over."""
    bad = []
    if not updating:
        for f in REQUIRED:
            v = rec.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                bad.append(f"missing {f}")
    for k in rec:
        if k not in ALLOWED:
            bad.append(f"unknown field {k!r}")
    if bool(rec.get("match_id")) != bool(rec.get("kind")):
        bad.append("match_id and kind go together (both or neither)")
    if rec.get("kind") and rec["kind"] not in ("preview", "report"):
        bad.append(f"kind must be preview or report, not {rec['kind']!r}")
    if rec.get("image_url") and not rec.get("image_credit") \
            and "ph-pitch" not in rec["image_url"] and "ph-ball" not in rec["image_url"]:
        # the standing rule: no credit, no use. Only our own placeholders are
        # exempt, and they are the last resort anyway.
        bad.append("image_url without image_credit (only our placeholders are exempt)")
    for u in rec.get("embeds") or []:
        # an embed must be an https post URL on X / Instagram / Facebook - the
        # club's own announcement, not a guess (the prompts say official only)
        if not isinstance(u, str) or not store.embed_platform(u):
            bad.append(f"embed is not an X/Instagram/Facebook post URL: {u!r}")
    if not updating and not rec.get("kind"):
        bad += source_problems(rec)
    words = len(b.strip_tags(rec.get("body") or "").split())
    if not updating and words < 300:
        bad.append(f"body is {words} words - under the {b.ARTICLE_MIN_WORDS}-word bar, "
                   f"so it would publish UNLISTED")
    return bad, words


def enrich(rec, words):
    """Add what the DB stores but the json does not: the editorial counters.

    Only for what the draft actually carries. A partial update (the
    sources-only pass) has no body, and writing `words = 0, thin = 1` for it
    would mark a 550-word article as thin in the warehouse - true of the draft,
    false of the article.
    """
    out = dict(rec)
    if "body" in rec:
        out["words"] = words
        out["thin"] = 1 if words < b.ARTICLE_MIN_WORDS else 0
    if "sources" in rec:
        out["has_sources"] = 1 if rec.get("sources") else 0
    if "faq" in rec:
        out["has_faq"] = 1 if rec.get("faq") else 0
    if out.get("match_id") is not None:
        out["match_id"] = str(out["match_id"])
    return out


def clubs_of(rec, aid="new"):
    return [tp["slug"] for tp in b.article_clubs(dict(rec, article_id=aid))]


def save_pending(rec):
    """Park a validated draft under drafts/. Returns the path.

    The name is derived from the title, so a run that retries the same draft
    overwrites its own file instead of leaving a second copy behind.
    """
    os.makedirs(PENDING_DIR, exist_ok=True)
    key = hashlib.md5((rec.get("title") or "").encode("utf-8")).hexdigest()[:8]
    path = os.path.join(PENDING_DIR,
                        f"{rec.get('pub_date') or 'undated'}-{key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
        f.write("\n")
    try:
        return os.path.relpath(path, HERE).replace(os.sep, "/")
    except ValueError:
        # Windows: relpath raises across drives. PENDING_DIR is under HERE in
        # production, but a test pointing it at the temp dir must not crash
        # the rescue path that exists to stop things being lost.
        return path.replace(os.sep, "/")


def _too_old(rec):
    """A parked draft is news; past PENDING_MAX_H it is not."""
    ts = (rec.get("pub_ts") or "").strip()
    if not ts:
        return False
    try:
        when = datetime.datetime.fromisoformat(ts)
    except ValueError:
        return False
    now = datetime.datetime.now(when.tzinfo) if when.tzinfo else datetime.datetime.now()
    return (now - when).total_seconds() / 3600 > PENDING_MAX_H


def retry_pending():
    """Publish the oldest parked draft. 0 = nothing to do or done, 2 = D1 still down.

    Deliberately publishes AT MOST ONE: the site's rule is one article per
    run, and a queue that empties itself all at once would dump three pieces
    into the feed at the same minute.
    """
    files = sorted(glob.glob(os.path.join(PENDING_DIR, "*.json")))
    if not files:
        print("no parked draft")
        return 0
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception as e:                               # noqa: BLE001
            print(f"{name}: unreadable ({e}) - removing")
            os.remove(path)
            continue
        rec.pop("article_id", None)
        if _too_old(rec):
            print(f"{name}: older than {PENDING_MAX_H}h - dropping, "
                  "it is no longer news")
            os.remove(path)
            continue
        bad, words = validate(rec)
        if bad:
            # it validated when it was parked; if it does not now, something
            # changed under it and a stuck file would block every future run
            print(f"{name}: no longer valid ({bad[0]}) - removing")
            os.remove(path)
            continue
        clubs = clubs_of(rec)
        try:
            aid = store.article_add(enrich(rec, words), clubs=clubs)
        except store.DuplicateArticle:
            print(f"{name}: the site already covers it - removing")
            os.remove(path)
            continue
        except Exception as e:                               # noqa: BLE001
            print(f"{name}: D1 still refusing ({e}) - left parked")
            return 2
        os.remove(path)
        n = store.article_export()
        print(f"parked draft {name} published as article {aid} "
              f"(pub_ts {rec.get('pub_ts') or '?'}) - "
              f"data/articles.json rewritten, {n} articles")
        return 0
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    mode = args[0]

    if store.backend() != "d1" and mode != "--check":
        print("!! D1 is not configured (CF_API_TOKEN / CF_ACCOUNT_ID / CF_D1_ID).")
        print("   Refusing to publish: writing to data/articles.json by hand is")
        print("   the racy path this script exists to replace.")
        return 1

    if mode == "--retry-pending":
        return retry_pending()

    if mode == "--export":
        n = store.article_export()
        print(f"data/articles.json rewritten from D1: {n} articles")
        return 0

    path = args[-1]
    if not os.path.exists(path):
        print(f"no such draft file: {path}")
        return 1
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    if isinstance(rec, dict) and "results" in rec:      # a one-item json export
        rec = rec["results"][0]["items"][0]
    rec.pop("article_id", None)

    updating = mode == "--update"
    bad, words = validate(rec, updating=updating)
    if bad:
        print("REFUSED:")
        for x in bad:
            print("  - " + x)
        return 1
    # the club links are derived from the title/summary/body; a draft without
    # them cannot recompute the list, and passing [] would DELETE it
    clubs = clubs_of(rec) if ("body" in rec or "title" in rec) else None
    print(f"ok: {words} words, clubs={clubs if clubs is not None else 'unchanged'}, "
          f"sources={len(rec.get('sources') or [])}, faq={len(rec.get('faq') or [])}")
    if mode == "--check":
        return 0

    if updating:
        aid = args[1]
        store.article_update(aid, enrich(rec, words), clubs=clubs)
        print(f"article {aid} updated in D1")
    else:
        try:
            aid = store.article_add(enrich(rec, words), clubs=clubs)
        except store.DuplicateArticle as e:
            print(f"REFUSED: {e}")
            print("  the site already covers that match with a piece of this kind")
            return 1
        except Exception as e:                               # noqa: BLE001
            # NOT a bad draft and NOT a duplicate - the database refused it.
            # The draft is good; park it instead of losing it.
            saved = save_pending(rec)
            print(f"D1 REFUSED THE INSERT: {e}")
            print(f"  the finished draft is saved at {saved}")
            print("  COMMIT IT (with any new media/ file) - the next run "
                  "publishes it before looking for a new story.")
            return 2
        print(f"article {aid} inserted in D1")

    n = store.article_export()
    print(f"data/articles.json rewritten from D1: {n} articles")
    print(f"now: git add data/articles.json <any media/ file> && commit && push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
