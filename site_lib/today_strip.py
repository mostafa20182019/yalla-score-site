"""«مباريات اليوم» inside every article (2026-10-18).

The first automatic visitor reading said 1.18 pages per visit: a reader lands
on a story from Facebook, reads it and leaves. Under the body every article
now carries today's matches - live first, the curated clubs next, then the
rest by competition order and kick-off - each a link to its match page. The
rows reuse the ticker's contract so LIVE_JS paints the live score seconds
after load (`data-lv` + `data-h`/`data-a`, a `.tk-mid` holding a `tk-s`
pill): no second script, no baked live score (user rule 2026-08-31).
"""
from site_lib.competitions import COMP_ORDER, COMP_TV
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


# ------------------------------------------------------------ the home cards
# User, 2026-10-22: «اليوزر بيدخل مواقع الكورة ليه؟ ... يشوف مواعيد مباريات ...
# اظهر اهم مباريات اليوم ويكون فيه بطاقة المباراة لما يضغط عليها يجبله معلومات
# المباراة». The home page opens with today's most important matches as
# cards - the same pick as the article strip (live first, the curated clubs,
# then competition order and kick-off), each card the competition, the
# kick-off (or the live score painted by LIVE_JS, or the final score), the
# two clubs with their crests, the TV channel, and a link into the match
# page, which is the «بطاقة المباراة»: lineups, events, the reading, the
# prediction. Nothing live is baked at build time (user rule 2026-08-31).
CARDS = 6


def today_cards(matches, today=None, limit=CARDS, pills=""):
    """The home block's HTML, or "" when nothing plays today. `pills` = the
    follow pills' HTML for the heading row (the top of the home page)."""
    rows = pick_today(matches, today, limit)
    if not rows:
        return ""
    its = []
    for m in rows:
        st = (m.get("status") or "").upper()
        h, a = ar_team(m.get("home")), ar_team(m.get("away"))

        def crest(u):
            return (f'<img src="{esc(local_crest(u))}" alt="" loading="lazy" width="26" height="26">'
                    if u else '<span class="ph">⚽</span>')
        if st == "LIVE":
            when, mid, cls = "مباشر الآن", score_pill(None, None, "tk-s tk-live") + '<span class="tk-dot"></span>', " tc-live"
        elif st == "FINISHED":
            when, mid, cls = "انتهت", score_pill(m.get("home_score"), m.get("away_score"), "tk-s"), " tc-fin"
        else:
            t = m.get("koff_time") or ""
            # the time sits in the middle pill; the top says only «اليوم»
            when, mid, cls = "اليوم", f'<span class="tk-t">{esc(t)}</span>', ""
        tv = m.get("channel") or COMP_TV.get(m.get("competition") or "") or ""
        tv_html = f'<span class="tc-tv">📺 {esc(str(tv))}</span>' if tv else "<span></span>"
        its.append(
            f'<a class="tc-card tk-item{cls}" href="{esc(match_url(m))}" data-lv data-h="{esc(h)}" data-a="{esc(a)}">'
            f'<span class="tc-top"><span class="tc-comp">{esc(comp_label(m.get("competition") or ""))}</span>'
            f'<span class="tc-when">{esc(when)}</span></span>'
            f'<span class="tc-t">{crest(m.get("home_badge"))}<bdi>{esc(h)}</bdi></span>'
            f'<span class="tc-t">{crest(m.get("away_badge"))}<bdi>{esc(a)}</bdi></span>'
            f'<span class="tc-mid tk-mid">{mid}</span>'
            f'<span class="tc-foot">{tv_html}<span class="tc-go">بطاقة المباراة ←</span></span>'
            f'</a>')
    # the heading: «أهم مباريات اليوم» (user, 2026-10-22, after seeing it live)
    return ('<section class="tc" aria-label="أهم مباريات اليوم">'
            '<div class="sec-h"><h2 class="page-h">⚽ أهم مباريات اليوم</h2>'
            f'<span class="tc-side">{pills}</span></div>'
            f'<div class="tc-row">{"".join(its)}</div>'
            '<div class="blk-more"><a class="see-all" href="/matches.html">كل المباريات ←</a></div></section>')


def today_list(matches, today=None, pills=""):
    """The home page on PHONES opens on today's matches, like FotMob's (user,
    2026-10-26: «الموقع يفتح على المباريات»): every match of the day, one
    card per league in the /matches order, one-line rows that open the match
    page. Shown only under 760px (style.css), where it replaces the
    «أهم مباريات اليوم» cards; desktop keeps the cards. Same rows as /matches
    (tables.match_row), so LIVE_JS paints them the same way."""
    from site_lib.crests import comp_icon
    from site_lib.tables import match_row
    today = today or REF_TODAY
    todays = [m for m in (matches or [])
              if m.get("kickoff") == today and m.get("home") and m.get("away")]
    comps = {}
    for m in todays:
        comps.setdefault(m.get("competition") or "", []).append(m)
    blocks = []
    for comp in sorted(comps, key=lambda c: (COMP_ORDER.index(c) if c in COMP_ORDER else len(COMP_ORDER), c)):
        rows = "".join(match_row(m, show_time=True, show_comp=False,
                                 link=match_url(m) if m.get("match_id") else None)
                       for m in sorted(comps[comp], key=lambda m: m.get("koff_time") or "99:99"))
        icon = comp_icon(comp) if comp else ""
        blocks.append(f'<div class="comp"><div class="comp-h">{icon} {esc(comp_label(comp))}</div>'
                      f'<div class="mlist">{rows}</div></div>')
    body = "".join(blocks) or '<p class="ph-none">لا توجد مباريات اليوم.</p>'
    return ('<section class="ph-today" aria-label="مباريات اليوم">'
            '<div class="sec-h"><h2 class="page-h">مباريات اليوم</h2>'
            f'<span class="tc-side">{pills}</span></div>'
            f'{body}'
            '<div class="blk-more"><a class="see-all" href="/matches.html">كل المباريات ←</a></div></section>')
