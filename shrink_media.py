"""Bring media/ down to web size, in place, without touching a filename.

    python shrink_media.py --dry     # what would change, changes nothing
    python shrink_media.py           # do it

Measured 2026-09-20: 240 photos, 75 MB, 323 KB on average, 96 of them over
300 KB and three over a megabyte — the biggest a 4544x2452, 3.2 MB hero on an
article page. On an Egyptian mobile connection that single image is the page.

Rules, and each exists for a reason:
  - A FILENAME IS NEVER CHANGED. Every article's image_url points at
    media/<name>, the CC credit line is keyed to it, and published Facebook
    posts scraped it. Renaming breaks all three (see the image-filenames note
    in memory). Files are rewritten in place.
  - Never upscale, never touch what is already fine (MAX_W wide or narrower
    AND under BAR bytes).
  - Never re-encode a file the pass would not actually shrink: if the new
    bytes are not at least MIN_GAIN smaller, keep the original. Re-encoding a
    JPEG always loses a little; doing it for nothing is pure loss.
  - EXIF orientation is applied before resizing, then dropped with the rest of
    the metadata (a rotated hero that renders sideways is worse than a big one).
  - SVG is skipped: our own placeholders, already tiny, and not raster.

Idempotent: run it twice and the second run reports nothing to do, which is
what makes it safe to wire into the publish workflow for newly downloaded
photos.
"""
import argparse
import glob
import io
import os
import sys

from PIL import Image, ImageOps

sys.stdout.reconfigure(encoding="utf-8")   # cp1252 console: the arrow below is not ASCII

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(HERE, "media")
MAX_W = 1600          # wider than any slot the site renders (the hero is 1544)
QUALITY = 82          # visually indistinguishable from 95 on photographs
BAR = 250 * 1024      # a photo bigger than this is worth a look
MIN_GAIN = 0.05       # skip a rewrite that saves less than 5%


def plan(path):
    """(needs_work, width, height, bytes) without decoding the whole file."""
    size = os.path.getsize(path)
    with Image.open(path) as im:
        w, h = im.size
    return (w > MAX_W or size > BAR), w, h, size


def shrink(path, dry=False):
    """Returns (before, after) bytes; after == before when nothing was done."""
    needs, w, h, before = plan(path)
    if not needs:
        return before, before
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)          # honour the camera's rotation
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)),
                           Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    after = buf.getbuffer().nbytes
    if after >= before * (1 - MIN_GAIN):
        return before, before                     # not worth the re-encode
    if not dry:
        with open(path, "wb") as f:
            f.write(buf.getvalue())
    return before, after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="only the summary")
    args = ap.parse_args()
    files = sorted(f for f in glob.glob(os.path.join(MEDIA, "*"))
                   if os.path.splitext(f)[1].lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not files:
        print("no media to shrink")
        return 0
    done = saved = total_before = 0
    for f in files:
        before, after = shrink(f, args.dry)
        total_before += before
        if after < before:
            done += 1
            saved += before - after
            if not args.quiet:
                print(f"  {os.path.basename(f)[:44]:46} {before / 1024:7.0f} → {after / 1024:6.0f} KB")
    verb = "would shrink" if args.dry else "shrank"
    print(f"{verb} {done} of {len(files)} photos: "
          f"{total_before / 1048576:.1f} MB → {(total_before - saved) / 1048576:.1f} MB "
          f"(saved {saved / 1048576:.1f} MB, {saved / total_before:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
