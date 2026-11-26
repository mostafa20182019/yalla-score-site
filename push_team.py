# -*- coding: utf-8 -*-
"""Web push for «تابع فريقك»: a followed club's goals, kick-off, final score
and news, sent ONLY to the browsers that follow that club.

    python push_team.py --goal '<json>'      # fb-post.yml, right after the goal card
    python push_team.py --whistle '<json>'   # ... after the kick-off / full-time card
    python push_team.py --news               # publish.yml, after push_send.py
    add --dry to any of them: what would be sent, to how many, and why / why not

WHY (2026-11-19, the user's «ابدأ فى اشعارات الفريق» after AdSense asked for
«محتوى يخلى المستخدم يرجعلك تانى»): the bell sends the same five stories a
day to everyone. A reader who followed ONE club wants that club: its goal the
minute it is scored, the result, and every story about it - not the five the
whole list gets. The club rides on the push subscription (push_subs.team,
push.js); this file is the sender.

THE RULES
  1. MATCH EVENTS come from the Worker's own dispatch - the JSON fb-post.yml
     already receives for the Facebook goal / kick-off / full-time cards -
     and go out only AFTER fb_post.py has posted that card (its store record
     is the proof). So every guard the page's posts have applies here without
     being written twice: a goal with no scorer named, a goal the live score
     no longer carries, a duplicate dispatch - none of them was posted, none
     of them is pushed. Half-time is not sent: three buzzes a match is enough.
  2. No quiet hours for a match: a reader who follows a club wants its goal
     at 01:10 too. A goal that is ten minutes old is worth nothing, so the
     push service drops it after GOAL_TTL if the phone is off.
  3. CLUB NEWS: a new article about the club (the club page's own test,
     names._team_news) that the bell did NOT send to everyone. Same quiet
     hours and freshness as push_send.py; at most NEWS_CAP a day per club,
     NEWS_GAP_MIN apart, one per club per run.
  4. CLAIM-THEN-POST like everything else (store.py, kind="push-team"): the
     reference names the event AND the club, so two overlapping runs cannot
     both buzz one club's followers, and a match between two followed clubs
     is one push per club.

Fails closed and quiet like push_send.py: no key, no D1, no follower -> it
prints why and exits 0. It never fails the job it rides in.
"""
import argparse
import json
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import fb_post as FB                                     # noqa: E402
import push_send as PS                                   # noqa: E402
import store                                             # noqa: E402
from site_lib import config as C                         # noqa: E402
from site_lib.clubs import TEAM_PAGES                    # noqa: E402
from site_lib.competitions import LIVE_COMP_ID           # noqa: E402
from site_lib.names import _in_scope, _team_news         # noqa: E402

KIND = "push-team"
GOAL_TTL = 10 * 60        # a goal is news for ten minutes
WHISTLE_TTL = 2 * 3600
NEWS_CAP = 4              # per club, per Cairo day
NEWS_GAP_MIN = 30
WHISTLES = ("ko", "ft")   # half-time stays on Facebook

_COMP_NAME = {v: k for k, v in LIVE_COMP_ID.items()}


def _arabic(s):
    return any("؀" <= ch <= "ۿ" for ch in s)


def side_names(tp):
    """The Arabic names a live payload can carry for this club. The Worker's
    payload is the 365scores feed (Arabic names) for every competition, while
    the European clubs' match tokens are football-data's Latin names - so for
    those the club's own Arabic name and its news spellings stand in."""
    names = {tp["name"]} | {t for t, _ in tp["match_tokens"] if _arabic(t)}
    if not any(_arabic(t) for t, _ in tp["match_tokens"]):
        names |= set(tp.get("news_tokens") or [])
    if tp["slug"] == "egypt":
        names.add("مصر")
    return names


def slugs_for_game(g):
    """The club pages whose team plays in this dispatched game: an EXACT side
    name (the feed spells «الأهلي» and «الأهلي طرابلس» - never a substring)
    inside the club's own competitions."""
    comp = _COMP_NAME.get(int(g.get("c") or 0), "")
    sides = {str(g.get("h") or "").strip(), str(g.get("a") or "").strip()}
    out = []
    for tp in TEAM_PAGES:
        if not (sides & side_names(tp)):
            continue
        scopes = [sc for t, sc in tp["match_tokens"]]
        if any(_in_scope(sc, comp) for sc in scopes):
            out.append(tp["slug"])
    return out


# ---------------------------------------------------------------- payloads
def _base(title, body, url, tag):
    return json.dumps({"title": PS._cut(title, 100), "body": PS._cut(body, 150), "url": url,
                       "icon": "/assets/icon-192.png", "badge": "/assets/badge-96.png", "tag": tag},
                      ensure_ascii=False)


def goal_payload(g, ev):
    cap = FB.goal_caption(g, ev).split("\n")
    body = cap[1] if len(cap) > 1 and cap[1].startswith("🥅") else ""
    return _base(cap[0], body, f"{C.SITE_BASE}/m/{g['id']}", f"g-{g['id']}")


def whistle_payload(kind, g, goals):
    cap = FB.whistle_caption(kind, g, goals).split("\n")
    body = " · ".join(x for x in cap[1:] if x and "elgoon.com" not in x and not x.startswith("#"))
    if not body:                          # a kick-off has no scorers: say where it is played
        body = FB.GOAL_COMP_AR.get(int(g.get("c") or 0), "")
    return _base(cap[0], body, f"{C.SITE_BASE}/m/{g['id']}", f"g-{g['id']}")


# ---------------------------------------------------------------- sending
def followers(slug):
    try:
        # the column holds up to four slugs joined by commas (2026-11-26):
        # the commas around both sides keep «al-ahly» out of «al-ahly-tripoli»
        return store.sql("SELECT endpoint, p256dh, auth FROM push_subs WHERE team = ? "
                         "OR (',' || team || ',') LIKE ?", [slug, f"%,{slug},%"])
    except Exception as e:                                    # noqa: BLE001
        if "no such table" in str(e) or "no such column" in str(e):
            return []                     # nobody followed a club with the bell on yet
        raise


def _sender(ttl, topic, urgency):
    def send(sub, data, key):
        from pywebpush import WebPushException, webpush
        try:
            r = webpush(subscription_info={"endpoint": sub["endpoint"],
                                           "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                        data=data, vapid_private_key=key, vapid_claims={"sub": PS.CONTACT},
                        ttl=ttl, headers={"Urgency": urgency, "Topic": topic}, timeout=15)
            return "ok", r.status_code
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            return ("gone" if code in (404, 410) else "fail"), code
        except Exception as e:                                # noqa: BLE001
            return "fail", str(e)[:80]
    return send


def ready(dry):
    """The private key, or None with the reason printed."""
    key, site_key = PS.private_key(), C.VAPID_PUBLIC_KEY
    if not site_key:
        print("push-team: VAPID_PUBLIC_KEY is empty - push is dark"); return None
    if store.backend() == "json":
        print("push-team: no D1 in this environment - the subscriptions live there"); return None
    if dry:
        return key or "dry"
    if not key:
        print("push-team: VAPID_PRIVATE_KEY not set - push is off"); return None
    if PS.public_of(key) != site_key:
        print("::warning::push-team: VAPID_PRIVATE_KEY does not belong to the site's public key"); return None
    return key


def deliver(ref, slug, data, key, sender, title, dry=False, seen=None):
    """One event to one club's followers. Returns how many got it.

    seen = the endpoints this SAME event already went to (a reader who follows
    both clubs of a match gets one notification, not two); the caller owns the
    set and shares it between the clubs of one event."""
    subs = followers(slug)
    if seen is not None:
        subs = [s for s in subs if s["endpoint"] not in seen]
        seen.update(s["endpoint"] for s in subs)
    print(f"push-team {ref} -> {slug}: {len(subs)} follower(s)")
    if dry:
        print("  " + data); return 0
    if not subs:
        return 0                          # nothing sent, nothing recorded
    full = f"{ref}:{slug}"
    if not store.claim(KIND, full, title):
        print(f"  {full}: already sent or held by another run"); return 0
    ok, gone, fails = PS.fan_out(subs, data, key, sender)
    if gone:
        PS.drop_subs(gone)
    print(f"  sent {ok}/{len(subs)}, dropped {len(gone)} dead endpoint(s)" + (f", failed {fails}" if fails else ""))
    if ok == 0 and fails:
        store.release(KIND, full)         # nobody got it: a retry cannot double-notify
        return 0
    store.record_post(KIND, full, f"{ok}/{len(subs)}", title=title)
    return ok


# ---------------------------------------------------------------- match events
def goal(payload, dry=False, sender=None):
    try:
        d = json.loads(payload)
        g, ev, seq = d["g"], d.get("ev") or {}, d.get("seq")
    except Exception as e:                                    # noqa: BLE001
        print(f"push-team --goal: bad payload ({e})"); return 0
    key = ready(dry)
    if not key:
        return 0
    slugs = slugs_for_game(g)
    if not slugs:
        print(f"push-team goal {g.get('id')}: no followed-club page plays in it"); return 0
    rec = store.get_post("goal", f"{g['id']}:{seq}")
    if not dry and not (rec and rec.get("post_id")):
        print(f"push-team goal {g['id']}:{seq}: the goal card was not posted - not pushed"); return 0
    data = goal_payload(g, ev)
    send = sender or _sender(GOAL_TTL, f"g{g['id']}", "high")
    seen = set()
    for slug in slugs:
        deliver(f"goal:{g['id']}:{seq}", slug, data, key, send, data[:80], dry, seen)
    return 0


def whistle(payload, dry=False, sender=None):
    try:
        d = json.loads(payload)
        kind, g, goals = d["kind"], d["g"], d.get("goals") or []
    except Exception as e:                                    # noqa: BLE001
        print(f"push-team --whistle: bad payload ({e})"); return 0
    if kind not in WHISTLES:
        print(f"push-team whistle {kind}: not a pushed kind"); return 0
    key = ready(dry)
    if not key:
        return 0
    slugs = slugs_for_game(g)
    if not slugs:
        print(f"push-team {kind} {g.get('id')}: no followed-club page plays in it"); return 0
    rec = store.get_post(kind, str(g["id"]))
    if not dry and not (rec and rec.get("post_id")):
        print(f"push-team {kind} {g['id']}: the card was not posted - not pushed"); return 0
    data = whistle_payload(kind, g, goals)
    send = sender or _sender(WHISTLE_TTL, f"g{g['id']}", "high" if kind == "ko" else "normal")
    seen = set()
    for slug in slugs:
        deliver(f"{kind}:{g['id']}", slug, data, key, send, data[:80], dry, seen)
    return 0


# ---------------------------------------------------------------- club news
def news_pick(tp, items, now, sent_general, recent):
    """(article, why) for ONE club on this run, or (None, reason)."""
    slug = tp["slug"]
    mine = [r for r in recent if str(r.get("ref_id", "")).startswith("news:") and str(r.get("ref_id", "")).endswith(":" + slug)]
    day0 = int(PS.cairo_midnight(now).timestamp())
    today = [r for r in mine if r["posted_at"] >= day0]
    if len(today) >= NEWS_CAP:
        return None, f"daily cap reached ({len(today)}/{NEWS_CAP})"
    if mine and now.timestamp() - max(r["posted_at"] for r in mine) < NEWS_GAP_MIN * 60:
        return None, f"last club story under {NEWS_GAP_MIN} min ago"
    done = {str(r.get("ref_id", "")) for r in mine}
    best = None
    for art in items:
        aid = str(art.get("article_id", "")).strip()
        if not aid or aid in sent_general or f"news:{aid}:{slug}" in done or PS.excluded(art):
            continue
        if not _team_news(tp, art):
            continue
        pub = FB.article_pub_dt(art)
        if pub is None or PS.sendable_hours(pub, now) > PS.MAX_AGE_H:
            continue
        if best is None or pub > best[0]:
            best = (pub, art)
    if best is None:
        return None, "no new story about the club"
    return best[1], f"sent today {len(today)}/{NEWS_CAP}"


def news(dry=False, now=None, sender=None, live=None):
    key = ready(dry)
    if not key:
        return 0
    now = now or PS._now()
    if PS.is_quiet(now):
        print("push-team news: quiet hours (01:00-08:00 Cairo)"); return 0
    items = FB.load_articles()
    sent_general = set(store.posted_ids(PS.KIND))
    day0 = int(PS.cairo_midnight(now).timestamp())
    recent = store.posted_since(KIND, min(day0, int(now.timestamp()) - NEWS_GAP_MIN * 60))
    send = sender or _sender(PS.TTL_SEC, "team-news", "normal")
    seen_by_art = {}                      # one story about two followed clubs: one notification
    for tp in TEAM_PAGES:
        art, why = news_pick(tp, items, now, sent_general, recent)
        if art is None:
            continue
        aid = str(art.get("article_id")).strip()
        link = FB.article_link(art)
        if not dry and not (live or FB.wait_live)(link):
            print(f"push-team news {aid}: page not live yet - next run"); continue
        deliver(f"news:{aid}", tp["slug"], PS.payload(art), key, send, art.get("title"), dry,
                seen_by_art.setdefault(aid, set()))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal")
    ap.add_argument("--whistle")
    ap.add_argument("--news", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    try:
        if a.goal:
            return goal(a.goal, dry=a.dry)
        if a.whistle:
            return whistle(a.whistle, dry=a.dry)
        if a.news:
            return news(dry=a.dry)
    except Exception as e:                                    # noqa: BLE001 - never fail the job it rides in
        print(f"::warning::push-team failed: {e}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
