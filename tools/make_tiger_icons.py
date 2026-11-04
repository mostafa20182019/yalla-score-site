# -*- coding: utf-8 -*-
"""The tiger - Yalla Score's mark since 2026-11-04 (user: «انا هستخدم الصورة d
... بس فى الموقع خليه باصص شمال»). Replaces the ball (tools/make_favicon.py).

    python tools/make_tiger_icons.py

One geometry, drawn here as SVG, every file below rendered from it:

  assets-src/favicon.svg        the source, facing LEFT (the site is RTL)
  assets-src/favicon.png  192   header logo + <link rel=icon>
  assets-src/favicon.ico        16/32/48/64 - /favicon.ico for Google's fetcher
  assets-src/logo.png     192   publisher logo (NewsArticle / RSS)
  assets-src/icon-192.png       home-screen + notification icon. "maskable":
  assets-src/icon-512.png       Android keeps only the centre 80%, so the head
                                is drawn smaller there
  assets-src/badge-96.png       status-bar badge: Android draws only the ALPHA,
                                so it is a white glyph with the stripes as holes
  assets-src/app-icon-1024.png  the brand corner on the Facebook cards
  assets-src/brand-tiger.png 128  the header logo: the head alone, transparent
  assets-src/fb-profile-1024.png  facing RIGHT - for the Facebook page photo,
                                uploaded by hand

An original drawing: a tiger head in profile, flat colours, white outline on a
gradient tile - the STYLE of a league crest, none of anyone's artwork. Rendered
with headless Edge (the machine has no other SVG renderer) at 1024 px, then
downsampled with Pillow.
"""
import io
import os
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets-src")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

OR, DK, WH = "#f58220", "#1b1f2a", "#ffffff"
HEAD = ("M132 176 C120 116 174 84 214 116 C254 94 316 92 352 112 C368 86 408 82 418 118 "
        "C424 140 420 160 412 172 C432 186 446 206 454 228 L486 276 C492 292 486 306 472 310 "
        "L474 330 C470 346 458 352 446 350 L396 360 L438 390 C438 408 420 420 396 422 "
        "C376 436 344 444 318 438 L298 464 L278 434 L248 458 L232 422 L198 442 L190 402 L152 414 L156 372 "
        "L114 370 L134 332 L98 318 L128 288 L102 258 L132 238 C118 214 120 190 132 176 Z")
def art(bw=False):
    """the tiger, facing RIGHT. bw=True: white glyph with black holes (for the badge alpha)."""
    o, d, w = (WH, "#000", "#000") if bw else (OR, DK, WH)
    g = [f'<path fill="{o}" stroke="#fff" stroke-width="{0 if bw else 16}" stroke-linejoin="round" paint-order="stroke" d="{HEAD}"/>']
    if not bw:
        g.append(f'<g clip-path="url(#hc)"><path fill="{w}" d="M392 252 C432 250 470 268 500 290 L500 520 L300 520 '
                 f'C318 470 340 420 352 380 C356 330 370 280 392 252 Z"/>'
                 f'<path fill="{w}" d="M318 204 L422 184 L416 198 L328 218 Z"/></g>')
    g.append(f'<path fill="{d}" d="M152 164 C150 132 178 114 198 128 C178 136 162 148 152 164 Z"/>')
    for s in ["M290 118 L314 178 L274 132 Z", "M246 118 L284 194 L230 134 Z", "M202 144 L254 212 L186 160 Z",
              "M140 250 L256 274 L146 288 Z", "M126 300 L266 316 L136 336 Z", "M150 352 L274 352 L168 382 Z",
              "M196 404 L288 392 L214 422 Z"]:
        g.append(f'<path fill="{d}" d="{s}"/>')
    if bw:
        g.append(f'<path fill="#000" d="M322 240 C340 214 378 202 414 206 L400 224 C376 240 348 248 322 240 Z"/>')
    else:
        g.append(f'<path fill="#ffd54a" stroke="{DK}" stroke-width="8" stroke-linejoin="round" '
                 f'd="M322 240 C340 214 378 202 414 206 L400 224 C376 240 348 248 322 240 Z"/>')
        g.append(f'<ellipse cx="372" cy="226" rx="7" ry="11" fill="{DK}"/>')
        g.append(f'<path fill="{DK}" d="M450 270 L486 280 L480 302 C466 306 450 296 450 270 Z"/>')
        g.append(f'<path fill="none" stroke="{DK}" stroke-width="7" stroke-linecap="round" d="M472 306 C462 320 446 326 428 324"/>')
        g.append(f'<path fill="{WH}" stroke="{DK}" stroke-width="4" stroke-linejoin="round" d="M456 348 L442 388 L428 352 Z"/>')
        # dark contour INSIDE the white outline: keeps the white muzzle from melting into the outline
        g.append(f'<path fill="none" stroke="{DK}" stroke-width="6" stroke-linejoin="round" d="{HEAD}"/>')
    return "".join(g)
def svg(left=True, bg=True, bw=False, scale=0.94):
    defs = (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1565c0"/>'
            f'<stop offset="1" stop-color="#29b6f6"/></linearGradient><clipPath id="hc"><path d="{HEAD}"/></clipPath></defs>')
    t = []
    if scale != 1.0:
        t.append(f"translate(256 256) scale({scale}) translate(-256 -256)")
    if left:
        t.append("translate(512 0) scale(-1 1)")
    t.append("translate(-36 -18)")   # the head's box is x 98-486, y 84-464: centre it
    tr = f' transform="{" ".join(t)}"' if t else ""
    back = '<rect width="512" height="512" fill="url(#bg)"/>' if bg else ('<rect width="512" height="512" fill="#000"/>' if bw else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{defs}{back}'
            f'<g{tr}>{art(bw)}</g></svg>')

def render(svg_text, size=1024, transparent=False):
    """SVG -> RGBA PIL image via headless Edge (transparent=True keeps the alpha)."""
    with tempfile.TemporaryDirectory() as tmp:
        sp = os.path.join(tmp, "t.svg")
        hp = os.path.join(tmp, "t.html")
        pp = os.path.join(tmp, "t.png")
        with open(sp, "w", encoding="utf-8") as f:
            f.write(svg_text)
        with open(hp, "w", encoding="utf-8") as f:
            f.write(f'<html><body style="margin:0;background:{"transparent" if transparent else "#000"}">'
                    f'<img src="t.svg" width="{size}" height="{size}" style="display:block"></body></html>')
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        *(["--default-background-color=00000000"] if transparent else []),
                        f"--window-size={size},{size}", f"--screenshot={pp}",
                        "file:///" + hp.replace("\\", "/")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # msedge.exe hands off to a browser process and returns before the
        # screenshot is written - wait for the file to appear and settle
        import time
        last = -1
        for _ in range(100):
            time.sleep(0.2)
            if os.path.exists(pp) and os.path.getsize(pp) == last and last > 0:
                break
            last = os.path.getsize(pp) if os.path.exists(pp) else -1
        im = Image.open(pp).convert("RGBA")
        im.load()
        return im.crop((0, 0, size, size))


def main():
    with open(os.path.join(OUT, "favicon.svg"), "w", encoding="utf-8") as f:
        f.write(svg(left=True))
    left = render(svg(left=True))
    mask = render(svg(left=True, scale=0.76))          # inside the 80% safe zone
    right = render(svg(left=False))
    glyph = render(svg(left=True, bg=False, bw=True, scale=0.92)).convert("L")
    out = {}
    out["favicon.png"] = left.resize((192, 192), Image.LANCZOS)
    out["logo.png"] = out["favicon.png"]
    out["icon-192.png"] = mask.resize((192, 192), Image.LANCZOS).convert("RGB")
    out["icon-512.png"] = mask.resize((512, 512), Image.LANCZOS).convert("RGB")
    out["app-icon-1024.png"] = left.convert("RGB")
    out["fb-profile-1024.png"] = right.convert("RGB")
    badge = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
    badge.putalpha(glyph.resize((96, 96), Image.LANCZOS))
    out["badge-96.png"] = badge
    # the header logo (2026-11-04: «كبر اللوجو»): the head alone, no tile,
    # trimmed to its outline so 46 px of header shows 46 px of tiger
    head = render(svg(left=True, bg=False, scale=1.0), transparent=True)
    head = head.crop(head.getbbox())
    side = max(head.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(head, ((side - head.size[0]) // 2, (side - head.size[1]) // 2))
    out["brand-tiger.png"] = sq.resize((128, 128), Image.LANCZOS)
    for name, im in out.items():
        im.save(os.path.join(OUT, name))
    left.resize((256, 256), Image.LANCZOS).save(
        os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    for name in list(out) + ["favicon.ico", "favicon.svg"]:
        p = os.path.join(OUT, name)
        print("%-22s %7d bytes" % (name, os.path.getsize(p)))


if __name__ == "__main__":
    sys.exit(main())
