r"""The article picture is shown WHOLE (2026-11-11).

    python tests/test_article_img.py

The user, on the Afsha story at desktop width: «هل ينفع تظبط صور المقالات
برضه عشان تظهر كلها لما ادخل على الخبر». The hero was a full-width box capped
at 400px with object-fit:cover, so a 16:9 picture lost its top and bottom on
every wide screen. It now keeps its own proportions, at most 540px high and
centred; a phone is unchanged (full width, natural height).
"""
import io, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

css = io.open("site_src/style.css", encoding="utf-8").read()
rule = re.search(r"\n\.a-img\{([^}]*)\}", css)
r = rule.group(1) if rule else ""
ck("1 the hero is never cropped: contain, natural height, no cover",
   "object-fit:contain" in r and "height:auto" in r and "cover" not in r, r)
ck("2 its own width, up to the column (a phone gets the full width)",
   "width:auto" in r and "max-width:100%" in r, r)
ck("3 on a wide screen at most 540px high, centred",
   "max-height:540px" in r and "margin-inline:auto" in r, r)
ck("4 the old full-width 400px band is gone", "max-height:400px;object-fit:cover" not in css)
tpl = io.open("site_src/templates/article.html", encoding="utf-8").read()
ck("5 the article template still renders the hero as .a-img", 'class="a-img"' in tpl)

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
