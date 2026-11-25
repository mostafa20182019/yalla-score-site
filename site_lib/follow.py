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
MY_BOOT = ("<script>try{var t=localStorage.getItem('elgoonTeam'),o=false;"
           "try{o=sessionStorage.getItem('elgoonPickOff')==='1'}catch(e){}"
           "document.documentElement.classList.add(/^[a-z0-9-]{2,40}$/.test(t||'')&&t!=='none'?'my-has':"
           "o?'my-off':'my-ask');}catch(e){}</script>")


def my_pick_html():
    chips = "".join(f'<button type="button" class="mp-c" data-slug="{esc(tp["slug"])}">{esc(tp["name"])}</button>'
                    for tp in TEAM_PAGES if not tp.get("league_page"))   # the picker stays short (2026-11-20)
    return ('<div id="myPick" class="my-pick" hidden>'
            '<b class="mp-t">⭐ اختر فريقك</b>'
            '<button type="button" class="mp-x" data-my-no aria-label="إخفاء اختيار الفريق">×</button>'
            f'<div class="mp-list">{chips}</div>'
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
            + '<button type="button" class="my-x" data-my-x aria-label="تغيير الفريق">تغيير</button>'
            '</div>'
            + (f'<div class="mlist">{row}</div>' if row else "")
            + (f'<a class="my-n" href="{esc(first["href"])}">{esc(first["title"])}</a>' if first else "")
            + (f'<a class="my-calc" href="{esc(calc["href"])}">{esc(calc["label"])} ←</a>' if calc else "")
            + '</section>')


def my_json(html):
    return json.dumps({"html": html}, ensure_ascii=False)
