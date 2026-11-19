# -*- coding: utf-8 -*-
"""«تابع فريقك» (2026-11-19, the user's ask after the fourth AdSense answer:
«محتوى يخلى المستخدم يرجعلك تانى»): a visitor picks ONE club and the home
page opens with it.

Nothing is stored with us: the choice lives in the visitor's browser
(snippets/follow_js.html, localStorage). The build only prepares what that
script shows:

  my_pick_html()   the home page's one-line picker (hidden until the script
                   finds a browser that follows nobody)
  my_block_html()  one club's block - next match, last result, two news rows -
                   written by the club builder to /my/<slug>.json, from the
                   very rows its /team/<slug> page prints (so it can never
                   say something the club page does not)
"""
import json

from site_lib.clubs import TEAM_PAGES
from site_lib.text import esc


def my_pick_html():
    chips = "".join(f'<button type="button" class="mp-c" data-slug="{esc(tp["slug"])}">{esc(tp["name"])}</button>'
                    for tp in TEAM_PAGES)
    return ('<div id="myPick" class="my-pick" hidden>'
            '<b class="mp-t">⭐ اختر فريقك</b>'
            f'<div class="mp-list">{chips}</div>'
            '<button type="button" class="mp-x" data-my-no aria-label="إخفاء اختيار الفريق">×</button>'
            '</div>')


def my_block_html(name, slug, crest, position, up_row, last_row, news):
    """The followed club's block. up_row / last_row = the club page's own
    match rows (HTML) or ""; news = [{"href", "title"}, ...] (two are shown)."""
    img = (f'<img class="my-crest" src="{esc(crest)}" alt="" width="32" height="32">' if crest else "")
    rows = "".join(x for x in (up_row, last_row) if x)
    items = "".join(f'<a class="my-n" href="{esc(n["href"])}">{esc(n["title"])}</a>' for n in news[:2])
    return ('<section class="minfo my-box">'
            f'<h2 class="my-h">{img}<span>فريقك: {esc(name)}</span>'
            f'<a class="my-more" href="/team/{esc(slug)}.html">صفحة {esc(name)} ←</a></h2>'
            + (position or "")
            + (f'<div class="mlist">{rows}</div>' if rows else "")
            + (f'<div class="my-news">{items}</div>' if items else "")
            + '<button type="button" class="my-x" data-my-x>تغيير الفريق</button>'
            '</section>')


def my_json(html):
    return json.dumps({"html": html}, ensure_ascii=False)
