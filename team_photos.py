# -*- coding: utf-8 -*-
r"""The editor's team folders -> media/ + data/team_photos.json (2026-10-13).

    python team_photos.py            # copy + register every new credited photo
    python team_photos.py --check    # only say what would happen
    team_photos.cmd                  # the same, then shrink + commit + push

The user asked for one folder per curated club where HE drops photos, and for
the article pipeline to use them in that club's news. The folders live in
`team-photos/<slug>/` (slugs = the /team/<slug> club pages, plus `egypt` for
the national team). Each folder has a `credits.txt`; a photo is only usable
once a credit line exists for it, because the site never publishes a photo
without a licence line (the same rule media_credits.json enforces for the
Oracle library - see audit_images.py).

What one run does, per folder:
  1. reads credits.txt  -  `file | credit | year | subject`, or a `*` line
     that covers every file in the folder not named on its own line;
  2. for every image with a credit that is not registered yet: shrinks the
     SOURCE in place to web size (shrink_media's rules: 1600px, q82, never
     upscale), writes `media/<slug>-<ascii name>.jpg` and adds a record to
     data/team_photos.json (file, credit, subject, club, year, is_person,
     source, added);
  3. a photo already registered keeps its media/ file untouched (an article
     may be using it), but its credit/year/subject follow credits.txt, so a
     typo can be fixed without re-adding the photo;
  4. images with no credit are listed as WAITING and skipped.

Why a separate registry and not media_credits.json: that file is GENERATED
by the Oracle library (yalla_media.write_registry overwrites it whole), so
anything we added there would vanish on the next Oracle push.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import unicodedata

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(HERE, "team-photos")
MEDIA = os.path.join(HERE, "media")
REGISTRY = os.path.join(HERE, "data", "team_photos.json")
CREDITS = "credits.txt"
EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_W, QUALITY = 1600, 82          # the same numbers as shrink_media.py

# slug -> the Arabic name the site writes (clubs.TEAM_PAGES + the NT)
TEAMS = {
    "al-ahly": "الأهلي", "zamalek": "الزمالك", "pyramids": "بيراميدز",
    "egypt": "منتخب مصر",
    "real-madrid": "ريال مدريد", "barcelona": "برشلونة",
    "man-united": "مانشستر يونايتد", "man-city": "مانشستر سيتي",
    "arsenal": "أرسنال", "liverpool": "ليفربول", "chelsea": "تشيلسي",
    "trabzonspor": "طرابزون سبور",
}

# a subject that starts with one of these is a place or a thing, not a person
# (the living-story test only applies to people)
NOT_A_PERSON = ("ملعب", "استاد", "ستاد", "إستاد", "الاستاد", "جماهير", "مشجعو",
                "مشجعي", "شعار", "قميص", "كأس", "مقر", "لافتة", "مدرجات", "درع")

WHY = ("Photos the editor put by hand into team-photos/<club>/ and team_photos.py "
       "copied into media/ with the credit he wrote in that folder's credits.txt. "
       "A media/ file is usable only when a credit for it lives here, in "
       "data/media_credits.json or in data/articles.json. Generated; do not hand-edit.")


# ----------------------------------------------------------------- credits
def read_credits(folder):
    """credits.txt -> ({file: (credit, year, subject)}, default_or_None).

    A line is `file | credit | year | subject`; year and subject optional.
    `*` as the file names the folder default. `#` starts a comment."""
    path = os.path.join(folder, CREDITS)
    per, default = {}, None
    if not os.path.exists(path):
        return per, default
    with open(path, encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2 or not parts[1]:
                continue
            name = parts[0]
            year = None
            if len(parts) > 2 and parts[2]:
                m = re.search(r"\d{4}", parts[2])
                year = int(m.group()) if m else None
            subject = parts[3] if len(parts) > 3 and parts[3] else None
            rec = (parts[1], year, subject)
            if name == "*":
                default = rec
            else:
                per[name] = rec
    return per, default


def credit_for(name, per, default):
    return per.get(name) or default


# ------------------------------------------------------------------ naming
def media_name(slug, name):
    """`<slug>-<ascii stem>.jpg`; a stem with nothing ascii in it (an Arabic
    filename from the user's phone) becomes a short hash so two such photos
    never collide. The slug prefix is honest here: a photo in the club's
    folder shows that club (the prompts' filename rule)."""
    stem = os.path.splitext(name)[0]
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    ascii_stem = re.sub(r"[^a-z0-9]+", "-", ascii_stem.lower()).strip("-")
    if len(ascii_stem) < 3:
        ascii_stem = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{ascii_stem}.jpg"


# ----------------------------------------------------------------- imaging
def _same_bytes(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    h = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()
    return h(a) == h(b)


def _web_bytes(path):
    """The photo at web size as JPEG bytes (EXIF rotation applied, RGB,
    at most MAX_W wide, never upscaled)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def shrink_source(path):
    """Shrink the user's own copy in place when it is bigger than the web size,
    so the repo never stores a 5 MB phone photo twice. Same rules as
    shrink_media.shrink: only when wider than MAX_W or heavier than 300 KB,
    and only when the re-encode actually gains 5%."""
    before = os.path.getsize(path)
    with Image.open(path) as im:
        w = im.width
    if w <= MAX_W and before <= 300 * 1024:
        return before, before
    data = _web_bytes(path)
    if len(data) >= before * 0.95:
        return before, before
    if path.lower().endswith((".png", ".webp")):
        # JPEG bytes under a .png name would lie about the content type
        return before, before
    with open(path, "wb") as f:
        f.write(data)
    return before, len(data)


# ---------------------------------------------------------------- registry
def load_registry(path=REGISTRY):
    if not os.path.exists(path):
        return {"_why": WHY, "generated_at": None, "photos": []}
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh) or {}
    d.setdefault("photos", [])
    d["_why"] = WHY
    return d


def save_registry(d, path=REGISTRY):
    d["photos"] = sorted(d["photos"], key=lambda p: p["file"])
    d["generated_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


# -------------------------------------------------------------------- sync
def scan(folder_root=FOLDER, teams=TEAMS):
    """[(slug, club, folder, [image names])] for every known folder present."""
    out = []
    if not os.path.isdir(folder_root):
        return out
    for slug in sorted(os.listdir(folder_root)):
        folder = os.path.join(folder_root, slug)
        if not os.path.isdir(folder):
            continue
        club = teams.get(slug)
        if not club:
            print(f"  ?    team-photos/{slug}: not a known club folder (see TEAMS) - skipped")
            continue
        imgs = sorted(f for f in os.listdir(folder)
                      if os.path.splitext(f)[1].lower() in EXTS
                      and os.path.isfile(os.path.join(folder, f)))
        out.append((slug, club, folder, imgs))
    return out


def sync(folder_root=FOLDER, media=MEDIA, registry_path=REGISTRY, teams=TEAMS,
         check=False):
    """Returns {"added": [...], "updated": [...], "waiting": [...], "kept": n}."""
    reg = load_registry(registry_path)
    by_source = {p.get("source"): p for p in reg["photos"]}
    by_file = {p["file"] for p in reg["photos"]}
    today = dt.date.today().isoformat()
    res = {"added": [], "updated": [], "waiting": [], "kept": 0}

    for slug, club, folder, imgs in scan(folder_root, teams):
        per, default = read_credits(folder)
        for name in imgs:
            source = f"team-photos/{slug}/{name}"
            rec = credit_for(name, per, default)
            if not rec:
                res["waiting"].append(source)
                continue
            credit, year, subject = rec
            subject = subject or club
            is_person = subject != club and not subject.startswith(NOT_A_PERSON)
            entry = by_source.get(source)
            if entry:
                changed = (entry.get("credit"), entry.get("year"), entry.get("subject")) \
                          != (credit, year, subject)
                if changed:
                    entry.update(credit=credit, year=year, subject=subject,
                                 is_person=is_person)
                    res["updated"].append(source)
                else:
                    res["kept"] += 1
                continue
            # A photo that already lives in media/ under this very name with
            # the very same bytes (the vetted photos our articles used, seeded
            # into the folders 2026-10-13): register THAT file, copy nothing -
            # a second copy would only confuse the variety rule.
            same = os.path.join(media, name)
            if os.path.exists(same) and _same_bytes(same, os.path.join(folder, name)):
                p = {"file": name, "credit": credit, "subject": subject, "club": club,
                     "slug": slug, "year": year, "is_person": is_person,
                     "source": source, "added": today}
                reg["photos"] = [q for q in reg["photos"] if q["file"] != name]
                reg["photos"].append(p)
                by_source[source] = p
                by_file.add(name)
                res["added"].append(f"{source} = media/{name} (already there)")
                continue
            fname = media_name(slug, name)
            if fname in by_file or os.path.exists(os.path.join(media, fname)):
                # the same stem twice in one folder, or a name an article
                # already owns: never overwrite a published photo
                base, ext = os.path.splitext(fname)
                fname = f"{base}-{hashlib.md5(name.encode('utf-8')).hexdigest()[:6]}{ext}"
            if not check:
                shrink_source(os.path.join(folder, name))
                os.makedirs(media, exist_ok=True)
                with open(os.path.join(media, fname), "wb") as f:
                    f.write(_web_bytes(os.path.join(folder, name)))
            p = {"file": fname, "credit": credit, "subject": subject, "club": club,
                 "slug": slug, "year": year, "is_person": is_person,
                 "source": source, "added": today}
            reg["photos"].append(p)
            by_source[source] = p
            by_file.add(fname)
            res["added"].append(f"{source} -> media/{fname}")

    # A photo the editor DELETED from its folder leaves the registry (user,
    # 2026-10-18: «لو فيه صور انت بتستخدمها ومش عجباني همسحها منه») - from
    # this moment no article picks it. Its media/ copy stays: the articles that
    # already published it keep their picture.
    res["removed"] = []
    keep = []
    for p in reg["photos"]:
        src = p.get("source") or ""
        if src.startswith("team-photos/") and not os.path.exists(os.path.join(folder_root, *src.split("/")[1:])):
            res["removed"].append(src)
            continue
        keep.append(p)
    reg["photos"] = keep

    if not check and (res["added"] or res["updated"] or res["removed"]):
        save_registry(reg, registry_path)
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()
    res = sync(check=args.check)
    verb = "would add" if args.check else "added"
    for s in res["added"]:
        print(f"  +    {verb} {s}")
    for s in res["updated"]:
        print(f"  ~    credit updated {s}")
    for s in res.get("removed", []):
        print(f"  -    deleted from its folder, out of the registry (media copy kept): {s}")
    for s in res["waiting"]:
        print(f"  !    WAITING for a credit line in credits.txt: {s}")
    print(f"team photos: {len(res['added'])} {verb}, {len(res['updated'])} updated, "
          f"{res['kept']} already registered, {len(res['waiting'])} waiting for a credit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
