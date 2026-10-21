# -*- coding: utf-8 -*-
"""The WordPress import file (2026-10-21): every article as a post with its
old URL, picture, dates, category and meta.

    python tests/test_wp_export.py     (from the repo root)
"""
import json, os, sys, tempfile
import xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
import wp_export as WX

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

NS = {"wp": "http://wordpress.org/export/1.2/", "content": "http://purl.org/rss/1.0/modules/content/",
      "excerpt": "http://wordpress.org/export/1.2/excerpt/", "dc": "http://purl.org/dc/elements/1.1/"}

arts = [
    {"article_id": "892", "title": "تقرير: النصر يتغلب على نيوم 1-0", "summary": "ملخص", "body": "<p>نص</p><h2>كيف سارت</h2><p>x & y</p>",
     "author": "مصطفى عبدالسلام", "pub_date": "2026-10-21", "pub_ts": "2026-10-21T13:02:22+03:00", "match_id": "4789450", "kind": "report",
     "image_url": "https://yallascore.site/media/matchup-4789450-result.jpg", "image_credit": "الصورة: تصميم يلا سكور",
     "sources": [{"name": "365scores", "url": "https://yallascore.site/m/4789450", "note": "الإحصاءات"}],
     "faq": [{"q": "متى؟", "a": "الثلاثاء."}], "fb_post": "سطر"},
    {"article_id": "61", "title": "خبر قديم", "summary": "", "body": "<p>قديم</p>", "author": "فريق التحرير", "pub_date": "2026-08-03",
     "image_url": "", "image_credit": ""},
]
tmp = tempfile.mkdtemp()
out = os.path.join(tmp, "all.xml")
WX.write(sorted(arts, key=lambda x: int(x["article_id"])), out)
root = ET.parse(out).getroot()
ch = root.find("channel")
items = ch.findall("item")
posts = [i for i in items if i.find("wp:post_type", NS).text == "post"]
atts = [i for i in items if i.find("wp:post_type", NS).text == "attachment"]
ck("1 WXR 1.2 with the two authors and the four categories", ch.find("wp:wxr_version", NS).text == "1.2"
   and len(ch.findall("wp:author", NS)) == 2 and len(ch.findall("wp:category", NS)) == 4)
ck("2 one post per article, one attachment per article with a picture", len(posts) == 2 and len(atts) == 1)
p = next(i for i in posts if i.find("wp:post_id", NS).text == "892")
ck("3 the old URL survives: post_name = the id, link = /a/<id>", p.find("wp:post_name", NS).text == "892" and p.find("link").text == "https://yallascore.site/a/892")
ck("4 dates: Cairo local and GMT from pub_ts", p.find("wp:post_date", NS).text == "2026-10-21 13:02:22" and p.find("wp:post_date_gmt", NS).text == "2026-10-21 10:02:22")
old = next(i for i in posts if i.find("wp:post_id", NS).text == "61")
ck("5 a date-only row lands at noon Cairo", old.find("wp:post_date", NS).text == "2026-08-03 12:00:00" and old.find("wp:post_date_gmt", NS).text == "2026-08-03 09:00:00")
body = p.find("content:encoded", NS).text
ck("6 the body keeps its HTML and carries the FAQ and the sources", body.startswith("<p>نص</p><h2>") and "x & y" in body
   and "<h2>أسئلة شائعة</h2><h3>متى؟</h3><p>الثلاثاء.</p>" in body and 'href="https://yallascore.site/m/4789450"' in body and "— الإحصاءات" in body)
ck("7 the excerpt is the summary, the author is the mapped login", p.find("excerpt:encoded", NS).text == "ملخص" and p.find("dc:creator", NS).text == "mustafa")
cats = {c.get("domain"): c.text for c in p.findall("category")}
ck("8 kind -> category (report), no kind -> news", cats.get("category") == "تقارير المباريات"
   and {c.get("domain"): c.text for c in old.findall("category")}.get("category") == "أخبار")
metas = {m.find("wp:meta_key", NS).text: m.find("wp:meta_value", NS).text for m in p.findall("wp:postmeta", NS)}
ck("9 the featured image points at the attachment (100000 + id), the credit and ids ride as meta",
   metas.get("_thumbnail_id") == "100892" and metas.get("ys_article_id") == "892" and metas.get("ys_match_id") == "4789450"
   and metas.get("ys_image_credit") == "الصورة: تصميم يلا سكور" and metas.get("ys_kind") == "report", str(metas))
att = atts[0]
ck("10 the attachment downloads from the live site, belongs to its post, caption = the credit",
   att.find("wp:attachment_url", NS).text == "https://yallascore.site/media/matchup-4789450-result.jpg"
   and att.find("wp:post_parent", NS).text == "892" and att.find("excerpt:encoded", NS).text == "الصورة: تصميم يلا سكور"
   and att.find("wp:post_id", NS).text == "100892")
ck("11 a post without a picture has no thumbnail meta", "_thumbnail_id" not in {m.find("wp:meta_key", NS).text for m in old.findall("wp:postmeta", NS)})
ck("12 every post is published, comments open, type post", all(i.find("wp:status", NS).text == "publish" and i.find("wp:comment_status", NS).text == "open" for i in posts))

# the fixed pages (from a built dist/): article block only, no <h1>, links extensionless
pd = os.path.join(tmp, "dist")
os.makedirs(pd)
with open(os.path.join(pd, "about.html"), "w", encoding="utf-8") as f:
    f.write('<html><head><title>x</title></head><body><header>nav</header><main><article class="article legal">\n  <h1>من نحن</h1>\n  <div class="a-body"><p>نص <a href="/contact.html">اتصل</a> و<a href="/editors.html">المحررون</a></p></div>\n</article></main><footer>f</footer></body></html>')
pages_out = os.path.join(tmp, "pages.xml")
found = WX.write_pages(pages_out, dist=pd)
proot = ET.parse(pages_out).getroot()
pitems = proot.find("channel").findall("item")
ck("15 only the pages present in dist/ are written, as type page with the slug as post_name", found == ["about"] and len(pitems) == 1
   and pitems[0].find("wp:post_type", NS).text == "page" and pitems[0].find("wp:post_name", NS).text == "about" and pitems[0].find("title").text == "من نحن")
pb = pitems[0].find("content:encoded", NS).text
ck("16 the page body is the article block without its h1, links extensionless, no chrome", "<h1" not in pb and 'href="/contact"' in pb
   and 'href="/editors"' in pb and "nav" not in pb and "footer" not in pb and pb.startswith('<div class="a-body">'), pb[:80])

# the real export parses and keeps every article
real = WX.load_articles()
real_out = os.path.join(tmp, "real.xml")
WX.write(real, real_out)
rroot = ET.parse(real_out).getroot()
rposts = [i for i in rroot.find("channel").findall("item") if i.find("wp:post_type", NS).text == "post"]
ck("13 the real export: one post per article, all with a body and a slug", len(rposts) == len(real)
   and all((i.find("content:encoded", NS).text or "") and i.find("wp:post_name", NS).text for i in rposts), f"{len(rposts)} / {len(real)}")
ck("14 ...ids unique", len({i.find("wp:post_id", NS).text for i in rposts}) == len(rposts))

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
