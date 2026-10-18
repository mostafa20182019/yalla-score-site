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

ONCE PER CHANGE (2026-10-18): publish runs every 15 minutes and every run used
to resend the same ~100 «changed today» URLs — Bing Webmaster showed 6.7K
submissions in 15 hours and 67K in a week for a 1,000-page site, while Bing
crawled 35 URLs and indexed 4. Flooding the same URLs is noise an engine
learns to ignore. Now a ledger in the D1 store (kind "indexnow", ref = the
URL, title = the <lastmod> we pushed) makes each URL go out once per real
change: skipped while its <lastmod> is the one already pushed, and never twice
within COOLDOWN_H hours even if it moved. Hubs and match pages carry a
date-only <lastmod>, so they go at most once a day; articles once per edit.
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
# 2026-10-12: Bing Webmaster Tools only reports IndexNow traffic for a key it
# generated itself (the «Get Started» wizard offers no "use my key"), so the
# site now signs with Bing's key; the old key file stays served (harmless).
KEY = "0529d0814bd94b3dab7787bf0afd773f"
KEY_URL = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
CAP = 100          # well under the protocol's 10,000; a focused list is the point
COOLDOWN_H = 6     # the same URL is never pushed twice within this window (2026-10-18)
LEDGER_KIND = "indexnow"   # store.py kind: ref_id = URL, title = the <lastmod> pushed
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


def changed_today(sitemap_path, today=None, with_lastmod=False):
    today = today or datetime.date.today().isoformat()
    with open(sitemap_path, encoding="utf-8") as f:
        xml = f.read()
    out = []
    for loc, lastmod in re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", xml):
        if lastmod[:10] == today:
            out.append((loc, lastmod))
    out.sort(key=lambda t: rank(t[0]))
    if with_lastmod:
        return out, len(out)
    return [u for u, _ in out[:CAP]], len(out)


def select(changed, lookup, now=None, cooldown_h=COOLDOWN_H, cap=CAP):
    """The URLs worth pushing NOW out of `changed` = [(url, lastmod)], ranked.
    `lookup(url)` -> the ledger record ({"title": lastmod_pushed, "posted_at":
    epoch}) or None. A URL is skipped when the pushed <lastmod> equals the
    current one (nothing new since), or when it was pushed within the
    cooldown. Returns ([(url, lastmod)], skipped_same, skipped_cooldown)."""
    now = now or datetime.datetime.now(datetime.timezone.utc).timestamp()
    out, same, cool = [], 0, 0
    for url, lastmod in changed:
        rec = lookup(url) or {}
        pushed = str(rec.get("title") or "")
        at = rec.get("posted_at") or rec.get("ts") or 0
        if pushed and pushed == lastmod:
            same += 1
            continue
        if at and (now - float(at)) < cooldown_h * 3600:
            cool += 1
            continue
        out.append((url, lastmod))
        if len(out) >= cap:
            break
    return out, same, cool


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
    changed, total = changed_today(args.sitemap, with_lastmod=True)
    if not changed:
        print("IndexNow: nothing changed today")
        return 0
    import store
    try:
        picked, same, cool = select(changed, lambda u: store.get_post(LEDGER_KIND, u))
        print(f"IndexNow: {total} URLs changed today; {same} already pushed at this version, "
              f"{cool} pushed within {COOLDOWN_H}h; submitting {len(picked)} (ledger: {store.backend()})")
    except Exception as e:                                   # noqa: BLE001 - a dead store must not stop the push
        print(f"  ledger unavailable ({e}) - submitting the capped list")
        picked, same, cool = changed[:CAP], 0, 0
    if not picked:
        return 0
    urls = [u for u, _ in picked]
    for u in urls[:8]:
        print("   ", u)
    if len(urls) > 8:
        print(f"    … and {len(urls) - 8} more")
    if args.dry:
        print("  (dry run — nothing sent)")
        return 0
    if not key_is_live():
        return 0
    if submit(urls):
        try:
            for u, lastmod in picked:
                store.record_post(LEDGER_KIND, u, "1", title=lastmod)
        except Exception as e:                               # noqa: BLE001
            print(f"  ledger not updated ({e}) - the next run may resend these")
    return 0


if __name__ == "__main__":
    sys.exit(main())
