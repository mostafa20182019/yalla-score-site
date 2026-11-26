# -*- coding: utf-8 -*-
"""«تابع فريقك» (2026-11-19, the user's ask after the fourth AdSense answer:
«محتوى يخلى المستخدم يرجعلك تانى»): a visitor picks ONE club and the home
page opens with it.

Nothing is stored with us: the choice lives in the visitor's browser
(snippets/follow_js.html, localStorage). The build only prepares what that
script shows:

  my_pick_html()   the home page's picker (hidden until the script finds a
                   browser that follows nobody)
  my_block_html()  one club's block, written by the club builder to
                   /my/<slug>.json from the very rows its /team/<slug> page
                   prints (so it can never say something the club page does
                   not)
  MY_BOOT          the two lines that run before the first paint, so the
                   block's room is there when the page appears

The block is SMALL on purpose (site review, the same evening: the first one
was 433 px tall and pushed the day's matches off the first screen - the home
page is the matches tab): one header line, ONE match row, one news line.
"""
import json

from site_lib.clubs import TEAM_PAGES
from site_lib.text import esc

# before the first paint: which of the three states this browser is in. The
# CSS keys the picker's / the block's reserved room on it; follow_js keeps it
# in step afterwards. No storage -> no class -> nothing reserved, nothing shown.
# The picker's × is remembered for the VISIT (sessionStorage), not for ever
# (user 2026-11-20); an old 'none' in localStorage counts as no choice.
# 2026-11-26: the row of clubs is the control itself (the followed ones are
# marked on it), so there are two states left - shown, or hidden for the visit.
MY_BOOT = ("<script>try{var o=false;localStorage.getItem('elgoonTeam');"
           "try{o=sessionStorage.getItem('elgoonPickOff')==='1'}catch(e){}"
           "document.documentElement.classList.add(o?'my-off':'my-ask');}catch(e){}</script>")


# the five leagues of the row, in its order (user, 2026-11-26: «نحط هنا اكتر
# خمس دوريات مميزة واليوزر يضغط على الدورى يفتحله popup فيها فرق الدورى ده»);
# every other club page - the national teams, a club of another league - sits
# under the last button
PICK_LEAGUES = (("Egyptian Premier League", "egypt", "الدوري المصري"),
                ("Saudi Pro League", "saudi", "الدوري السعودي"),
                ("Premier League", "england", "الدوري الإنجليزي"),
                ("Primera Division", "spain", "الدوري الإسباني"),
                ("Turkish Super Lig", "turkey", "الدوري التركي"))
PICK_OTHER = ("other", "منتخبات وأندية أخرى")


def pick_groups():
    """[(key, label, [club pages])] - every club page in exactly one group,
    a group with no club left out. Only a club with a page can be followed
    (its page, its matches and its notifications hang on the slug)."""
    own = {lg for lg, _k, _l in PICK_LEAGUES}
    out = [(k, label, [tp for tp in TEAM_PAGES if tp["league"] == lg]) for lg, k, label in PICK_LEAGUES]
    out.append((PICK_OTHER[0], PICK_OTHER[1], [tp for tp in TEAM_PAGES if tp["league"] not in own]))
    return [g for g in out if g[2]]


def my_pick_html():
    groups = pick_groups()
    row = "".join(f'<button type="button" class="mp-lg" data-lg="{k}" aria-haspopup="dialog">{esc(label)}</button>'
                  for k, label, _c in groups)
    lists = "".join(
        f'<div class="mp-grp" data-lg="{k}" data-label="{esc(label)}" hidden>'
        + "".join(f'<button type="button" class="mp-c" data-slug="{esc(tp["slug"])}">{esc(tp["name"])}</button>'
                  for tp in clubs) + '</div>'
        for k, label, clubs in groups)
    return ('<div id="myPick" class="my-pick" hidden>'
            '<b class="mp-t">⭐ اختر فرقك (حتى 4)</b>'
            '<button type="button" class="mp-x" data-my-no aria-label="إخفاء اختيار الفريق">×</button>'
            f'<div class="mp-list">{row}</div>'
            # what following gives (2026-11-26): shown once a club is marked;
            # the bell beside it is push_js's own button, so the line and the
            # real state of the notifications never disagree
            '<p id="myNote" class="mp-note" hidden><span class="mp-note-t">ستصلك إشعارات مباريات هذه الفرق.</span>'
            '<button type="button" class="push-btn follow-push mp-push" hidden aria-pressed="false">'
            '<span class="push-lbl">فعّل الإشعارات</span></button></p>'
            # a league's clubs: one dialog, the tapped league's list shown in it
            '<div id="myDlg" class="pick-box" role="dialog" aria-modal="true" aria-labelledby="myDlgT" hidden>'
            '<div class="pick-in"><div class="pick-hd"><div><h2 id="myDlgT" class="pick-t"></h2>'
            '<p id="myDlgS" class="pick-s"></p></div>'
            '<button type="button" class="pick-x" data-dlg-x aria-label="إغلاق">×</button></div>'
            f'<div class="pick-ls mp-dlg">{lists}</div>'
            '<div class="pick-ft"><span class="pick-n"></span>'
            '<button type="button" class="pick-go" data-dlg-x>تم</button></div></div></div>'
            '</div>')


def my_block_html(name, slug, crest, chip, row, news, calc=None):
    """The followed club's block. chip = a few words on where the club stands
    («المركز 2 · 20 نقطة») or ""; row = ONE of the club page's own match rows
    (HTML: its next match, else its last result) or ""; news = [{"href",
    "title"}, ...] - the first one is shown, on one line."""
    img = (f'<img class="my-crest" src="{esc(crest)}" alt="" width="28" height="28">' if crest else "")
    first = news[0] if news else None
    return ('<section class="minfo my-box">'
            '<div class="my-h">'
            f'<a class="my-name" href="/team/{esc(slug)}.html">{img}<span class="my-lbl">فريقك</span><b>{esc(name)}</b></a>'
            + (f'<span class="my-chip">{esc(chip)}</span>' if chip else "")
            + '<button type="button" class="my-x" data-my-x aria-label="إلغاء متابعة ' + esc(name) + '">إلغاء</button>'
            '</div>'
            + (f'<div class="mlist">{row}</div>' if row else "")
            + (f'<a class="my-n" href="{esc(first["href"])}">{esc(first["title"])}</a>' if first else "")
            + (f'<a class="my-calc" href="{esc(calc["href"])}">{esc(calc["label"])} ←</a>' if calc else "")
            + '</section>')


def my_json(html, ko=""):
    """ko = when the club plays next ("2026-11-28 18:00", "" = nothing
    scheduled): a reader who follows several clubs sees the one that plays
    soonest first (2026-11-26)."""
    return json.dumps({"html": html, "ko": ko}, ensure_ascii=False)
