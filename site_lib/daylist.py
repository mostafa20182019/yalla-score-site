"""The per-day match list: /matches AND the home page (2026-10-26).

The user, on the phone home page: «الصفحة الرئيسية ... تجيب كل المباريات زى
ما كانت صفحة المباريات بتجيب بالظبط، ويكون فيه فلترز زى اللى كانت موجودة فى
صفحة المباريات». So the day sections are built here once and rendered by the
same partial (site_src/templates/_days.html) on both pages, and the same
MATCHES_JS drives the day arrows and the filters on both.
"""
from collections import OrderedDict

from site_lib.competitions import COMP_ORDER, COMP_TV
from site_lib.crests import comp_icon
from site_lib.dates import fmt_day
from site_lib.matchdata import match_goals
from site_lib.names import comp_label
from site_lib.render import Markup
from site_lib.tables import match_row
from site_lib.text import esc
from site_lib.urls import match_url


def day_sections(matches, ge_idx):
    """[{day, heading, comps: [{comp, label, icon, rows}]}] for every day in
    the feed, leagues in the sidebar order, plus the raw row HTML (the
    matches page hands it to pred_pop)."""
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
            block = {"comp": comp, "label": comp_label(comp), "rows": []}
            if comp:
                block["icon"] = Markup(comp_icon(comp))
            for m in ms:
                row = match_row(m, show_time=True, show_comp=False,
                                goals=match_goals(ge_idx, m),
                                link=match_url(m))
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
