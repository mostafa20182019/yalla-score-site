# -*- coding: utf-8 -*-
"""Redraw the favicon as OUR ball, filling the whole canvas.

What was wrong: the icon was the ball INVERTED - a solid brand-blue disc with
white panels - while the ball everyone sees on the site (the app icon, the
header) is WHITE with dark navy panels. And in Google's chip it sat small with
padding around it instead of filling the circle.

This draws the app-icon ball edge to edge: white disc across the full canvas,
navy centre pentagon, five navy spokes, and a brand-blue rim right at the edge.
The rim is not decoration - Google renders the favicon on white, and without it
a white ball has no outline at all.

Drawn at 8x and downsampled, which is how you get clean anti-aliased edges out
of Pillow without an SVG renderer (there is none on this machine).
"""
import io
import math
import os

from PIL import Image, ImageDraw

OUT = r"F:\yalla-score-site\assets-src"
BLUE = (31, 148, 211, 255)     # #1f94d3, the brand
NAVY = (19, 41, 61, 255)       # #13293d, the panels on the app icon
WHITE = (255, 255, 255, 255)

S = 8                          # supersample factor
N = 128                        # design units
C = N / 2.0

R_BALL = 64.0                  # the ball IS the canvas - no padding
R_RIM = 62.0                   # rim centre-line, so its outer edge touches 64
W_RIM = 5.0
R_PENT = 34.0                  # centre pentagon
R_SPOKE = 56.0                 # spokes stop inside the rim
W_SPOKE = 10.0


def pent_points(r, rot=-90.0):
    return [(C + r * math.cos(math.radians(rot + i * 72)),
             C + r * math.sin(math.radians(rot + i * 72))) for i in range(5)]


def draw(size):
    px = size * S
    im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = px / float(N)                      # design units -> pixels

    def xy(p):
        return (p[0] * k, p[1] * k)

    # the ball, filling everything
    d.ellipse([(C - R_BALL) * k, (C - R_BALL) * k,
               (C + R_BALL) * k, (C + R_BALL) * k], fill=WHITE)

    inner = pent_points(R_PENT)
    outer = pent_points(R_SPOKE)

    # spokes first, so the pentagon caps them cleanly
    for a, b in zip(inner, outer):
        d.line([xy(a), xy(b)], fill=NAVY, width=int(round(W_SPOKE * k)))
        # round the far end
        rr = W_SPOKE * k / 2.0
        d.ellipse([b[0] * k - rr, b[1] * k - rr, b[0] * k + rr, b[1] * k + rr],
                  fill=NAVY)

    d.polygon([xy(p) for p in inner], fill=NAVY)

    # the brand rim, last, right at the edge
    d.ellipse([(C - R_RIM) * k, (C - R_RIM) * k,
               (C + R_RIM) * k, (C + R_RIM) * k],
              outline=BLUE, width=int(round(W_RIM * k)))

    return im.resize((size, size), Image.LANCZOS)


png192 = draw(192)
png192.save(os.path.join(OUT, "favicon.png"))

# the .ico Google's fetcher asks for directly; several sizes in one file so a
# 16px tab and a 48px bookmark each get a sharp one
ico = draw(256)
ico.save(os.path.join(OUT, "favicon.ico"),
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

for f in ("favicon.png", "favicon.ico"):
    p = os.path.join(OUT, f)
    print("%-18s %6d bytes  %s" % (f, os.path.getsize(p), Image.open(p).size))
