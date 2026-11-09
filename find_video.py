#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — find REAL football footage we are allowed to post (2026-11-09).

    python find_video.py "Japan Germany World Cup 2022"            # Commons + Internet Archive
    python find_video.py "Al Ahly" "Zamalek" "Egypt football" --out /tmp/vids
    python find_video.py "Munich air disaster" --archive-only

Why (user, 2026-11-09: «متبحث كده في الإنترنت عن فيديوهات ننزلها reels»): the
page may never re-upload broadcast footage — a FIFA remix was blocked by the
rights holder on 11-09 — but three kinds of real video ARE ours to use:
  * fan- or journalist-filmed clips on Wikimedia Commons under CC BY / BY-SA /
    CC0 (the 2022 Japan–Germany celebrations filmed from the stands by a Mehr
    News reporter, Chelsea's 2012 final filmed by a supporter, a Mbappé clip
    from the Bernabéu stands);
  * public-domain archive film on the Internet Archive — Universal Newsreels
    (1929–1967: the 1958 Munich air disaster), Prelinger, VOA;
  * stock clips (Mixkit, Pexels) — generic, for B-roll only.
This tool searches the first two with the licence read from the file page,
and RATES each hit for the one risk a licence does not remove: Facebook's
Rights Manager matching a rights holder's own content. A club's or a
federation's video imported from YouTube under CC BY is legal to reuse and
still gets blocked — rate it «rights-holder», never pick it. «all goals»,
«highlights», «skills» titles are broadcast re-uploads whatever the label says.

Output: a table, and with --out a JSON (title, url, page, licence, author,
seconds, width×height, source kind, risk) to hand to clip_reel.py's spec.
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

UA = {"User-Agent": "elgoon-video-finder/1.0 (https://elgoon.com)"}
COMMONS = "https://commons.wikimedia.org/w/api.php"
ARCHIVE = "https://archive.org/advancedsearch.php"
OK = ("cc by", "cc by-sa", "cc0", "public domain", "pd")
BROADCAST_RE = re.compile(r"\b(all( \d+)? goals|highlights|skills|best goals|top \d+|full match|"
                          r"goal of the week|haftanın en iyi golü|resumen|melhores momentos)\b", re.I)
RIGHTS_HOLDERS = ("fifa", "uefa", "caf ", "premier league", "laliga", "bundesliga", "serie a",
                  "ligue 1", "real madrid", "fc barcelona", "manchester", "liverpool fc", "chelsea fc",
                  "arsenal", "bayern", "juventus", "psg", "al ahly", "zamalek", "bein", "espn", "sky sports",
                  "dazn", "onefootball", "football association", "federation", "federación", "federação")


def get_json(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def licence_ok(s):
    s = (s or "").strip().lower()
    if not s or "-nc" in s or "-nd" in s or " nc" in s or " nd" in s:
        return False
    return any(s == k or s.startswith(k + " ") or s.startswith(k + "-") for k in OK) or s.startswith("cc by")


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def rate(title, author, source_wikitext, description, reviewed=False):
    """('own' | 'fan-import' | 'rights-holder' | 'broadcast?' | 'archive-pd', reason)."""
    t = (title or "").lower()
    a = (author or "").lower()
    d = (description or "").lower()
    src = (source_wikitext or "").lower()
    if BROADCAST_RE.search(t) or BROADCAST_RE.search(d):
        return "broadcast?", "title/description reads like a broadcast compilation"
    if any(h in a for h in RIGHTS_HOLDERS) or any(h in t for h in ("official trailer", "thank you video")):
        return "rights-holder", "the author is a club/federation/broadcaster: legal, but Rights Manager will match it"
    if "{{own" in src or "own work" in src:
        return "own", "uploader's own footage"
    if "flickr" in src:
        return "own", "Flickr photographer's own footage (licence reviewed)"
    if "from youtube" in src or "from vimeo" in src:
        if re.search(r"\bi (filmed|recorded|shot)\b|my (video|footage)|filmed by me", d):
            return "fan-import", "a fan's own YouTube video (says so in the description)"
        return "fan-import", "imported from YouTube/Vimeo: check the channel is a person, not a rights holder"
    if "archive.org" in src or "universal" in a or "newsreel" in t:
        return "archive-pd", "archive film in the public domain"
    if reviewed and src.startswith("[http"):
        return "own", "a news agency's / photographer's own footage, licence reviewed on Commons"
    return "fan-import", "unknown provenance: open the file page before using"


# ---------------------------------------------------------------- Commons
def commons(query, limit):
    q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search", "srnamespace": 6,
                                "srlimit": limit, "srsearch": f"filetype:video {query}"})
    titles = [r["title"] for r in get_json(f"{COMMONS}?{q}").get("query", {}).get("search", [])]
    out = []
    for i in range(0, len(titles), 20):
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": "|".join(titles[i:i + 20]),
                                    "prop": "imageinfo|revisions", "iiprop": "url|size|extmetadata",
                                    "rvprop": "content", "rvslots": "main"})
        for p in (get_json(f"{COMMONS}?{q}").get("query", {}).get("pages", {}) or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {}) or {}
            wt = ((p.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*") or "")
            src = re.search(r"\|\s*[Ss]ource\s*=\s*([^\n]+)", wt)
            lic = em.get("LicenseShortName", {}).get("value", "")
            author = strip_html(em.get("Artist", {}).get("value", ""))[:60]
            desc = strip_html(em.get("ImageDescription", {}).get("value", ""))[:200]
            reviewed = bool(re.search(r"\{\{(License ?Review|YouTubeReview|Flickrreview)", wt, re.I))
            kind, why = rate(p.get("title"), author, src.group(1) if src else wt[:400], desc, reviewed)
            out.append({
                "source": "commons", "title": p.get("title", ""), "url": (ii.get("url") or "").split("?")[0],
                "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(p.get("title", "").replace(" ", "_")),
                "licence": lic, "licence_ok": licence_ok(lic), "author": author,
                "seconds": round(float(ii.get("duration") or 0)), "width": ii.get("width"), "height": ii.get("height"),
                "mb": round((ii.get("size") or 0) / 1e6, 1), "reviewed": reviewed,
                "kind": kind, "risk_note": why, "description": desc,
            })
    return out


# ---------------------------------------------------------------- Internet Archive
def archive(query, limit):
    q = (f'mediatype:movies AND ({query}) AND (collection:universal_newsreels OR collection:prelinger '
         f'OR licenseurl:*publicdomain* OR licenseurl:*creativecommons.org/licenses/by/* OR licenseurl:*by-sa*)')
    u = ARCHIVE + "?" + urllib.parse.urlencode({"q": q, "fl[]": ["identifier", "title", "year", "licenseurl",
                                                                  "description", "collection"],
                                                 "rows": limit, "output": "json", "sort[]": "downloads desc"}, doseq=True)
    out = []
    for d in get_json(u).get("response", {}).get("docs", []):
        lic = d.get("licenseurl") or ""
        coll = d.get("collection") or []
        coll = coll if isinstance(coll, list) else [coll]
        pd = "publicdomain" in lic or "universal_newsreels" in coll or "prelinger" in coll
        out.append({
            "source": "archive.org", "title": str(d.get("title") or ""), "year": d.get("year"),
            "url": f"https://archive.org/download/{d['identifier']}", "page": f"https://archive.org/details/{d['identifier']}",
            "licence": "Public domain" if pd else lic.split("/licenses/")[-1].upper().replace("/", " "),
            "licence_ok": pd or licence_ok("cc " + lic.split("/licenses/")[-1].split("/")[0]) if lic else pd,
            "author": "Universal Newsreel" if "universal_newsreels" in coll else ", ".join(coll[:2]),
            "kind": "archive-pd" if pd else "fan-import", "risk_note": "public-domain archive film" if pd else "CC on archive.org: open the item",
            "description": str(d.get("description") or "")[:200],
        })
    return out


def find(queries, limit=12, commons_on=True, archive_on=True):
    seen, out = set(), []
    for q in queries:
        hits = []
        if commons_on:
            try:
                hits += commons(q, limit)
            except Exception as e:                           # noqa: BLE001
                print(f"  commons failed for {q!r}: {str(e)[:80]}")
        if archive_on:
            try:
                hits += archive(q, limit)
            except Exception as e:                           # noqa: BLE001
                print(f"  archive.org failed for {q!r}: {str(e)[:80]}")
        for h in hits:
            if h["url"] in seen or not h["licence_ok"]:
                continue
            seen.add(h["url"])
            h["query"] = q
            out.append(h)
    order = {"own": 0, "archive-pd": 1, "fan-import": 2, "rights-holder": 3, "broadcast?": 4}
    out.sort(key=lambda h: (order.get(h["kind"], 9), -(h.get("width") or 0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries", nargs="+", help="English search phrases")
    ap.add_argument("--limit", type=int, default=12, help="per query per source")
    ap.add_argument("--out", help="write <out>.json")
    ap.add_argument("--archive-only", action="store_true")
    ap.add_argument("--commons-only", action="store_true")
    args = ap.parse_args()
    hits = find(args.queries, args.limit, commons_on=not args.archive_only, archive_on=not args.commons_only)
    for i, h in enumerate(hits):
        dims = f"{h.get('width')}x{h.get('height')} {h.get('seconds')}s" if h.get("width") else (h.get("year") or "")
        print(f"#{i + 1:<3}{h['kind']:<13}| {h['licence']:<16}| {dims:<16}| {h['author'][:24]:<24}| {h['title'][:70]}")
        print(f"      {h['risk_note']} — {h['page']}")
    print(f"{len(hits)} usable hits (own/archive first; «rights-holder» and «broadcast?» are listed to be avoided)")
    if args.out:
        with open(args.out + ".json", "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False, indent=1)
        print(f"→ {args.out}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
