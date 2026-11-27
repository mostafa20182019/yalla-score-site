# -*- coding: utf-8 -*-
"""What /tv shows: the channel of each match of today and tomorrow.

The page is a table the data already holds, said in one place (SEO review
2026-11-26; user 2026-11-27: «اعمل صفحة القنوات الناقلة»): the kick-off in
Cairo and Mecca time, the two sides, the channel. The channel is the one the
match's own feed names (matches.json `channel`, written by tv_feed.py) and,
where the feed names none, the competition's VERIFIED broadcaster
(competitions.COMP_TV through match_tv). A match with neither says «لم تُعلن
بعد» - a channel is never guessed.

Pure functions; site_pages/tv.py writes the page.
"""
import datetime
from zoneinfo import ZoneInfo

from site_lib.competitions import COMP_ORDER, match_tv
from site_lib.names import _is_ticker_team, ar_team_in, comp_label

CAIRO = ZoneInfo("Africa/Cairo")
MECCA = ZoneInfo("Asia/Riyadh")
NOT_YET = "لم تُعلن بعد"
INDEX_MIN = 3            # a day with fewer named channels than this is not a guide: built, not indexed
FAQ_MAX = 4


def cairo_today(now=None):
    return (now or datetime.datetime.now(CAIRO)).astimezone(CAIRO).date()


def channel_of(m):
    """The channel to print for one match, or '' when none is verified."""
    return (m.get("channel") or "").strip() or match_tv(m) or ""


def _times(m):
    """('18:00', '19:00') - Cairo and Mecca - or ('', '') without a time."""
    t = (m.get("koff_time") or "").strip()
    try:
        d = datetime.date.fromisoformat(str(m.get("kickoff") or "")[:10])
        hh, mm = (int(x) for x in t.split(":")[:2])
    except (TypeError, ValueError):
        return "", ""
    ko = datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=CAIRO)
    return ko.strftime("%H:%M"), ko.astimezone(MECCA).strftime("%H:%M")


def _state(m):
    st = (m.get("status") or "").upper()
    return {"FINISHED": "انتهت", "LIVE": "جارية الآن"}.get(st, "")


def day_rows(matches, day):
    """The matches of `day` (YYYY-MM-DD), one dict a match, by the clock."""
    rows = []
    for m in matches or []:
        if str(m.get("kickoff") or "")[:10] != day or not m.get("match_id"):
            continue
        if (m.get("status") or "").upper() in ("POSTPONED", "CANCELLED", "CANCELED"):
            continue
        comp = m.get("competition") or ""
        cairo, mecca = _times(m)
        rows.append({"id": str(m["match_id"]), "comp": comp, "comp_label": comp_label(comp),
                     "home": ar_team_in(m.get("home"), comp), "away": ar_team_in(m.get("away"), comp),
                     "cairo": cairo, "mecca": mecca, "channel": channel_of(m), "state": _state(m),
                     "ours": bool(_is_ticker_team(m)), "upcoming": (m.get("status") or "").upper() == "UPCOMING"})
    rows.sort(key=lambda r: (r["cairo"] or "99:99", r["comp_label"], r["home"]))
    return rows


def by_competition(rows):
    """[(label, [row])] - the site's own order of competitions, then the
    earliest kick-off."""
    groups = {}
    for r in rows:
        groups.setdefault(r["comp"], []).append(r)

    def key(item):
        comp, rs = item
        return (COMP_ORDER.index(comp) if comp in COMP_ORDER else len(COMP_ORDER), rs[0]["cairo"] or "99:99")
    return [(rs[0]["comp_label"], rs) for _, rs in sorted(groups.items(), key=key)]


def named(rows):
    return [r for r in rows if r["channel"]]


def faq(rows):
    """[(question, answer)] for the matches still to play whose channel is
    named - ours first, then by the clock; FAQ_MAX at most."""
    pick = sorted((r for r in rows if r["upcoming"] and r["channel"] and r["cairo"]),
                  key=lambda r: (not r["ours"], r["cairo"]))[:FAQ_MAX]
    return [(f"ما القناة الناقلة لمباراة {r['home']} و{r['away']} اليوم؟",
             f"تُنقل مباراة {r['home']} و{r['away']} اليوم الساعة {r['cairo']} بتوقيت القاهرة "
             f"({r['mecca']} بتوقيت مكة المكرمة) على {r['channel']}.") for r in pick]
