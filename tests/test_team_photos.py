# -*- coding: utf-8 -*-
r"""The editor's team folders (2026-10-13).

    python tests/test_team_photos.py     (from the repo root)

Everything runs in a temp tree - no real folder, media/ or registry is touched.
The rules under test are the ones whose failure costs a published article:
a photo with no credit must never reach media/, a registered file is never
rewritten, the slug prefix and ascii name are what the prompts search for,
and a credit fix in credits.txt reaches the registry without re-adding.
"""
import io, json, os, shutil, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from PIL import Image
import team_photos as TP

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

tmp = tempfile.mkdtemp()
root = os.path.join(tmp, "team-photos")
media = os.path.join(tmp, "media")
reg = os.path.join(tmp, "data", "team_photos.json")

def photo(folder, name, w=2400, h=1200):
    os.makedirs(folder, exist_ok=True)
    im = Image.new("RGB", (w, h), (31, 148, 211))
    px = im.load()
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            px[x, y] = ((x * 7) % 256, (y * 5) % 256, (x + y) % 256)
    p = os.path.join(folder, name)
    im.save(p, "JPEG" if name.lower().endswith(("jpg", "jpeg")) else "PNG", quality=95)
    return p

def credits(folder, text):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "credits.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)

def run(check=False):
    return TP.sync(folder_root=root, media=media, registry_path=reg, check=check)

# ------------------------------------------------------ 1. no credit, no copy
ahly = os.path.join(root, "al-ahly")
photo(ahly, "Trezeguet-2026.jpg")
r = run()
ck("1a a photo with no credit line is WAITING", r["waiting"] == ["team-photos/al-ahly/Trezeguet-2026.jpg"])
ck("1b ...and nothing reached media/", not os.path.isdir(media) or not os.listdir(media))
ck("1c ...and no registry was written", not os.path.exists(reg))

# ------------------------------------------------------ 2. the folder default
credits(ahly, "# تعليق\n* | الصورة: من أرشيف يلا سكور | 2026\n")
r = run(check=True)
ck("2a --check reports the add", len(r["added"]) == 1 and r["added"][0].startswith("team-photos/al-ahly/Trezeguet-2026.jpg -> media/al-ahly-trezeguet-2026.jpg"), str(r["added"]))
ck("2b --check writes nothing", not os.path.exists(reg) and not os.path.exists(os.path.join(media, "al-ahly-trezeguet-2026.jpg")))
r = run()
f = os.path.join(media, "al-ahly-trezeguet-2026.jpg")
ck("2c the copy is media/<slug>-<ascii stem>.jpg", os.path.exists(f))
with Image.open(f) as im:
    ck("2d the copy is web-sized (1600 wide, JPEG)", im.width == 1600 and im.format == "JPEG", f"{im.width} {im.format}")
with Image.open(os.path.join(ahly, "Trezeguet-2026.jpg")) as im:
    ck("2e the source was shrunk in place too", im.width == 1600, str(im.width))
d = json.load(open(reg, encoding="utf-8"))
p = d["photos"][0]
ck("2f registry record carries file/credit/club/year/source", (p["file"], p["credit"], p["club"], p["year"], p["source"]) ==
   ("al-ahly-trezeguet-2026.jpg", "الصورة: من أرشيف يلا سكور", "الأهلي", 2026, "team-photos/al-ahly/Trezeguet-2026.jpg"))
ck("2g no subject -> the club itself, not a person", p["subject"] == "الأهلي" and p["is_person"] is False)

# ---------------------------------------------- 3. idempotent + credit update
before = os.path.getmtime(f)
r = run()
ck("3a a second run adds nothing", r["added"] == [] and r["kept"] == 1)
ck("3b ...and does not rewrite the media file", os.path.getmtime(f) == before)
credits(ahly, "* | الصورة: من أرشيف يلا سكور | 2026\n"
              "Trezeguet-2026.jpg | الصورة: تريزيجيه في تدريبات الأهلي، رخصة CC BY 4.0 | 2025 | تريزيجيه\n")
r = run()
p = json.load(open(reg, encoding="utf-8"))["photos"][0]
ck("3c an own line beats the folder default and updates the record in place",
   r["updated"] == ["team-photos/al-ahly/Trezeguet-2026.jpg"] and p["year"] == 2025 and p["subject"] == "تريزيجيه")
ck("3d a named subject marks a person", p["is_person"] is True)
ck("3e ...and the media file is still the same one", os.path.getmtime(f) == before and len(os.listdir(media)) == 1)

# ------------------------------------------------- 4. names, png, collisions
zam = os.path.join(root, "zamalek")
photo(zam, "صورة الزمالك.jpg", 800, 600)
photo(zam, "stadium.png", 1000, 700)
photo(zam, "stadium.jpg", 1000, 700)   # same ascii stem, other extension (case-insensitive FS safe)
credits(zam, "* | الصورة: ملعب الزمالك، ملكية عامة |\n")
r = run()
names = sorted(os.listdir(media))
ck("4a an all-Arabic filename becomes a short hash, still slug-prefixed",
   any(n.startswith("zamalek-") and len(n) == len("zamalek-") + 8 + 4 for n in names), str(names))
ck("4b a png source is copied as .jpg", "zamalek-stadium.jpg" in names)
ck("4c two sources with the same ascii stem get two files", sum(n.startswith("zamalek-stadium") for n in names) == 2, str(names))
ck("4d a small photo is not upscaled", Image.open([os.path.join(media, n) for n in names if n.startswith("zamalek-") and "stadium" not in n][0]).width == 800)
ck("4e year left empty is null, not 0", all(p["year"] is None for p in json.load(open(reg, encoding="utf-8"))["photos"] if p["slug"] == "zamalek"))

# ------------------------------------------------------- 5. unknown folders
photo(os.path.join(root, "juventus"), "x.jpg", 900, 600)
credits(os.path.join(root, "juventus"), "* | صورة |\n")
r = run()
ck("5a a folder that is not a curated club is skipped", not any("juventus" in s for s in r["added"]))

# ------------------------------- 7. a photo media/ already has (the seeding)
liv = os.path.join(root, "liverpool")
src = photo(os.path.join(media), "anfield-kop.jpg", 1200, 600)        # "already published"
os.makedirs(liv, exist_ok=True); shutil.copy2(src, os.path.join(liv, "anfield-kop.jpg"))                # same bytes in the folder
credits(liv, "anfield-kop.jpg | صورة: مدرجات ملعب أنفيلد معقل ليفربول، رخصة CC BY 2.0 | 2024 | مدرجات ملعب أنفيلد\n")
n_before = len(os.listdir(media))
r = run()
p = [q for q in json.load(open(reg, encoding="utf-8"))["photos"] if q["slug"] == "liverpool"][0]
ck("7a identical bytes under the same name -> registered as THAT file, no copy",
   p["file"] == "anfield-kop.jpg" and len(os.listdir(media)) == n_before, str(r["added"]))
ck("7b a stadium/crowd subject is not a person", p["is_person"] is False)
ck("7c the source was left alone (already web-sized)", Image.open(os.path.join(liv, "anfield-kop.jpg")).width == 1200)

# ------------------------------------------------- 6. the real repo's state
ck("6a every curated club page has a folder", all(os.path.isdir(os.path.join("team-photos", s)) for s in TP.TEAMS), str([s for s in TP.TEAMS if not os.path.isdir(os.path.join("team-photos", s))]))
ck("6b every folder ships its credits.txt", all(os.path.exists(os.path.join("team-photos", s, "credits.txt")) for s in TP.TEAMS))
import site_lib.clubs as C
ck("6c the slugs are the /team/<slug> slugs", set(p["slug"] for p in C.TEAM_PAGES) <= set(TP.TEAMS))
ck("6d the Arabic names are the site's spellings", all(TP.TEAMS[p["slug"]] == p["name"] for p in C.TEAM_PAGES))
real = TP.load_registry()
ck("6e the committed registry is well-formed", isinstance(real.get("photos"), list) and all({"file", "credit", "club", "source"} <= set(p) for p in real["photos"]))
for p in real["photos"]:
    ck(f"6f registered file exists: {p['file']}", os.path.exists(os.path.join("media", p["file"])))
import audit_images as AI
ck("6g audit_images reads this registry too", all(p["file"] in AI.registry() for p in real["photos"]))

# 9 a photo the editor DELETES from its folder leaves the registry; its media copy stays
# (user, 2026-10-18: «لو فيه صور إنت بتستخدمها ومش عجباني همسحها منه»)
_del_src = os.path.join(root, "al-ahly", "Trezeguet-2026.jpg")
_del_media = os.path.join(media, "al-ahly-trezeguet-2026.jpg")
ck("9a before: the photo is registered and its media copy exists",
   any(q["source"] == "team-photos/al-ahly/Trezeguet-2026.jpg" for q in json.load(open(reg, encoding="utf-8"))["photos"]) and os.path.exists(_del_media))
os.remove(_del_src)
_r9 = run()
ck("9b sync reports the deletion", _r9.get("removed") == ["team-photos/al-ahly/Trezeguet-2026.jpg"], str(_r9.get("removed")))
ck("9c the registry no longer lists it", not any(q["source"] == "team-photos/al-ahly/Trezeguet-2026.jpg" for q in json.load(open(reg, encoding="utf-8"))["photos"]))
ck("9d the media copy is left in place (published articles keep their picture)", os.path.exists(_del_media))
ck("9e a second sync is quiet", run().get("removed") == [])

# 7 the prompts send a curated club's NEW photo through its folder (user ask
# 2026-10-18: the folders are where he sees what his clubs' stories used)
_pr = io.open(".github/prompts/daily-article.md", encoding="utf-8").read()
ck("8a daily-article saves a curated club's photo into team-photos/<slug>/ and runs team_photos.py",
   "team-photos/<slug>/" in _pr and "python team_photos.py" in _pr and "credits.txt" in _pr)
ck("8b ...and commits the folder + registry with the article", "git add team-photos data/team_photos.json" in _pr)
_wf = io.open(".github/workflows/daily-article.yml", encoding="utf-8").read()
ck("8c the parked-draft commit carries the folder and the registry too", "git add drafts media team-photos data/team_photos.json" in _wf)

shutil.rmtree(tmp, ignore_errors=True)
print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
