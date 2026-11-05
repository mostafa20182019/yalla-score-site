"""The per-day match list: /matches AND the home page (2026-10-26).

The user, on the phone home page: «الصفحة الرئيسية ... تجيب كل المباريات زى
ما كانت صفحة المباريات بتجيب بالظبط، ويكون فيه فلترز زى اللى كانت موجودة فى
صفحة المباريات». So the day sections are built here once and rendered by the
same partial (site_src/templates/_days.html) on both pages, and the same
MATCHES_JS drives the day arrows and the filters on both.
"""
from collections import OrderedDict
import os

from site_lib.competitions import COMP_ORDER, COMP_SLUG, COMP_TV
from site_lib.crests import comp_icon
from site_lib.dates import fmt_day
from site_lib.matchdata import match_goals
from site_lib.media import highlight_links
from site_lib.names import comp_label
from site_lib.render import Markup
from site_lib.tables import match_row
from site_lib.text import esc
from site_lib.urls import match_url

# how many days either side of today ship INLINE in /matches and the home
# page; every other day is a fragment at /matches/d/<date> that MATCHES_JS
# fetches when the reader steps to it (2026-11-05: the 19-day feed inline was
# 344 KB of markup on both pages, 18 of them hidden by the navigator)
INLINE_SPAN = 2


def comp_hrefs(with_table, with_rounds):
    """{competition: its own page} for the league headings of the day list
    (user, 2026-10-31: «الدوري المصري» above its matches opens the league).
    Same rule as /leagues: the table (/standings) when it has one, otherwise
    the season's fixtures (/fixtures), otherwise no link - never a dead one."""
    out = {}
    for comp, slug in COMP_SLUG.items():
        if comp in with_table:
            out[comp] = f"/standings/{slug}.html"
        elif comp in with_rounds:
            out[comp] = f"/fixtures/{slug}.html"
    return out


def day_sections(matches, ge_idx, hrefs=None):
    """[{day, heading, comps: [{comp, label, icon, href, rows}]}] for every day
    in the feed, leagues in the sidebar order, plus the raw row HTML (the
    matches page hands it to pred_pop). hrefs = comp_hrefs(...)."""
    hrefs = hrefs or {}
    hls = highlight_links()     # the «الأهداف» button (2026-11-02)
    daymap = OrderedDict()
    for m in matches:
        daymap.setdefault(m.get("kickoff") or "", []).append(m)
    days, pieces = [], []
    for d in sorted(k for k in daymap.keys() if k):
        day = {"day": d, "heading": fmt_day(d), "comps": []}
        comps = OrderedDict()
        for m in daymap[d]:
            comps.setdefault(m.get("competition") or "", []).append(m)
        # same fixed league order as the sidebar
        for comp, ms in sorted(comps.items(),
                               key=lambda kv: (COMP_ORDER.index(kv[0])
                                               if kv[0] in COMP_ORDER
                                               else len(COMP_ORDER), kv[0])):
            block = {"comp": comp, "label": comp_label(comp), "href": hrefs.get(comp, ""), "rows": []}
            if comp:
                block["icon"] = Markup(comp_icon(comp))
            for m in ms:
                row = match_row(m, show_time=True, show_comp=False,
                                goals=match_goals(ge_idx, m),
                                link=match_url(m), card_link=False,
                                highlight=hls.get(str(m.get("match_id"))))
                # filter hooks: "على التلفزيون" = a known broadcaster (per-match
                # channel or the verified COMP_TV map); "حسب الوقت" sorts by data-ko
                tv = "1" if (m.get("channel") or COMP_TV.get(comp)) else "0"
                row = row.replace('<div class="mrow ',
                                  f'<div data-tv="{tv}" data-ko="{esc(m.get("koff_time") or "")}" class="mrow ', 1)
                block["rows"].append(Markup(row))
                pieces.append(row)
            day["comps"].append(block)
        days.append(day)
    return days, pieces


def inline_days(days, today):
    """(the day sections to inline, every day key) for _days.html: today and
    INLINE_SPAN days either side of it - the arrows reach the rest through
    the fragments. `today` absent from the feed: the window centres on the
    first day at or after it (same rule as MATCHES_JS's first pick)."""
    keys = [d["day"] for d in days]
    if not keys:
        return [], []
    idx = next((i for i, k in enumerate(keys) if k >= today), len(keys) - 1)
    lo, hi = max(0, idx - INLINE_SPAN), idx + INLINE_SPAN
    return [d for i, d in enumerate(days) if lo <= i <= hi], keys


def write_day_fragments(days):
    """One file per day at dist/matches/d/<date>.html: the <section> of
    _day.html and nothing else (no <html>, no head - a fragment, not a page;
    root-extras/_headers marks the folder noindex). Written for EVERY day,
    the inlined ones too, so the loader never depends on the window."""
    from site_lib.config import DIST
    from site_lib.render import render
    from site_lib.shell import write
    os.makedirs(os.path.join(DIST, "matches", "d"), exist_ok=True)
    for d in days:
        write(f"matches/d/{d['day']}.html", render("_day.html", d=d))
    return len(days)
