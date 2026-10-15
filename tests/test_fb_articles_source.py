# -*- coding: utf-8 -*-
r"""fb_post reads the articles the SITE sees (2026-10-15).

    python tests/test_fb_articles_source.py     (from the repo root)

Article 801 («محمد هاني يوافق على تجديد عقده») was live for an hour with no
export commit, so `fb_post.py --pending` (which read data/articles.json)
counted 0 and the posting workflow was never dispatched. The poster now
checks the store's articles signature like the build does and pulls from D1
when the committed export is behind. No network: the store is faked.
"""
import json, os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fb_post as F

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

# a fake export with sig "old" and one article
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "data"))
export = {"sig": "old", "results": [{"items": [{"article_id": "800", "title": "a"}]}]}
json.dump(export, open(os.path.join(tmp, "data", "articles.json"), "w", encoding="utf-8"))
F.HERE = tmp

class FakeStore:
    def __init__(self, backend, sig, fresh, boom=False):
        self._b, self._s, self._f, self._boom = backend, sig, fresh, boom
        self.pulls = 0
    def backend(self): return self._b
    def articles_sig(self):
        if self._boom: raise RuntimeError("quota")
        return self._s
    def article_all(self, with_body=True):
        self.pulls += 1
        return self._f
real = F.store

F.store = FakeStore("json", None, [])
ck("1 json backend: the export, untouched", [a["article_id"] for a in F.load_articles()] == ["800"])

F.store = fs = FakeStore("d1", "old", [{"article_id": "801"}, {"article_id": "800"}])
ck("2 D1 and the export's sig matches: the export, no D1 pull", [a["article_id"] for a in F.load_articles()] == ["800"] and fs.pulls == 0)

F.store = fs = FakeStore("d1", "new", [{"article_id": "801"}, {"article_id": "800"}])
got = [a["article_id"] for a in F.load_articles()]
ck("3 D1 and the export is BEHIND: the articles come from D1 (801 visible)", got == ["801", "800"] and fs.pulls == 1, str(got))

F.store = fs = FakeStore("d1", None, [{"article_id": "801"}])
ck("4 no sig yet (never bumped): pull everything, like the build", [a["article_id"] for a in F.load_articles()] == ["801"])

F.store = FakeStore("d1", "new", [], boom=True)
ck("5 a D1 failure never blocks: the export is used", [a["article_id"] for a in F.load_articles()] == ["800"])

F.store = real
F.HERE = os.getcwd()
print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
