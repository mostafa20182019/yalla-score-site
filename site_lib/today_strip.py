"""«مباريات اليوم» inside every article (2026-10-18).

The first automatic visitor reading said 1.18 pages per visit: a reader lands
on a story from Facebook, reads it and leaves. Under the body every article
now carries today's matches - live first, the curated clubs next, then the
rest by competition order and kick-off - each a link to its match page. The
rows reuse the ticker's contract so LIVE_JS paints the live score seconds
after load (`data-lv` + `data-h`/`data-a`, a `.tk-mid` holding a `tk-s`
pill): no second script, no baked live score (user rule 2026-08-31).
"""
from site_lib.competitions import COMP_ORDER
from site_lib.config import REF_TODAY
from site_lib.crests import local_crest
from site_lib.matchdata import score_pill
from site_lib.names import _is_ticker_team, ar_team, comp_label
from site_lib.text import esc
from site_lib.urls import match_url

LIMIT = 8


def _rank(m):
    comp = m.get("competition") or ""
    order = COMP_ORDER.index(comp) if comp in COMP_ORDER else len(COMP_ORDER)
    live = 0 if (m.get("status") or "") == "LIVE" else 1
    curated = 0 if _is_ticker_team(m) else 1
    return (live, curated, order, m.get("koff_time") or "99:99", ar_team(m.get("home") or ""))


def pick_today(matches, today=None, limit=LIMIT):
    """Today's matches worth a row: live first, curated clubs next, the rest
    by competition order and kick-off; postponed ones left out."""
    today = today or REF_TODAY
    todays = [m for m in (matches or [])
              if m.get("kickoff") == today and m.get("match_id")
              and (m.get("status") or "") != "POSTPONED"
              and m.get("home") and m.get("away")]
    return sorted(todays, key=_rank)[:limit]


def today_strip(matches, today=None, limit=LIMIT):
    """The section's HTML, or "" when nothing plays today."""
    rows = pick_today(matches, today, limit)
    if not rows:
        return ""
    its = []
    for m in rows:
        st = (m.get("status") or "").upper()
        h, a = ar_team(m.get("home")), ar_team(m.get("away"))
        hb = (f'<img class="tk-b" src="{esc(local_crest(m["home_badge"]))}" alt="" loading="lazy" width="22" height="22">'
              if m.get("home_badge") else "")
        ab = (f'<img class="tk-b" src="{esc(local_crest(m["away_badge"]))}" alt="" loading="lazy" width="22" height="22">'
              if m.get("away_badge") else "")
        if st == "LIVE":
            mid = score_pill(None, None, "tk-s tk-live") + '<span class="tk-dot"></span>'
        elif st == "FINISHED":
            mid = score_pill(m.get("home_score"), m.get("away_score"), "tk-s")
        else:
            mid = f'<span class="tk-t">{esc(m.get("koff_time") or "")}</span>'
        cls = "ts-item tk-item" + (" ts-live" if st == "LIVE" else " ts-fin" if st == "FINISHED" else "")
        its.append(
            f'<a class="{cls}" href="{esc(match_url(m))}" data-lv data-h="{esc(h)}" data-a="{esc(a)}">'
            f'<span class="ts-comp">{esc(comp_label(m.get("competition") or ""))}</span>'
            f'<span class="ts-teams">{hb}<bdi>{esc(h)}</bdi> <span class="tk-mid">{mid}</span> <bdi>{esc(a)}</bdi>{ab}</span>'
            f'</a>')
    return ('<section class="ts" aria-label="مباريات اليوم">'
            '<div class="ts-h"><h2>⚽ مباريات اليوم</h2><a class="ts-all" href="/matches.html">كل المباريات ←</a></div>'
            f'<div class="ts-row">{"".join(its)}</div></section>')
