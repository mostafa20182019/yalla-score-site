# -*- coding: utf-8 -*-
"""Rewrite the TEXT of already-published Facebook posts from data/articles.json.

Why: on 2026-09-05 the user changed the Facebook rule for match articles —
posts now carry a condensed version of the article instead of the title only.
Posts that had already gone out (title-only) get their message updated IN
PLACE with Graph API `POST /{post_id}` (no new post, no duplicate).

Usage (locally, token stays on your machine):
    set "FB_PAGE_TOKEN=..." && python fb_update_posts.py 393 394 395 396 397 391
    python fb_update_posts.py --all-match        # every article with a `kind` and a recorded post
    python fb_update_posts.py --dry-run 393      # show the text, change nothing

The post ids come from data/fb_posted.json ("articles" -> post_id). Records
whose post_id starts with "seeded" (never really posted) are skipped.
"""
import json, os, sys, urllib.parse, urllib.request, urllib.error

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = "https://graph.facebook.com/v23.0"


def main():
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    all_match = "--all-match" in args
    ids = [a for a in args if a.isdigit()]
    arts = {str(a["article_id"]): a for a in
            json.load(open(os.path.join(HERE, "data", "articles.json"), encoding="utf-8"))["results"][0]["items"]}
    state = json.load(open(os.path.join(HERE, "data", "fb_posted.json"), encoding="utf-8"))
    posted = state.get("articles", {})
    if all_match:
        ids = [k for k, a in arts.items() if a.get("kind") and k in posted]
    if not ids:
        print("nothing to do (give article ids or --all-match)")
        return 0
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token and not dry:
        print("FB_PAGE_TOKEN not set"); return 1
    for aid in ids:
        a = arts.get(aid); rec = posted.get(aid)
        if not a or not rec or not rec.get("post_id") or str(rec["post_id"]).startswith("seeded"):
            print(f"{aid}: no article/post record - skipped"); continue
        msg = (a.get("fb_post") or "").strip()
        if not msg:
            print(f"{aid}: empty fb_post - skipped"); continue
        print(f"--- {aid} -> post {rec['post_id']} ({len(msg)} chars)\n{msg}\n")
        if dry:
            continue
        data = urllib.parse.urlencode({"message": msg, "access_token": token}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{GRAPH}/{rec['post_id']}", data=data), timeout=30) as r:
                print(f"{aid}: updated -> {json.load(r)}")
            rec["text_updated"] = True
        except urllib.error.HTTPError as e:
            print(f"{aid}: FAILED HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:  # noqa: BLE001
            print(f"{aid}: FAILED {e}")
    if not dry:
        json.dump(state, open(os.path.join(HERE, "data", "fb_posted.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
