# -*- coding: utf-8 -*-
r"""The article posts' daily cap and the evening digest (2026-11-20).

    python tests/test_article_cap.py      (from the repo root)

The page took 6-16 article posts a day. fb_post now posts at most
ARTICLE_DAILY_CAP a Cairo day, one a run, ARTICLE_GAP_MIN apart, the Egyptian
and Sudanese sides first - and what the cap leaves out goes in ONE evening
post, so the 09-12 rule «an article on the site lands on Facebook» still
holds. No network: the store is a throwaway sqlite file, the clock is passed
in, and post_text is replaced.
"""
import datetime
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "state.sqlite")

import store            # noqa: E402
import fb_post as fp    # noqa: E402

store.init_schema()
fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


CAIRO = fp.CAIRO


def at(hour, minute=0):
    """A moment of one fixed Cairo day, as UTC."""
    return datetime.datetime(2026, 11, 21, hour, minute, tzinfo=CAIRO).astimezone(datetime.timezone.utc)


def art(aid, title, hour, minute=0):
    return {"article_id": str(aid), "title": title, "summary": title,
            "pub_ts": at(hour, minute).isoformat()}


def mark_posted(aid, when):
    """An article post recorded at `when` (the store stamps now, so set it)."""
    store.claim("article", str(aid))
    store.record_post("article", str(aid), f"P{aid}")
    store.sql("UPDATE fb_posted SET posted_at = ? WHERE kind = 'article' AND ref_id = ?",
              [int(when.timestamp()), str(aid)])


print("1. the shipped numbers")
ck("one article a run, five a day, an hour apart, digest from 21:00 Cairo",
   (fp.AUTO_MAX_PER_RUN, fp.ARTICLE_DAILY_CAP, fp.ARTICLE_GAP_MIN, fp.DIGEST_HOUR) == (1, 5, 60, 21))

print("2. who goes first")
EURO = art(1, "ريال مدريد يجدد عقد كورتوا حتى 2028", 12, 0)
AHLY = art(2, "الأهلي يعلن قائمته لمباراة بيراميدز في الدوري المصري", 12, 30)
HILAL = art(3, "الهلال السوداني يصل كوناكري لمواجهة حوريا في دوري أبطال أفريقيا", 12, 40)
OTHER = art(4, "بوروسيا دورتموند يعلن إصابة لاعبه", 12, 10)
ck("an Egyptian or Sudanese side ranks 0, another curated club 1, the rest 2",
   [fp.article_rank(a) for a in (AHLY, HILAL, EURO, OTHER)] == [0, 0, 1, 2],
   str([fp.article_rank(a) for a in (AHLY, HILAL, EURO, OTHER)]))
got = fp.pending([EURO, OTHER, AHLY, HILAL], now=at(13))
ck("one article a run, and it is the OLDEST of the home sides - not the oldest of all",
   [a["article_id"] for a in got] == ["2"], str([a["article_id"] for a in got]))

print("3. the gap")
mark_posted(2, at(13))
ck("nothing more for an hour after an article post", fp.pending([EURO, OTHER, HILAL], now=at(13, 40)) == [])
got = fp.pending([EURO, OTHER, HILAL], now=at(14, 1))
ck("after the hour the next home side goes", [a["article_id"] for a in got] == ["3"])

print("4. the cap")
for i, h in zip((3, 11, 12, 13), (14, 15, 16, 17)):
    mark_posted(i, at(h))
ck("five posts today", len(fp.posted_today(at(18, 30))) == 5)
ck("a sixth article waits, however fresh", fp.pending([art(20, "الزمالك يفوز", 18, 0)], now=at(18, 30)) == [])
ck("the next Cairo day starts from zero",
   len(fp.posted_today(at(18, 30) + datetime.timedelta(days=1))) == 0)

print("5. the digest")
LATE = art(20, "الزمالك يعلن موعد مباراته المقبلة في الدوري المصري", 18, 0)
OLDDAY = {"article_id": "30", "title": "خبر من أمس", "summary": "",
          "pub_ts": (at(12) - datetime.timedelta(days=1)).isoformat()}
items = [EURO, OTHER, LATE, OLDDAY, AHLY]
ck("before 21:00 Cairo there is no digest", fp.digest_due(items, now=at(20, 59)) == [])
due = fp.digest_due(items, now=at(21, 5))
ck("at 21:00 it holds today's articles that got no post - never a posted one, never yesterday's",
   [a["article_id"] for a in due] == ["20", "1", "4"], str([a["article_id"] for a in due]))
text = fp.digest_text(due)
ck("the text: the heading, each title with its own link, then the news page",
   text.startswith("📰 أخبار اليوم على الجون") and all(a["title"] in text for a in due)
   and f"{fp.SITE}/a/20" in text and f"{fp.SITE}/a/1" in text and text.rstrip().endswith(f"{fp.SITE}/news"),
   text)
ck("no betting word, no «عاجل»", not any(w in text for w in ("توقع", "راهن", "اربح", "عاجل")))
sent = []
fp.post_text = lambda token, message: sent.append(message) or "DG1"
ck("it posts once", fp.post_digest("tok", items, now=at(21, 5)) == "DG1" and len(sent) == 1)
ck("... and never twice the same day", fp.post_digest("tok", items, now=at(21, 40)) is None and len(sent) == 1)
ck("its articles never get a post of their own afterwards",
   fp.pending(items, now=at(21, 5) + datetime.timedelta(days=1)) == []
   and {"20", "1", "4"} <= set(store.posted_ids("digest_item")))
ck("--pending counts a due digest as work (or a capped evening never dispatches)",
   bool(fp.digest_due([{"article_id": "40", "title": "بيراميدز يعلن قائمته", "summary": "",
                        "pub_ts": (at(10) + datetime.timedelta(days=1)).isoformat()}],
                      now=at(21, 5) + datetime.timedelta(days=1))))

print("6. a quiet day needs no digest")
store.sql("DELETE FROM fb_posted")
fresh = art(50, "الأهلي يعلن قائمته", 20, 30)
ck("an article still young enough for its own post is not in the digest",
   fp.digest_due([fresh], now=at(21, 5)) == [] and [a["article_id"] for a in fp.pending([fresh], now=at(21, 5))] == ["50"])

print("6. a night of European reports does not spend the day (2026-11-26)")
D3 = lambda h, m=0: at(h, m) + datetime.timedelta(days=3)      # noqa: E731 - a clean day


def piece(aid, title, hour, kind=None):
    a = {"article_id": str(aid), "title": title, "summary": title, "pub_ts": D3(hour).isoformat()}
    if kind:
        a["kind"] = kind
    return a


R1, R2 = piece(61, "نتيجة مباراة نابولي وتورينو 2-0", 0, "report"), piece(62, "نتيجة مباراة ليل وليون 1-1", 0, "report")
R3 = piece(63, "نتيجة مباراة موناكو وأوكسير 3-0", 1, "report")
RH = piece(64, "نتيجة مباراة الأهلي وبيراميدز 0-2", 1, "report")
NEWS = piece(65, "بوروسيا دورتموند يعلن إصابة لاعبه", 1)
ck("the number shipped: two foreign reports a day", fp.FOREIGN_REPORT_CAP == 2)
ck("a report of a side of ours is not foreign; another club's is; news never is",
   [fp.foreign_report(a) for a in (R1, RH, NEWS)] == [True, False, False])
mark_posted(61, D3(0, 30))
ck("the second foreign report still goes", [a["article_id"] for a in fp.pending([R1, R2, R3], now=D3(1, 40))] == ["62"])
mark_posted(62, D3(1, 40))
ck("the third waits for the digest, with three posts of the day unspent", fp.pending([R1, R2, R3], now=D3(3)) == [])
ck("...and the day's news takes the slot", [a["article_id"] for a in fp.pending([R1, R2, R3, NEWS], now=D3(3))] == ["65"])
ck("...and so does a report of a side of ours", [a["article_id"] for a in fp.pending([R1, R2, R3, RH], now=D3(3))] == ["64"])
ck("the held report is a line of the 21:00 digest", "63" in [a["article_id"] for a in fp.digest_items([R1, R2, R3], now=D3(21, 5))])

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
