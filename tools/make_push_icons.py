# -*- coding: utf-8 -*-
"""The icons web push needs, drawn from the favicon's own geometry.

    python tools/make_push_icons.py

  icon-192.png / icon-512.png  the home-screen icon (manifest.webmanifest) and
                               the notification's big icon: our ball on a
                               brand-blue square. "maskable": Android crops an
                               installed icon to a circle or a squircle, and
                               only the centre 80% is guaranteed to survive, so
                               the ball sits inside that safe zone.
  badge-96.png                 the tiny status-bar badge. Android draws ONLY
                               its alpha channel (as a white glyph), so a
                               colour icon there becomes a white blob. This is
                               the ball's white leather as opaque pixels and
                               the navy panels + rim as holes - a ball, not a
                               disc.

Generated, not hand-drawn, for the same reason as the favicon: there is no SVG
renderer on this machine, and one geometry keeps every icon the same ball.
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_favicon import BLUE, OUT, draw   # noqa: E402

BALL_SHARE = 0.72          # ball diameter / icon side: inside the 80% safe zone


def square_icon(size):
    im = Image.new("RGBA", (size, size), BLUE)
    d = int(round(size * BALL_SHARE))
    ball = draw(d)
    off = (size - d) // 2
    im.alpha_composite(ball, (off, off))
    return im.convert("RGB")


def badge(size):
    ball = draw(size)
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    src, dst = ball.load(), out.load()
    for y in range(size):
        for x in range(size):
            r, g, b, a = src[x, y]
            # white leather: every channel high. Navy (19,41,61) and the blue
            # rim (31,148,211) both have a LOW red channel, so red alone
            # separates them from white - and keeps the anti-aliased edges.
            dst[x, y] = (255, 255, 255, a * r // 255)
    return out


def main():
    for name, im in (("icon-192.png", square_icon(192)),
                     ("icon-512.png", square_icon(512)),
                     ("badge-96.png", badge(96))):
        p = os.path.join(OUT, name)
        im.save(p, optimize=True)
        print("%-14s %6d bytes  %s" % (name, os.path.getsize(p), im.size))


if __name__ == "__main__":
    main()
