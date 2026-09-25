"""data_store.py (2026-09-24, step 3) - the working data in Workers KV, not git.

    python tests/test_data_store.py   (from the repo root)

The store is only safe if its three rules hold, so they are what this pins:
a failed or incomplete pull never becomes a build input, a job that never
pulled cannot push, and an accumulating archive that shrinks is refused. Plus
the merge that keeps two overlapping runs from dropping each other's additions.
The KV transport is replaced by an in-memory fake; nothing here touches the network.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import data_store as DS  # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


# ---- a sandbox data/ dir and an in-memory KV -------------------------------
tmp = tempfile.mkdtemp()
DS.DATA = os.path.join(tmp, "data")
DS.STATE = os.path.join(DS.DATA, ".store_state.json")
os.makedirs(DS.DATA)
KV = {}
DS.remote_get = lambda: DS.unpack(KV["blob"]) if "blob" in KV else (None, {})
DS.remote_put = lambda blob: KV.__setitem__("blob", blob)


def write(name, doc):
    with open(os.path.join(DS.DATA, name), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)


def read(name):
    with open(os.path.join(DS.DATA, name), encoding="utf-8") as f:
        return json.load(f)


def arch(n, frozen_ids=()):
    return {"meta": {}, "results": [{"match_id": str(i), "home_score": 1, "away_score": 0,
                                     "frozen": str(i) in frozen_ids} for i in range(n)]}


def items_doc(n):
    return {"results": [{"items": [{"match_id": i} for i in range(n)]}]}


def seed_files(n_arch=50):
    write("matches.json", items_doc(5))
    write("fixtures.json", {"results": []})
    write("results_archive.json", arch(n_arch))
    write("matches_archive.json", items_doc(40))
    write("match_details.json", items_doc(30))


# 1) pack/unpack is lossless, Arabic included
files = {"matches.json": json.dumps({"x": "الأهلي 2-1 الزمالك"}, ensure_ascii=False).encode("utf-8")}
meta, back = DS.unpack(DS.pack(files, {"ts": 1}))
ck("1 pack -> unpack returns the exact bytes (Arabic too)", back == files and meta == {"ts": 1})

# 2) rule 2: a job that never pulled cannot push; --seed is the explicit first push
seed_files()
rc = DS.push()
ck("2a push without a pull is refused", rc == 2 and "blob" not in KV, rc)
rc = DS.push(seed=True, by="seed")
ck("2b the explicit --seed push fills the empty store", rc == 0 and "blob" in KV, rc)
m, r = DS.unpack(KV["blob"])
ck("2c every STORE_FILE present is in the bundle, nothing else",
   set(r) == {"matches.json", "fixtures.json", "results_archive.json", "matches_archive.json", "match_details.json"})
rc = DS.push(seed=True, by="again")
ck("2d an unchanged push writes nothing", rc == 0 and DS.unpack(KV["blob"])[0]["by"] == "seed")

# 3) pull restores the files and records what it pulled
shutil.rmtree(DS.DATA); os.makedirs(DS.DATA)
rc = DS.pull()
ck("3a pull writes the files back", rc == 0 and len(read("results_archive.json")["results"]) == 50)
ck("3b pull records the state that licenses a later push", os.path.exists(DS.STATE))

# 4) rule 3: a shrinking archive is refused
write("results_archive.json", arch(10))
rc = DS.push()
ck("4a results_archive 50 -> 10 is refused, the store keeps 50",
   rc == 3 and len(json.loads(DS.unpack(KV["blob"])[1]["results_archive.json"])["results"]) == 50, rc)
write("results_archive.json", arch(52))
rc = DS.push()
ck("4b growth is fine", rc == 0 and len(json.loads(DS.unpack(KV["blob"])[1]["results_archive.json"])["results"]) == 52)

# 5) two overlapping runs: B pulled before A pushed -> archives are MERGED
shutil.rmtree(DS.DATA); os.makedirs(DS.DATA); DS.pull()
state_b = json.load(open(DS.STATE, encoding="utf-8"))
# run A adds match 100 (frozen) and pushes
doc = read("results_archive.json"); doc["results"].append({"match_id": "100", "frozen": True, "home_score": 2, "away_score": 0})
write("results_archive.json", doc); DS.push()
# run B, from the OLD pull, adds match 200 and has match 100 unfrozen
doc = arch(52); doc["results"] += [{"match_id": "200", "frozen": False}, {"match_id": "100", "frozen": False, "home_score": 9}]
write("results_archive.json", doc)
json.dump(state_b, open(DS.STATE, "w", encoding="utf-8"))
rc = DS.push()
got = {e["match_id"]: e for e in json.loads(DS.unpack(KV["blob"])[1]["results_archive.json"])["results"]}
ck("5a both runs' additions survive the overlap", rc == 0 and "100" in got and "200" in got, rc)
ck("5b a frozen result from the other run beats our unfrozen copy",
   got["100"]["frozen"] is True and got["100"]["home_score"] == 2)

# 6) rule 1: an empty store or a bundle missing the essentials is never pulled
KV.clear()
ck("6a pulling an empty store fails (the workflow stops before building)", DS.pull() == 2)
KV["blob"] = DS.pack({"standings.json": b"{}"}, {"ts": 1})
ck("6b a bundle without matches/fixtures/results_archive is refused", DS.pull() == 2)

# 7) merge() handles the write_items shape too
a = json.dumps(items_doc(3)).encode(); b = json.dumps({"results": [{"items": [{"match_id": 7}]}]}).encode()
merged = json.loads(DS.merge("matches_archive.json", a, b))
ck("7 matches_archive merge unions the write_items shape",
   sorted(e["match_id"] for e in merged["results"][0]["items"]) == [0, 1, 2, 7])

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
