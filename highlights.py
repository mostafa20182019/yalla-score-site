#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/highlights.json - match highlight videos from the rights holders'
own YouTube channels, for /goals («أهداف المباريات»).

    python highlights.py            # fetch, match, store (fetch_data runs it)
    python highlights.py --show     # what the store holds, newest first

User, 2026-11-02: «عايزك تعمل صفحة اسمها أهداف المباريات هتحط فيها لينكات
متجابة من اليوتيوب اما من حساب bein sports or on sport ... bein sport هتجيب
منها لينكات الماتشات الاوروبية اما on sport هتجيب منها لينكات الماتشات
المصرية». LINKS to the channels' own uploads - nothing is downloaded or
re-hosted (the reel rule: no broadcast footage of ours, ever).

Sources, per channel:
  * the channel's RSS (youtube.com/feeds/videos.xml) - official, keyless, the
    15 newest uploads. Read on every fetch run (~30 min), so a highlight is
    caught while it is still among the 15 even on ON Sport, which uploads
    talk-show clips by the dozen.
  * the channel's own search page («ملخص مباراة» / «أهداف مباراة»), at most
    every SEARCH_EVERY_H: catches what fell out of the 15 between two runs
    and filled the first week. HTML scraping - any failure is ignored.

A video is kept only when it is a highlight («ملخص مباراة» / «أهداف مباراة»
in the title) AND both clubs in its title are a FINISHED match of ours in the
channel's scope, played in the days before the upload. So talk shows, basket-
ball, handball and other channels' leagues never reach the page, and every
card can carry our score, crests and a link to our match page.
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FILE = os.path.join(HERE, "data", "highlights.json")

EUROPE = {"Premier League", "Primera Division", "Serie A", "Bundesliga", "Ligue 1",
          "UEFA Champions League", "UEFA Europa League", "Turkish Super Lig"}
EGYPT = {"Egyptian Premier League", "CAF Champions League", "CAF Confederation Cup"}
CHANNELS = [
    {"key": "bein", "name": "beIN SPORTS", "id": "UCJUCcJUeh0Cz2xyKwkw5Q1w",
     "handle": "@beINSPORTS", "scope": EUROPE, "search": "ملخص مباراة"},
    {"key": "on", "name": "ON Sport", "id": "UCo2TvjBHS1BtyIkeGGTMe6w",
     "handle": "@ONSportEG", "scope": EGYPT, "search": "أهداف مباراة"},
]
HIGHLIGHT = ("ملخص مباراة", "أهداف مباراة", "اهداف مباراة", "ملخص وأهداف مباراة")
SEARCH_EVERY_H = 6
MATCH_DAYS = 4          # an upload is about a match played in the 4 days before it
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


# ------------------------------------------------------------------ names
_DIAC = re.compile(r"[ً-ْـ]")       # harakat + tatweel


def norm(s):
    """Arabic folded for matching: no diacritics, one alef, ة→ه, ى→ي."""
    s = _DIAC.sub("", s or "")
    # غ/ج: the foreign G is written both ways («راسينغ» on beIN, «راسينج» ours)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("غ", "ج")):
        s = s.replace(a, b)
    return s


def tokens(s):
    """The words of s, folded. A word glued to the conjunction و also counts
    without it: beIN writes «تشيلسي ومانشستر يونايتد»."""
    out = []
    for t in re.split(r"[^\w]+", norm(s)):
        if t:
            out.append(t)
            if t.startswith("و") and len(t) > 3:
                out.append(t[1:])
    return out


# words that name no club on their own: «سبور» is in half the Turkish league
# (the first run tied three different Turkish highlights to آمد سبور - أيوب
# سبور through it), «اف سي» trails «زد اف سي»
GENERIC = {"سبور", "اف", "سي", "fc", "sc", "نادي", "club"}


def _tok_hit(t, title_tokens):
    """The token itself, or - in a long token only - the same letters with two
    swapped («كليوباترا» / «كيلوباترا»). Nothing looser: one changed letter
    already turns one club into another."""
    if t in title_tokens:
        return True
    return len(t) >= 7 and any(len(x) == len(t) and sorted(x) == sorted(t)
                               and sum(a != b for a, b in zip(x, t)) == 2 for x in title_tokens)


def club_key(team):
    """A club's distinctive words, as a set (GENERIC words dropped)."""
    return frozenset([t for t in tokens(team) if t not in GENERIC] or tokens(team))


def team_hits(team, title_tokens, clubs=()):
    """How strongly the title names our club, 0 = not at all. `clubs` = every
    club's club_key in the pool: the clubs whose names nest («الأهلي» inside
    «البنك الأهلي») are told apart through it.
    Every distinctive token of our name = 2 per token (the full name; the title
    may say more: «ديبورتيفو ألافيس» names our «ألافيس») - unless a LONGER
    club containing our whole name is named too: then the title is about that
    club («البنك الأهلي - المصري» does not name الأهلي). Only the LONGEST token
    of a longer name = 1 (beIN's short names: «توتنهام» for our «توتنهام
    هوتسبر»); never a shorter one («ريال بيتيس» does not name «ريال مدريد»), and
    never a token that is itself a whole club («الأهلي» does not name «البنك
    الأهلي»)."""
    mine = club_key(team)
    if not mine:
        return 0
    if all(_tok_hit(t, title_tokens) for t in mine):
        if any(mine < c and all(_tok_hit(t, title_tokens) for t in c) for c in clubs):
            return 0
        return 2 * len(mine)
    longest = max(mine, key=len)
    if (len(mine) >= 2 and len(longest) >= 5 and _tok_hit(longest, title_tokens)
            and frozenset([longest]) not in clubs):
        return 1
    return 0


def title_score(title):
    """The score a title states («| 2/1 |», «1 - 2»), as a sorted pair, or None.
    ON Sport writes it, beIN does not."""
    m = re.search(r"(?<![\d/])(\d{1,2})\s*[-/]\s*(\d{1,2})(?![\d/])", title or "")
    return tuple(sorted((int(m.group(1)), int(m.group(2))))) if m else None


def is_highlight(title):
    t = norm(title)
    return any(norm(h) in t for h in HIGHLIGHT)


# ------------------------------------------------------------------ fetching
def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def rss(ch):
    """[(video_id, title, published ISO)] - the channel's 15 newest uploads."""
    root = ET.fromstring(_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"))
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", "", NS)
        if vid:
            out.append((vid, e.findtext("a:title", "", NS), e.findtext("a:published", "", NS)))
    return out


def search(ch):
    """[(video_id, title, None)] from the channel's search page (no exact date:
    the page only says «قبل يومين»)."""
    q = urllib.parse.quote(ch["search"])
    h = _get(f"https://www.youtube.com/{ch['handle']}/search?query={q}")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", h, re.S)
    if not m:
        return []
    out = []

    def walk(x):
        if isinstance(x, dict):
            v = x.get("videoRenderer")
            if v and v.get("videoId"):
                t = "".join(r.get("text", "") for r in (v.get("title") or {}).get("runs", []))
                out.append((v["videoId"], t, None))
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(json.loads(m.group(1)))
    return out


# ------------------------------------------------------------------ matching
def finished_pool():
    """Our finished matches, Arabic names, newest copy per id."""
    import build_site as b
    seen = {}
    for m in b.load("matches_archive.json") + b.load("matches.json"):
        if (m.get("status") or "").upper() == "FINISHED" and m.get("match_id"):
            seen[str(m["match_id"])] = m
    out = []
    for m in seen.values():
        out.append(dict(m, ar_home=b.ar_team(m.get("home")), ar_away=b.ar_team(m.get("away"))))
    return out


def match_for(title, published, scope, pool, now=None):
    """The finished match of ours this highlight is about, or None: both clubs
    named in the title, in the channel's scope, played in the MATCH_DAYS before
    the upload (or the last 21 days when the upload date is unknown), and - when
    the title states a score - that score. Of several candidates, the one whose
    names cover more of the title wins («البنك الأهلي - المصري» is that match,
    not الأهلي - المصري), then the most recent."""
    tt = set(tokens(title))
    said = title_score(title)
    now = now or datetime.now(timezone.utc)
    try:
        up = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
    except ValueError:
        up = None
    hi = (up or now).date().isoformat()
    lo = ((up - timedelta(days=MATCH_DAYS)) if up else (now - timedelta(days=21))).date().isoformat()
    clubs = {club_key(n) for x in pool for n in (x["ar_home"], x["ar_away"])}
    best, best_key = None, None
    for m in pool:
        if m.get("competition") not in scope or not (lo <= (m.get("kickoff") or "") <= hi):
            continue
        h, a = team_hits(m["ar_home"], tt, clubs), team_hits(m["ar_away"], tt, clubs)
        if not (h and a):
            continue
        if said and said != tuple(sorted((m.get("home_score") or 0, m.get("away_score") or 0))):
            continue
        key = (h + a, m.get("kickoff") or "")
        if best_key is None or key > best_key:
            best, best_key = m, key
    return best


def entry(ch, vid, title, published, m):
    return {"vid": vid, "ch": ch["key"], "channel": ch["name"], "title": title,
            "published": published or "", "match_id": str(m["match_id"]),
            "competition": m.get("competition"), "kickoff": m.get("kickoff"),
            "home": m["ar_home"], "away": m["ar_away"],
            "home_score": m.get("home_score"), "away_score": m.get("away_score"),
            "home_badge": m.get("home_badge"), "away_badge": m.get("away_badge"),
            "found": datetime.now(timezone.utc).isoformat(timespec="seconds")}


# ------------------------------------------------------------------ store
def load(path=FILE):
    try:
        with io.open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}, {}
    return {e["vid"]: e for e in doc.get("results") or [] if e.get("vid")}, doc.get("meta") or {}


def save(store, meta, path=FILE):
    rows = sorted(store.values(), key=lambda e: (e.get("kickoff") or "", e.get("published") or ""),
                  reverse=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": rows}, f, ensure_ascii=False, indent=0)


def run(now=None):
    """Fetch both channels, keep the highlights that name a match of ours.
    Returns a one-line note for fetch_debug.json. Never raises."""
    now = now or datetime.now(timezone.utc)
    store, meta = load()
    pool = finished_pool()
    due = True
    try:
        last = datetime.fromisoformat(meta.get("searched_at") or "")
        due = (now - last).total_seconds() >= SEARCH_EVERY_H * 3600
    except ValueError:
        pass
    added, notes = 0, []
    for ch in CHANNELS:
        vids = []
        try:
            vids += rss(ch)
        except Exception as e:                              # noqa: BLE001
            notes.append(f"{ch['key']} rss FAIL {str(e)[:60]}")
        if due:
            try:
                time.sleep(1)
                vids += search(ch)
            except Exception as e:                          # noqa: BLE001
                notes.append(f"{ch['key']} search FAIL {str(e)[:60]}")
        n_ch = 0
        for vid, title, published in vids:
            if vid in store or not is_highlight(title):
                continue
            m = match_for(title, published, ch["scope"], pool, now)
            if m:
                store[vid] = entry(ch, vid, title, published, m)
                added += 1
                n_ch += 1
        notes.append(f"{ch['key']} {len(vids)} read +{n_ch}")
    if due:
        meta["searched_at"] = now.isoformat(timespec="seconds")
    meta["updated"] = now.isoformat(timespec="seconds")
    save(store, meta)
    note = f"{len(store)} stored, +{added} new ({'; '.join(notes)})"
    print(f"highlights: {note}")
    return note


def show():
    store, meta = load()
    for e in sorted(store.values(), key=lambda e: e.get("kickoff") or "", reverse=True)[:40]:
        print(e["kickoff"], e["channel"], f'{e["home"]} {e["home_score"]}-{e["away_score"]} {e["away"]}',
              "|", e["title"][:70])
    print(f"{len(store)} stored; meta {meta}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    sys.exit(show() if a.show else (run() and 0))
