# -*- coding: utf-8 -*-
"""«توقّع وشارك» (user, 2026-11-25: «زرار جنب زرار الكاميرا اسمه توقع وشارك،
يدخل يتوقع الجولة ويشارك»). The button on a league heading of the day list
opens a sheet: the reader taps a winner (or the draw) for each match and gets
ONE image of his picks with our name on it (snippets/shot_js.html).

What he picks:
  * a league with numbered rounds -> the nearest round that still has open
    matches, from /pick/<slug>.json (written here, from the season's fixtures);
  * any other competition (a cup, the national teams) -> the open matches of
    that day, read from the rows on screen. Nothing is written for those.

Nothing is predicted by us and nothing reaches a server: the picks live in the
reader's browser. set_pick_rounds() is called once in build(), before any page
with a day list is built."""
import json
import os

from site_lib.calc import _CLOSED
from site_lib.competitions import COMP_SLUG
from site_lib.config import DIST
from site_lib.crests import local_crest
from site_lib.dates import day_month
from site_lib.names import ar_team

MIN_MATCHES = 2
_PAGES = {}         # competition -> {"slug", "rounds": [(n, {match ids}, {(home, away)})]}
_ROUNDS = {}        # competition -> {"slug", "r", "ids": {match ids}, "pairs": {(home, away)}}


def is_open(m):
    """A match the reader can still call: not played, not being played."""
    return (m.get("status") or "").upper() not in _CLOSED + ("POSTPONED",) and m.get("home_score") is None


def pick_round(fx):
    """{"r": n, "m": [{id, h, a, hc, ac, w}]} - the nearest numbered round
    with at least MIN_MATCHES open matches - or None."""
    rounds = [rd for rd in (fx or {}).get("rounds") or []
              if not rd.get("label") and isinstance(rd.get("round"), int)]
    for rd in sorted(rounds, key=lambda x: x["round"]):
        ms = []
        for m in rd.get("matches") or []:
            if not is_open(m) or not m.get("home") or not m.get("away") or not m.get("match_id"):
                continue
            when = (day_month(m.get("kickoff"), weekday=True) + (f" · {m['koff_time']}" if m.get("koff_time") else "")
                    if m.get("kickoff") else "")
            ms.append({"id": str(m["match_id"]), "h": ar_team(m["home"]), "a": ar_team(m["away"]),
                       "hc": local_crest(m["home_badge"]) if m.get("home_badge") else "",
                       "ac": local_crest(m["away_badge"]) if m.get("away_badge") else "", "w": when})
        if len(ms) >= MIN_MATCHES:
            return {"r": rd["round"], "m": ms}
    return None


def set_pick_rounds(fx_by_comp, write=True, st_by_comp=None):
    """Register every league's round and write /pick/<slug>.json. Returns the
    number of leagues.

    st_by_comp (user, 2026-11-25: «يفتحله صفحة التوقعات... ويشوف الجدول وهوه
    متغير بعد توقعاته»): a league whose round is the one its /calc/<slug> page
    opens on sends the button THERE - the picks, the table after them and an
    image of each, on a page he can come back to and edit. calc_data() is the
    same test calc_pages() writes the page by, so the link never dangles."""
    from site_lib.calc import calc_data
    _ROUNDS.clear()
    _PAGES.clear()
    # every league with a predictions page, whatever round it opens on (the
    # Saudi page opens on a postponed match of round 8 while the league plays
    # round 13 - user, 2026-11-25: «السعودى بيفتح البوب اب»): each of its
    # rounds, so a day's heading links to the round that day belongs to
    for comp, slug in COMP_SLUG.items():
        cd = calc_data((st_by_comp or {}).get(comp), (fx_by_comp or {}).get(comp))
        if cd:
            _PAGES[comp] = {"slug": slug, "rounds": [
                (r["r"], {x[0] for x in r["m"]},
                 {(cd["teams"][x[1]]["n"], cd["teams"][x[2]]["n"]) for x in r["m"]}) for r in cd["rounds"]]}
    if write:
        os.makedirs(os.path.join(DIST, "pick"), exist_ok=True)
    for comp, slug in COMP_SLUG.items():
        rd = pick_round((fx_by_comp or {}).get(comp))
        if not rd:
            continue
        _ROUNDS[comp] = {"slug": slug, "r": rd["r"], "ids": {m["id"] for m in rd["m"]},
                         # the day list and the fixtures file do not always share an id
                         "pairs": {(m["h"], m["a"]) for m in rd["m"]}}
        if write:
            from site_lib.shell import write_text
            write_text(f"pick/{slug}.json", json.dumps(rd, ensure_ascii=False, separators=(",", ":")))
    return len(_ROUNDS)


def pick_door(comp, day_matches):
    """What the day list's heading needs for ONE league on ONE day:
    None = no button (nothing open that day); "" = the button, on that day's
    own rows; a slug = the button, on the league's round - only when one of
    that day's open matches belongs to the round, so the sheet never opens on
    a round the reader is not looking at."""
    opened = [m for m in day_matches if is_open(m)]
    if not comp or not opened:
        return None
    rd = _ROUNDS.get(comp)
    if rd and any(str(m.get("match_id")) in rd["ids"]
                  or (ar_team(m.get("home") or ""), ar_team(m.get("away") or "")) in rd["pairs"] for m in opened):
        return rd["slug"]
    return ""


def pick_page(comp, day_matches=()):
    """The league's predictions page, opened on the round one of that day's
    open matches belongs to ("/calc/<slug>.html#r=13"; no round found = the
    page as it opens), or "" when the league has no page - the sheet opens
    instead (a cup, the national teams, a league without a table)."""
    pg = _PAGES.get(comp)
    if not pg:
        return ""
    for m in day_matches:
        if not is_open(m):
            continue
        pair = (ar_team(m.get("home") or ""), ar_team(m.get("away") or ""))
        for n, ids, pairs in pg["rounds"]:
            if str(m.get("match_id")) in ids or pair in pairs:
                return f'/calc/{pg["slug"]}.html#r={n}'
    # nothing open that day (today's matches have started): the round the
    # league plays next, when the page has it
    nxt = (_ROUNDS.get(comp) or {}).get("r")
    if nxt in [n for n, _i, _p in pg["rounds"]]:
        return f'/calc/{pg["slug"]}.html#r={nxt}'
    return f'/calc/{pg["slug"]}.html'
