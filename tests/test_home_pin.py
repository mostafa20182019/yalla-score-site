r"""The home page lead story can be pinned (HOME_PIN, 2026-10-07).

    python tests/test_home_pin.py   (from the repo root)

User ask: keep the derby analysis as the big card of «الأكثر تداولًا» even
when newer stories arrive. The pin expires by itself (`until`), and a pin on
an article that is not listed changes nothing.
"""
import datetime
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


from site_lib.articles import pinned_first                  # noqa: E402

arts = [{"article_id": str(i)} for i in (700, 699, 698, 687, 650)]
pin = {"article_id": "687", "until": "2026-10-12T00:00:00+03:00"}
before = datetime.datetime(2026, 10, 9, 12, 0, tzinfo=datetime.timezone.utc)
after = datetime.datetime(2026, 10, 12, 1, 0, tzinfo=datetime.timezone.utc)
ids = lambda xs: [a["article_id"] for a in xs]               # noqa: E731
ck("while valid: the pinned article leads, newer ones follow in order",
   ids(pinned_first(arts, pin, before)) == ["687", "700", "699", "698", "650"])
ck("nothing is lost or duplicated", sorted(ids(pinned_first(arts, pin, before))) == sorted(ids(arts)))
ck("after `until`: back to newest first", ids(pinned_first(arts, pin, after)) == ids(arts))
ck("a pin on an unlisted article changes nothing",
   ids(pinned_first(arts, {"article_id": "1", "until": pin["until"]}, before)) == ids(arts))
ck("no pin / a broken pin changes nothing",
   ids(pinned_first(arts, {}, before)) == ids(arts) and ids(pinned_first(arts, {"article_id": "687"}, before)) == ids(arts))
src = io.open("site_pages/home.py", encoding="utf-8").read()
ck("the home page applies the pin before it builds its blocks",
   src.index("pinned_first(articles)") < src.index("home_insights(articles, pin_on"))   # prefix: the call also passes held=...

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
