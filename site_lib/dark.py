# -*- coding: utf-8 -*-
"""«الوضع الليلي» (2026-11-27): the dark theme, GENERATED from the light one.

WHY generated: style.css holds ~400 colours written straight into ~1,900
rules. A hand-written dark sheet would be a second stylesheet to keep in
step for ever; this reads the light sheet at build time and writes, for
every rule that paints a light surface or dark text, the same rule under
html[data-theme=dark] with the colour moved. A rule added tomorrow gets its
dark twin with no further work.

OPT-IN: the reader switches it on (the footer's button, kept in the
browser's localStorage). It never follows the device by itself - a theme
nobody has looked at on every page is not shipped as the default.

The rules, all on the colour's lightness (HSL):
  * a SURFACE (background, border, outline, shadow) lighter than SURF_MIN
    becomes a dark one of the same hue - white -> the card tone, a tint a
    shade lighter than the card, a pastel chip a dark chip of its colour;
  * TEXT (color, fill, stroke) darker than TEXT_MAX becomes light text of
    the same hue;
  * a mid or saturated surface (a blue button, a yellow badge) is LEFT, and
    the rule that paints it keeps its own dark text - or gets dark text
    written in, when it relied on the page's ink;
  * translucent colours are left (they sit over a photo or the blue header);
  * the footer (dark already) and anything over a photo are left: SKIP. The
    blue header needs no entry: its whites are translucent or text.
The five theme variables are set by hand at the top (VARS).
"""
import colorsys
import re

ROOT = "html[data-theme=dark]"
VARS = ("--ink:#e6edf6;--muted:#9db0c8;--card:#161f30;--bg:#0b1220;--line:#27344a;"
        "--fin:#94a3b8;--up:#7ab8ff")
SURF_MIN = 0.80          # a surface this light is repainted dark
TEXT_MAX = 0.45          # text this dark is repainted light
KEEP_LO, KEEP_HI = 0.50, 0.80     # a surface in this band is kept: its text must stay dark
INK = "#0f172a"
LINK = "#6cc0ee"         # var(--green-d) / var(--green-b) as TEXT on a dark surface
# selectors that stay as they are: the footer (dark already), text and veils laid over a photo
SKIP = (".site-foot", ".foot-links", ".credit", ".hero", ".a-credit", ".ad-top")
# classes the scripts put on <html> ITSELF (shot_js, the team card's scroll
# lock): «.shot-on .comp-shot» has no ancestor to hang the theme on, so the
# theme joins the same element - html[data-theme=dark].shot-on .comp-shot
ROOT_CLASSES = (".shot-on", ".lt-lock")
_LINK_VAR = re.compile(r"var\(--green-[db](?:,[^)]*)?\)")     # with or without a fallback colour
TEXT_PROPS = ("color", "fill", "stroke", "caret-color", "text-decoration-color", "-webkit-text-fill-color")
SURF_PREFIX = ("background", "border", "outline", "box-shadow", "column-rule")
_COL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\bwhite\b|\bblack\b")


def _rgba(tok):
    """(r, g, b, alpha) in 0..1, or None for a token we do not read."""
    t = tok.strip().lower()
    if t == "white":
        return (1.0, 1.0, 1.0, 1.0)
    if t == "black":
        return (0.0, 0.0, 0.0, 1.0)
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return None
        v = [int(h[i:i + 2], 16) / 255 for i in range(0, len(h), 2)]
        return (v[0], v[1], v[2], v[3] if len(v) == 4 else 1.0)
    m = re.match(r"rgba?\(([^)]*)\)", t)
    if not m:
        return None
    parts = [p for p in re.split(r"[,\s/]+", m.group(1).strip()) if p]
    if len(parts) < 3:
        return None
    try:
        r, g, b = (float(p.rstrip("%")) / (100 if p.endswith("%") else 255) for p in parts[:3])
        a = 1.0 if len(parts) < 4 else (float(parts[3].rstrip("%")) / 100 if parts[3].endswith("%") else float(parts[3]))
    except ValueError:
        return None
    return (r, g, b, a)


def _hex(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x * 255))) for x in (r, g, b))


def lightness(tok):
    c = _rgba(tok)
    return None if c is None else colorsys.rgb_to_hls(*c[:3])[1]


def surface(tok):
    """The dark twin of a light surface colour; the token itself otherwise."""
    c = _rgba(tok)
    if c is None or c[3] < 1.0:
        return tok
    h, l, s = colorsys.rgb_to_hls(*c[:3])
    if l < SURF_MIN:
        return tok
    if s < 0.08:
        h, s = 0.61, 0.35          # white and the greys take the card's slate, not a flat grey
    return _hex(*colorsys.hls_to_rgb(h, 0.13 + (1.0 - l) * 0.9, min(s, 0.35)))


def text(tok):
    """The light twin of a dark text colour; the token itself otherwise."""
    c = _rgba(tok)
    if c is None or c[3] < 1.0:
        return tok
    h, l, s = colorsys.rgb_to_hls(*c[:3])
    if l > TEXT_MAX:
        return tok
    return _hex(*colorsys.hls_to_rgb(h, 0.92 - l * 0.55, s * 0.8))


def _decls(body):
    """Split a rule's body on the ';' that are not inside brackets or quotes
    (a data: URI carries its own)."""
    out, depth, quote, cur = [], 0, "", []
    for ch in body:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return [d.strip() for d in out if ":" in d]


def _role(prop):
    if prop in TEXT_PROPS:
        return "text"
    if prop.startswith(SURF_PREFIX):
        return "surface"
    return ""


def rule(selector, body):
    """The dark twin of one rule ("" when nothing in it changes)."""
    sel = selector.strip()
    if not sel or sel.startswith(("@", ":root")) or any(k in sel for k in SKIP):
        return ""
    decls = [(d.split(":", 1)[0].strip().lower(), d.split(":", 1)[1].strip()) for d in _decls(body)]
    # does this rule paint a surface we keep light-ish (a yellow badge)? then
    # the text on it stays dark
    kept_light = False
    for prop, val in decls:
        if prop in ("background", "background-color") and "url(" not in val and "gradient" not in val:
            m = _COL.search(val)
            c = _rgba(m.group(0)) if m else None
            if c and c[3] == 1.0 and KEEP_LO <= colorsys.rgb_to_hls(*c[:3])[1] < KEEP_HI:
                kept_light = True
    out, has_color = [], False
    for prop, val in decls:
        role = _role(prop)
        if prop == "color":
            has_color = True
        if not role or "url(" in val:
            continue
        if role == "text":
            if kept_light:
                if "var(--ink)" in val or "var(--muted)" in val:
                    out.append(f"{prop}:{INK}")
                continue
            new = _COL.sub(lambda m: text(m.group(0)), _LINK_VAR.sub(LINK, val))
        else:
            new = _COL.sub(lambda m: surface(m.group(0)), val)
        if new != val:
            out.append(f"{prop}:{new}")
    if kept_light and not has_color:
        out.append(f"color:{INK}")
    if not out:
        return ""
    sels = ",".join(_under_root(s.strip()) for s in sel.split(",") if s.strip())
    return f"{sels}{{{';'.join(out)}}}"


def _under_root(s):
    for c in ROOT_CLASSES:
        if s.startswith(c) and s[len(c):len(c) + 1] in (" ", ">", ""):
            return f"{ROOT}{s}"
    if s.startswith(("html", "body")):
        return f"{ROOT}{s[4:]}" if s.startswith("html") else f"{ROOT} {s}"
    return f"{ROOT} {s}"


def _block_end(css, i):
    """The index just after the '}' that closes the '{' at css[i]."""
    depth = 0
    for j in range(i, len(css)):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(css)


def _walk(css):
    out, i = [], 0
    while True:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        end = _block_end(css, j)
        inner = css[j + 1:end - 1]
        if prelude.startswith(("@media", "@supports")):
            sub = _walk(inner)
            if sub:
                out.append(f"{prelude}{{{sub}}}")
        elif not prelude.startswith("@"):
            r = rule(prelude, inner)
            if r:
                out.append(r)
        i = end
    return "".join(out)


def dark_css(css):
    """The dark theme for the (minified, comment-free) light stylesheet."""
    return f"{ROOT}{{{VARS};color-scheme:dark}}" + _walk(css)


# ---- the switch -----------------------------------------------------------
# In <head>, before the stylesheet paints: a reader who chose the dark theme
# never sees a white flash.
HEAD_JS = "try{if(localStorage.getItem('theme')==='dark')document.documentElement.setAttribute('data-theme','dark')}catch(e){}"
# The footer's button: [hidden] until the script finds storage it can use.
BUTTON = '<button type="button" class="theme-btn" hidden aria-pressed="false">🌙 الوضع الليلي</button>'
BUTTON_JS = """<script>
(function(){
  var b=document.querySelector('.theme-btn'); if(!b) return;
  var LS; try{ LS=window.localStorage; LS.setItem('_t','1'); LS.removeItem('_t'); }catch(e){ return; }
  var root=document.documentElement;
  function paint(){ var on=root.getAttribute('data-theme')==='dark';
    b.setAttribute('aria-pressed',on?'true':'false'); b.textContent=on?'☀️ الوضع الفاتح':'🌙 الوضع الليلي'; }
  b.hidden=false; paint();
  b.addEventListener('click',function(){
    var on=root.getAttribute('data-theme')==='dark';
    if(on){ root.removeAttribute('data-theme'); LS.removeItem('theme'); }
    else { root.setAttribute('data-theme','dark'); LS.setItem('theme','dark'); }
    paint();
  });
})();
</script>"""
