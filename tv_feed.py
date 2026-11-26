#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The channel of each COMING match, by its number (user, 2026-11-26: «نعمل
5» - until now the site named a competition's broadcaster, «beIN Sports»,
never the channel a match is on).

    python tv_feed.py            # ask for what is missing, then write the channel into data/matches.json
    python tv_feed.py --dry      # say what would be asked, write nothing

THE SOURCE: the 365scores game feed - the one every score on the site comes
from - lists a game's `tvNetworks` for the Arab region (userCountryId=131)
in the days before kick-off: «beIN SPORTS HD 1», «ثمانية 1», «الرياضية
المغربية (3)». Not for every competition and not weeks ahead: a match the
feed names no channel for keeps the competition's verified broadcaster
(site_lib/competitions.COMP_TV) exactly as before - this file only ever ADDS.

HOW IT REACHES THE PAGES: every page, card and post already reads
`m["channel"]` first and falls back to COMP_TV. fetch_data.py writes that
field as None on every run; this script runs after it and fills it from
data/tv_feed.json (in the data store), so the build, the morning card and
the Facebook posts all read one value.

Kind to the feed: a match is asked when it kicks off within AHEAD_D days and
its answer is older than REFRESH_H hours (channels are assigned late and do
change); MAX_NEW games a run. NEVER FAILS THE RUN.
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "data", "tv_feed.json")
MATCHES = os.path.join(HERE, "data", "matches.json")
WHY = ("The channels the 365scores game feed names for a coming match in the Arab region "
       "(tv_feed.py). Keyed by our match_id. Written into matches.json's `channel`.")
AHEAD_D = 3
REFRESH_H = 12
MAX_NEW = 40
KEEP_D = 10               # an entry this long after its kick-off is dropped
COUNTRY = 131             # the feed's Arab-region audience


def clean(name):
    """One channel name as the site writes it: «beIN SPORTS HD 1», «Bein
    Sports HD2» and «beIN Sports 5 HD» are all «beIN Sports 1/2/5»."""
    s = re.sub(r"\s+", " ", str(name or "")).strip()
    m = re.match(r"(?i)^bein\s*sports?\b(.*)$", s)
    if m:
        rest = re.sub(r"(?i)\bhd\b", " ", m.group(1))
        rest = re.sub(r"(?i)hd(?=\d)", " ", rest)
        num = re.search(r"\d+", rest)
        extra = re.sub(r"\d+", " ", rest)
        extra = re.sub(r"\s+", " ", extra).strip()
        return ("beIN Sports" + (f" {extra}" if extra else "") + (f" {num.group(0)}" if num else "")).strip()
    return s


def channel_text(names):
    """The field's text: the channels in the feed's order, no name twice."""
    out = []
    for n in names or []:
        c = clean(n)
        if c and c not in out:
            out.append(c)
    return "، ".join(out[:3])


def load(path=OUT):
    try:
        with open(path, encoding="utf-8") as f:
            return (json.load(f) or {}).get("matches") or {}
    except (OSError, ValueError):
        return {}


def wanted(matches, held, now, ahead=AHEAD_D, refresh_h=REFRESH_H):
    """The coming matches to ask about, soonest first."""
    today = now.date().isoformat()
    lim = (now.date() + datetime.timedelta(days=ahead)).isoformat()
    old = (now - datetime.timedelta(hours=refresh_h)).isoformat(timespec="seconds")
    out = []
    for m in sorted(matches, key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or "")):
        d = str(m.get("kickoff") or "")[:10]
        if m.get("status") != "UPCOMING" or not m.get("match_id") or not (today <= d <= lim):
            continue
        cur = held.get(str(m["match_id"]))
        if cur and (cur.get("fetched") or "") >= old:
            continue
        out.append(m)
    return out


def run(matches, held, now, fetch, max_new=MAX_NEW, log=print):
    """Ask the feed. Returns (held, changed)."""
    import h2h_feed as HF
    want = wanted(matches, held, now)[:max_new]
    ids = HF.feed_ids([m for m in want if m.get("competition") in HF.FD_COMPS], fetch) if want else {}
    changed = False
    for m in want:
        gid = ids.get(m["match_id"]) if m.get("competition") in HF.FD_COMPS else m.get("match_id")
        if not gid:
            continue
        try:
            g = (fetch(f"game/?appTypeId=5&langId=27&timezoneName=Africa/Cairo&gameId={int(gid)}"
                       f"&userCountryId={COUNTRY}") or {}).get("game") or {}
        except Exception as e:                          # noqa: BLE001
            log(f"  ! {m['match_id']}: feed unreachable ({e})")
            continue
        names = [n.get("name") for n in g.get("tvNetworks") or [] if n.get("name")]
        held[str(m["match_id"])] = {"fetched": now.isoformat(timespec="seconds"),
                                    "kickoff": str(m.get("kickoff") or "")[:10], "names": names}
        changed = True
        log(f"  {m['match_id']} {m.get('competition')}: {channel_text(names) or '-'}")
    # an entry long after its match is of no use to anyone
    cut = (now.date() - datetime.timedelta(days=KEEP_D)).isoformat()
    for k in [k for k, v in held.items() if (v.get("kickoff") or "9") < cut]:
        del held[k]
        changed = True
    return held, changed


def apply(doc_items, held):
    """Write the channel onto the matches that have none. Returns how many."""
    n = 0
    for m in doc_items:
        if m.get("channel"):
            continue
        txt = channel_text((held.get(str(m.get("match_id"))) or {}).get("names"))
        if txt:
            m["channel"] = txt
            n += 1
    return n


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max", type=int, default=MAX_NEW)
    a = ap.parse_args()
    try:
        import match_brief as MB
        import data_store as DS
        with open(MATCHES, encoding="utf-8") as f:
            doc = json.load(f)
        items = DS._items(doc)
        held = load()
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).replace(tzinfo=None)
        if a.dry:
            for m in wanted(items, held, now)[:a.max]:
                print(f"  would ask: {m.get('kickoff')} {m.get('competition')} {m.get('match_id')}")
            return 0
        held, changed = run(items, held, now, MB._s365, a.max)
        if changed:
            with open(OUT, "w", encoding="utf-8", newline="\n") as f:
                json.dump({"_why": WHY, "matches": held}, f, ensure_ascii=False, indent=1)
                f.write("\n")
        n = apply(items, held)
        if n:
            with open(MATCHES, "w", encoding="utf-8", newline="\n") as f:
                json.dump(doc, f, ensure_ascii=False)
        print(f"  tv_feed: {len(held)} match(es) on record, the channel written on {n}")
    except Exception as e:                              # noqa: BLE001 - never fails the publish run
        print(f"tv_feed: skipped ({e!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
