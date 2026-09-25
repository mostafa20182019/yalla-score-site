"""HTML/text primitives: escaping, stripping, JSON-LD, number formatting.

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
import html, json, re


def esc(s):
    return html.escape(s or "", quote=True)


def strip_tags(s):
    import re
    return re.sub(r"<[^>]+>", "", s or "").strip()


def strip_src(title, source):
    """Drop a trailing ' - <source>' suffix from aggregated headlines (like the app)."""
    t = (title or "").strip()
    if source and t.endswith(" - " + source):
        t = t[: -(len(source) + 3)].strip()
    return t


def seo_desc(desc, limit=155):
    """Meta description: Google shows ~155-160 chars; cut at a word boundary
    so the snippet never ends mid-word. (og:description keeps the long form.)"""
    d = " ".join(strip_tags(desc).split())
    if len(d) <= limit:
        return d
    cut = d[:limit].rsplit(" ", 1)[0].rstrip(" ،,.:;-—")
    return cut + "…"


def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'


def article_words(a):
    return len(strip_tags(a.get("body") or "").split())


def _pct(x):
    return f"{round(x * 100)}%"


def _signed_pct(x):
    """+24% / -18%, for a factor's distance from the league average."""
    return ("+" if x >= 0 else "−") + f"{abs(x) * 100:.0f}%"


def _pval(x):
    """Chart value — "value" is the current key, "goals" the original one."""
    v = x.get("value")
    return (x.get("goals") or 0) if v is None else v


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _lam(name):
    """Arabic lam of possession before a club name: «الأهلي» -> «للأهلي»,
    «نيوم» -> «لنيوم». Writing «لـالأهلي» is what a template does, not a writer."""
    name = name or ""
    return ("ل" + name[1:]) if name.startswith("ال") else ("ل" + name)
