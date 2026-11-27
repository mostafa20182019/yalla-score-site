# -*- coding: utf-8 -*-
"""«الوضع الليلي» (2026-11-27): the dark theme is generated from the light
stylesheet (site_lib/dark.py) and the reader switches it on.

    python tests/test_dark_mode.py     (from the repo root)
"""
import colorsys, io, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib import dark as D

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

def L(c):
    return D.lightness(c)

# ---------------------------------------------------------------- the colour rules
ck("1 a light surface becomes a dark one; white lands on the card's slate, not a flat grey",
   L(D.surface("#fff")) < 0.2 and L(D.surface("#f1f5f9")) < 0.25 and D.surface("#fff") == D.surface("white")
   and colorsys.rgb_to_hls(*D._rgba(D.surface("#fff"))[:3])[2] > 0.2, D.surface("#fff"))
ck("2 a tint stays a shade apart from the card, so a hover or a stripe still shows",
   L(D.surface("#fff")) < L(D.surface("#f8fafc")) < L(D.surface("#e2e8f0")))
ck("3 a pastel chip keeps its colour, dark", D.surface("#dcfce7") != D.surface("#fee2e2") and L(D.surface("#fee2e2")) < 0.3)
ck("4 a mid or saturated surface is left (the blue button, the yellow card)",
   D.surface("#1f94d3") == "#1f94d3" and D.surface("#fbbf24") == "#fbbf24" and D.surface("#0b1220") == "#0b1220")
ck("5 dark text becomes light text of its hue; light text is left",
   L(D.text("#0f172a")) > 0.8 and L(D.text("#15803d")) > 0.6 and D.text("#fff") == "#fff" and D.text("#94a3b8") == "#94a3b8")
ck("6 a translucent colour is never touched (it sits over a photo or the blue header)",
   D.surface("rgba(255,255,255,.85)") == "rgba(255,255,255,.85)" and D.text("rgba(15,23,42,.6)") == "rgba(15,23,42,.6)")

# ---------------------------------------------------------------- one rule
r = D.rule(".card", "background:#fff;border:1px solid #e2e8f0;color:#0f172a;padding:4px")
ck("7 a rule's twin holds only what changed, under the theme", r.startswith("html[data-theme=dark] .card{") and "padding" not in r
   and r.count(":") == 3, r)
ck("8 every selector of a list gets the theme", D.rule(".a,.b", "background:#fff").startswith("html[data-theme=dark] .a,html[data-theme=dark] .b{"))
ck("9 nothing to change: no rule", D.rule(".x", "display:flex;color:#fff;background:#1f94d3") == "")
y = D.rule(".badge", "background:#fbbf24;color:var(--ink)")
ck("10 text on a surface we keep light stays dark - written in when the rule relied on the page's ink",
   y == "html[data-theme=dark] .badge{color:#0f172a}" and D.rule(".b2", "background:#fbbf24") == "html[data-theme=dark] .b2{color:#0f172a}", y)
ck("11 a link colour from the theme's blue turns light on the dark surface, with or without a fallback",
   D.rule(".l", "color:var(--green-d)") == "html[data-theme=dark] .l{color:#6cc0ee}"
   and D.rule(".l", "color:var(--green-d, #15658f)") == "html[data-theme=dark] .l{color:#6cc0ee}")
ck("12 the footer and what sits over a photo are left", D.rule(".site-foot", "background:#fff") == "" and D.rule(".hero-t", "color:#0f172a") == "")
ck("13 a data: image is not read as colours", D.rule(".i", 'background:url("data:image/svg+xml;utf8,<svg fill=\'#fff\'/>") #fff') == "")
ck("14 a class the scripts put on <html> itself joins the theme on the same element",
   D.rule(".shot-on .comp-shot", "background:#fff").startswith("html[data-theme=dark].shot-on .comp-shot{")
   and D.rule(".shot-only", "background:#fff").startswith("html[data-theme=dark] .shot-only{"))

# ---------------------------------------------------------------- the sheet
css = ".a{background:#fff}@media(max-width:600px){.a{color:#0f172a}.b{display:none}}@keyframes k{from{background:#fff}to{background:#000}}"
d = D.dark_css(css)
ck("15 the theme's variables come first, with color-scheme", d.startswith("html[data-theme=dark]{--ink:") and "color-scheme:dark}" in d)
ck("16 a media query keeps its wrapper; an empty one and @keyframes give nothing",
   "@media(max-width:600px){html[data-theme=dark] .a{color:" in d and "keyframes" not in d and ".b" not in d, d)
from site_lib.text import css_min
real = css_min(io.open("site_src/style.css", encoding="utf-8").read())
dk = D.dark_css(real)
ck("17 the real sheet: balanced braces, every rule under the theme, a few hundred rules",
   dk.count("{") == dk.count("}") and 250 < dk.count("html[data-theme=dark]") < 900
   and not re.search(r"(^|})(?!html\[data-theme=dark\]|@media|@supports|html\[data-theme=dark\])[^@}]", dk.replace("}}", "}")), str(dk.count("html[data-theme=dark]")))
ck("18 the light sheet is not changed by a byte: the theme is added after it",
   "dark_css(_css)" in io.open("site_pages/files.py", encoding="utf-8").read() and "data-theme" not in real)

# ---------------------------------------------------------------- the switch
sh = io.open("site_lib/shell.py", encoding="utf-8").read()
ck("19 the choice is read in <head>, before the stylesheet: no white flash",
   sh.index("<script>{_DARK.HEAD_JS}</script>") < sh.index('<link rel="stylesheet" href="/assets/style.css'))
ck("20 opt-in only: the theme never follows the device by itself",
   "prefers-color-scheme" not in real and "prefers-color-scheme" not in D.HEAD_JS and "prefers-color-scheme" not in D.BUTTON_JS)
ck("21 the footer's button is hidden until the script finds storage it can use; the script is in app.js",
   " hidden " in D.BUTTON and "{_DARK.BUTTON}" in sh and "_js_body(_DARK.BUTTON_JS)" in sh and "b.hidden=false" in D.BUTTON_JS)
ck("22 the script fails quietly without storage and keeps the choice under one key",
   "catch(e){ return; }" in D.BUTTON_JS and D.BUTTON_JS.count("'theme'") == 2 and "getItem('theme')==='dark'" in D.HEAD_JS)

dist = os.path.join(os.getcwd(), "dist")
if os.path.isfile(os.path.join(dist, "assets", "style.css")):
    built = io.open(os.path.join(dist, "assets", "style.css"), encoding="utf-8").read()
    home = io.open(os.path.join(dist, "index.html"), encoding="utf-8").read()
    ck("23 the built stylesheet carries the theme once, after the light rules",
       built.count("html[data-theme=dark]{--ink:") == 1 and built.index("html[data-theme=dark]{") > len(built) * 0.6)
    ck("24 every page has the head script and the footer's button", "getItem('theme')==='dark'" in home and 'class="theme-btn"' in home)
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
