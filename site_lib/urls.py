"""Article and match URLs, match-piece detection, breadcrumbs.

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.text import jsonld


def article_href(a):
    """Site-relative URL of an article.

    A match preview/report lives INSIDE its match page (2026-09-16): one URL per
    match carrying the story, the numbers, the XI and the result, instead of a
    prose page at /a/ and a data page at /m/ competing for the same query with
    half an answer each. Everything that links an article goes through here, so
    the move is one function wide. The old /a/<id> URLs keep working as 301s
    (see the _redirects file the build writes) - 43 of the 44 have a published
    Facebook post pointing at them.
    """
    if a.get("kind") in ("preview", "report") and a.get("match_id"):
        return f"/m/{a['match_id']}.html"
    return f"/a/{a['article_id']}.html"


def is_match_piece(a):
    return bool(a.get("kind") in ("preview", "report") and a.get("match_id"))


def pick_match_article(pieces, status):
    """One piece per match page: the report once the match is over, otherwise
    the preview. Both on one page would tell the same story twice."""
    if not pieces:
        return None
    want = "report" if status == "FINISHED" else "preview"
    return (next((a for a in pieces if a.get("kind") == want), None)
            or sorted(pieces, key=lambda a: a.get("pub_ts") or "")[-1])


def breadcrumb_ld(items):
    """BreadcrumbList JSON-LD from [(name, absolute_url), ...]."""
    return jsonld({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u}
            for i, (n, u) in enumerate(items)]})


def match_url(m):
    """Canonical per-match page path, or None when the id is missing."""
    return f"/m/{m['match_id']}.html" if m.get("match_id") else None
