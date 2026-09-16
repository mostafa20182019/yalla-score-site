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

draft.json is one article object with the same field names the json uses:
title, summary, body, author, pub_date, pub_ts, image_url, image_credit,
sources, faq, fb_post, and match_id + kind on a match piece.
"""
import json
import os
import sys
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as b     # noqa: E402  - words/thin and the club matcher
import store               # noqa: E402

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
    """Add what the DB stores but the json does not: the editorial counters."""
    out = dict(rec)
    out["words"] = words
    out["thin"] = 1 if words < b.ARTICLE_MIN_WORDS else 0
    out["has_sources"] = 1 if rec.get("sources") else 0
    out["has_faq"] = 1 if rec.get("faq") else 0
    if out.get("match_id") is not None:
        out["match_id"] = str(out["match_id"])
    return out


def clubs_of(rec, aid="new"):
    return [tp["slug"] for tp in b.article_clubs(dict(rec, article_id=aid))]


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
    clubs = clubs_of(rec)
    print(f"ok: {words} words, clubs={clubs or ['-']}, "
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
        print(f"article {aid} inserted in D1")

    n = store.article_export()
    print(f"data/articles.json rewritten from D1: {n} articles")
    print(f"now: git add data/articles.json <any media/ file> && commit && push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
