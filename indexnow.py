"""IndexNow: tell Bing, Yandex and Seznam what changed, the moment it changes.

    python indexnow.py            # submit today's changed URLs
    python indexnow.py --dry      # print what would be submitted, send nothing

Why this exists (2026-09-20): Search Console says 7 of our pages are indexed
and 732 are «Discovered – currently not indexed» — Google knows the URLs and
has not crawled them. That is a crawl-allocation decision on a seven-week-old
domain whose previous owner ran a made-for-AdSense site on it, and no amount of
publishing changes it quickly. Bing and Yandex carry none of that history, and
IndexNow is a push protocol: no account, no quota, no waiting to be discovered.
Google does NOT participate — this buys nothing there, and pretending otherwise
would be the kind of thing this project does not do.

How it works: a key file at https://yallascore.site/<key>.txt containing the
key proves we own the host; a POST lists the URLs. The key file ships from
root-extras/ like ads.txt.

What gets submitted: the URLs whose <lastmod> in the freshly built sitemap is
today — that is exactly «what changed in this build» — newest first, capped at
CAP. Sections and articles come before match pages when the cap bites.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = "yallascore.site"
KEY = "ed37eefa1248d5155a305468d9099dab"
KEY_URL = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
CAP = 100          # well under the protocol's 10,000; a focused list is the point
UA = "yalla-score-indexnow/1.0"


def rank(u):
    """Sections and articles first, match pages last: if the cap bites, it
    should bite the templated pages, not the ones we write."""
    path = u.split(HOST, 1)[-1]
    if path in ("", "/"):
        return 0
    for i, pre in enumerate(("/news", "/matches", "/predictions", "/analysis",
                             "/fixtures/", "/standings/", "/team/", "/a/", "/m/"), start=1):
        if path.startswith(pre):
            return i
    return 5


def changed_today(sitemap_path, today=None):
    today = today or datetime.date.today().isoformat()
    with open(sitemap_path, encoding="utf-8") as f:
        xml = f.read()
    out = []
    for loc, lastmod in re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", xml):
        if lastmod[:10] == today:
            out.append(loc)
    out.sort(key=rank)
    return out[:CAP], len(out)


def key_is_live():
    """Never submit against a key the search engines cannot verify."""
    try:
        req = urllib.request.Request(KEY_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200 and KEY in r.read().decode("utf-8", "replace")
    except Exception as e:                                   # noqa: BLE001
        print(f"  key file not reachable ({e}) — not submitting")
        return False


def submit(urls):
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": KEY_URL,
                       "urlList": urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            # 200 accepted, 202 accepted-but-key-still-validating: both fine
            print(f"  IndexNow: HTTP {r.status} for {len(urls)} URLs")
            return r.status in (200, 202)
    except urllib.error.HTTPError as e:
        print(f"  IndexNow refused: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}")
    except Exception as e:                                   # noqa: BLE001
        print(f"  IndexNow failed: {e}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print, do not submit")
    ap.add_argument("--sitemap", default=os.path.join(HERE, "dist", "sitemap.xml"))
    args = ap.parse_args()
    if not os.path.exists(args.sitemap):
        print("no sitemap built — nothing to submit")
        return 0
    urls, total = changed_today(args.sitemap)
    if not urls:
        print("IndexNow: nothing changed today")
        return 0
    print(f"IndexNow: {total} URLs changed today, submitting {len(urls)}")
    for u in urls[:8]:
        print("   ", u)
    if len(urls) > 8:
        print(f"    … and {len(urls) - 8} more")
    if args.dry:
        print("  (dry run — nothing sent)")
        return 0
    if not key_is_live():
        return 0
    submit(urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
