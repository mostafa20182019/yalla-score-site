r"""Web push (2026-09-27): the sending rules, the run, the real crypto, the wiring.

    python tests/test_push_send.py      (from the repo root)

The rules are the ones agreed with the user and printed on /privacy: new
articles only (no upgrades, no «الجولة بالأرقام»), nothing 01:00-08:00 Cairo
(a night story goes out at 08:00), at most 5 a day and 60 minutes apart, the
last 2 of the day kept for Egyptian / curated-club news. Then the run itself
on a real sqlite store (claim, dead endpoints dropped, a total failure
retried, nothing without subscribers), and finally a REAL push against a local
fake push service: the payload must decrypt with the subscriber's keys (RFC
8291) and the VAPID token must verify with our public key (RFC 8292) - the
part a fake sender can never prove.
"""
import base64
import datetime
import http.server
import json
import os
import re
import sys
import tempfile
import threading
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
for k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "VAPID_PRIVATE_KEY"):
    os.environ.pop(k, None)
_tmp = tempfile.mkdtemp()
os.environ["D1_SQLITE"] = os.path.join(_tmp, "push.sqlite")

import store                     # noqa: E402
import push_send as P            # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


CAI = ZoneInfo("Africa/Cairo")


def cai(h, m=0, day=27):
    return datetime.datetime(2026, 9, day, h, m, tzinfo=CAI)


def art(aid, title, pub, **kw):
    a = {"article_id": str(aid), "title": title, "summary": kw.pop("summary", "ملخص الخبر"),
         "pub_ts": pub.isoformat(), "image_url": "https://yallascore.site/media/x.jpg"}
    a.update(kw)
    return a


def reset():
    for t in ("fb_posted", "fb_failed", "push_subs"):
        store.sql(f"DELETE FROM {t}", [])


def sent_at(aid, when):
    store.record_post(P.KIND, aid, "1/1", title="x")
    store.sql("UPDATE fb_posted SET posted_at = ?, claimed_at = ? WHERE kind = ? AND ref_id = ?",
              [int(when.timestamp()), int(when.timestamp()), P.KIND, str(aid)])


store.init_schema()
EGY = "الأهلي يعلن تفاصيل إصابة لاعبه قبل القمة"
CLUB = "برشلونة يحسم صفقة جديدة في الشتاء"
OTHER = "إنتر ميامي يتعاقد مع مدافع جديد"

# ------------------------------------------------------------- 1. the rules
ck("1 an upgraded archive piece is never news",
   P.excluded(art(1, EGY, cai(10), upgraded_ts="2026-09-27T10:00:00+03:00")) is not None)
ck("2 «الجولة بالأرقام» (a round: source note) is excluded",
   P.excluded(art(2, EGY, cai(10), sources=[{"name": "بيانات يلا سكور", "note": "round:egypt:5"}]))
   is not None)
ck("3 an ordinary new article is eligible", P.excluded(art(3, EGY, cai(10))) is None)
ck("4 priority: Egypt 2 > curated club 1 > anything else 0",
   (P.priority(art(1, EGY, cai(10))), P.priority(art(2, CLUB, cai(10))),
    P.priority(art(3, OTHER, cai(10)))) == (2, 1, 0))
ck("5 Saudi Al-Ahli is not Egyptian football",
   P.priority(art(4, "الأهلي السعودي يتعاقد مع مهاجم", cai(10))) == 0)

reset()
items = [art(10, EGY, cai(9, 30))]
a, why = P.choose(items, now=cai(3))
ck("6 nothing at all in the quiet hours", a is None and "quiet" in why, why)
night = [art(11, EGY, cai(3, 10))]
a, why = P.choose(night, now=cai(8, 10))
ck("7 a story published at 03:10 goes out at 08:10 (quiet hours do not age it)",
   a is not None and a["article_id"] == "11", why)
a, _ = P.choose([art(12, EGY, cai(9))], now=cai(12, 30))
ck("8 a story 3.5 sendable hours old is stale", a is None)
a, _ = P.choose([art(13, OTHER, cai(12)), art(14, EGY, cai(11, 30))], now=cai(12, 10))
ck("9 an Egyptian story beats a newer non-curated one", a and a["article_id"] == "14")
a, _ = P.choose([art(15, CLUB, cai(11, 30)), art(16, CLUB, cai(12))], now=cai(12, 10))
ck("10 same priority: the newest goes", a and a["article_id"] == "16")

reset()
sent_at(900, cai(11, 40))
a, why = P.choose([art(17, EGY, cai(12))], now=cai(12, 10))
ck("11 at least 60 minutes between two notifications", a is None and "min ago" in why, why)
a, why = P.choose([art(17, EGY, cai(12))], now=cai(12, 45))
ck("12 ... and after 60 minutes the next one may go", a is not None, why)

reset()
for i, h in enumerate((8, 10, 12, 14, 16)):
    sent_at(800 + i, cai(h, 5))
a, why = P.choose([art(18, EGY, cai(18))], now=cai(18, 10))
ck("13 at most 5 a day", a is None and "cap" in why, why)
a, why = P.choose([art(18, EGY, cai(8, 20, day=28))], now=cai(8, 30, day=28))
ck("14 yesterday's 5 do not count today", a is not None, why)

reset()
for i, h in enumerate((8, 10, 12)):
    sent_at(700 + i, cai(h, 5))
a, why = P.choose([art(19, OTHER, cai(14))], now=cai(14, 10))
ck("15 after 3 today, a non-curated story may not take a reserved slot", a is None, why)
a, why = P.choose([art(19, OTHER, cai(14)), art(20, CLUB, cai(13, 50))], now=cai(14, 10))
ck("16 ... but a curated-club story may", a and a["article_id"] == "20", why)

reset()
sent_at(21, cai(8, 5))
a, _ = P.choose([art(21, EGY, cai(8))], now=cai(9, 30))
ck("17 an article already notified is never notified again", a is None)

# ------------------------------------------------------------- 2. the payload
long_sum = "كلمة " * 400
pl = json.loads(P.payload(art(22, EGY, cai(10), summary=long_sum)))
ck("18 payload: title, a short body, the canonical link, a per-article tag",
   pl["title"] == EGY and len(pl["body"]) <= 150 and pl["url"] == "https://yallascore.site/a/22"
   and pl["tag"] == "a-22", pl["body"][-20:])
ck("19 payload fits the push record", len(P.payload(art(22, EGY * 10, cai(10), summary=long_sum))
                                          .encode("utf-8")) <= P.PAYLOAD_MAX)
rep = json.loads(P.payload(art(23, EGY, cai(10), kind="report", match_id="560586")))
ck("20 a match report opens the match page", rep["url"] == "https://yallascore.site/m/560586")
ck("21 no SVG placeholder as the big image",
   "image" not in json.loads(P.payload(art(24, EGY, cai(10), image_url="/media/ph-ball.svg"))))

# ------------------------------------------------------------- 3. the run
PUB, PRIV = P.keygen()
P.C.VAPID_PUBLIC_KEY = PUB
os.environ["VAPID_PRIVATE_KEY"] = PRIV
NOW = cai(12, 10)
ARTS = [art(30, EGY, cai(12))]
P.FB.load_articles = lambda: ARTS


def add_sub(ep):
    store.sql("INSERT INTO push_subs (endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, 0)",
              [ep, "p" * 87, "a" * 22])


def fake(results):
    calls = []

    def s(sub, data, key):
        calls.append(sub["endpoint"])
        return results.get(sub["endpoint"], ("ok", 201))
    return s, calls


reset()
r = P.auto(now=NOW, sender=fake({})[0], live=lambda u: True)
ck("22 no subscribers: nothing sent, nothing recorded",
   r == 0 and not store.posted_ids(P.KIND))

reset()
for ep in ("https://fcm.googleapis.com/a", "https://fcm.googleapis.com/dead",
           "https://updates.push.services.mozilla.com/b"):
    add_sub(ep)
snd, calls = fake({"https://fcm.googleapis.com/dead": ("gone", 410)})
r = P.auto(now=NOW, sender=snd, live=lambda u: True)
rec = store.get_post(P.KIND, "30")
left = {x["endpoint"] for x in store.sql("SELECT endpoint FROM push_subs", [])}
ck("23 everyone is sent to, the result is recorded as ok/total",
   r == 0 and len(calls) == 3 and rec and rec["post_id"] == "2/3", rec and rec["post_id"])
ck("24 an endpoint answering 410 is deleted on the spot",
   "https://fcm.googleapis.com/dead" not in left and len(left) == 2)
# record_post stamps the REAL clock; pin it to the test clock, then come back
# after the gap, while the article is still fresh
store.sql("UPDATE fb_posted SET posted_at = ? WHERE kind = ? AND ref_id = '30'",
          [int(NOW.timestamp()), P.KIND])
a, why = P.choose(ARTS, now=cai(13, 20))
snd2, calls2 = fake({})
P.auto(now=cai(13, 20), sender=snd2, live=lambda u: True)
ck("25 the same article never goes out twice", a is None and calls2 == [], why)

reset()
add_sub("https://fcm.googleapis.com/a")
snd, calls = fake({"https://fcm.googleapis.com/a": ("fail", 403)})
P.auto(now=NOW, sender=snd, live=lambda u: True)
ck("26 nobody received it: the claim is released and the failure counted (retry is safe)",
   "30" not in store.posted_ids(P.KIND) and store.failed_count(P.KIND, "30") == 1
   and store.get_post(P.KIND, "30") is None)

reset()
add_sub("https://fcm.googleapis.com/a")
snd, calls = fake({})
P.auto(now=NOW, sender=snd, live=lambda u: False)
ck("27 the page is not live yet: nothing sent, claim released for the next run",
   calls == [] and store.get_post(P.KIND, "30") is None)

src = open("push_send.py", encoding="utf-8").read()
ck("28 the claim comes BEFORE the fan-out (the duplicate lock)",
   src.index("store.claim(KIND") < src.index("ok, gone, fails = fan_out("))
ck("29 its dedup namespace is its own", P.KIND == "push")

_, other_priv = P.keygen()
os.environ["VAPID_PRIVATE_KEY"] = other_priv
ck("30 a private key that is not the site's public key fails loudly (exit 1)",
   P.auto(now=NOW, sender=fake({})[0], live=lambda u: True) == 1)
os.environ.pop("VAPID_PRIVATE_KEY")
snd, calls = fake({})
ck("31 no private key: exits 0, sends nothing",
   P.auto(now=NOW, sender=snd, live=lambda u: True) == 0 and calls == [])
os.environ["VAPID_PRIVATE_KEY"] = PRIV
P.C.VAPID_PUBLIC_KEY = ""
ck("32 no public key in config (the bell is dark): nothing to do",
   P.auto(now=NOW, sender=snd, live=lambda u: True) == 0 and calls == [])
P.C.VAPID_PUBLIC_KEY = PUB
_d1 = os.environ.pop("D1_SQLITE")
ck("33 no D1 (json backend): skipped, exit 0",
   P.auto(now=NOW, sender=snd, live=lambda u: True) == 0 and calls == [])
os.environ["D1_SQLITE"] = _d1
ck("34 the key pair: 87-char public key starting B, and public_of() finds it",
   len(PUB) == 87 and PUB[0] == "B" and P.public_of(PRIV) == PUB)

# ------------------------------------------------------------- 4. REAL crypto
try:
    import http_ece
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    HAVE = True
except ImportError:
    HAVE = False
ck("35 pywebpush + http_ece are installed (requirements.txt)", HAVE)

if HAVE:
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            got.append((self.path, self.headers, self.rfile.read(n)))   # case-insensitive get()
            self.send_response(410 if self.path == "/gone" else 201)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    ua_priv = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua_priv.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()   # noqa: E731
    sub = {"endpoint": base + "/push/abc", "p256dh": b64(ua_pub), "auth": b64(auth)}
    data = P.payload(art(40, EGY, cai(10)))
    res = P.send_one(sub, data, PRIV)
    ck("36 a real push is accepted by the push service", res == ("ok", 201), res)
    path, hdr, body = got[-1]
    plain = http_ece.decrypt(body, private_key=ua_priv, auth_secret=auth, version="aes128gcm")
    ck("37 the payload decrypts with the SUBSCRIBER's keys, byte for byte",
       plain.decode("utf-8") == data)
    ck("38 aes128gcm, a TTL, the topic and urgency headers are sent",
       hdr.get("Content-Encoding") == "aes128gcm" and hdr.get("TTL") == str(P.TTL_SEC)
       and hdr.get("Topic") == P.TOPIC and hdr.get("Urgency") == "normal")
    authz = hdr.get("Authorization", "")
    parts = dict(p.strip().split("=", 1) for p in authz[len("vapid "):].split(","))
    jwt = parts.get("t", "")
    h64, c64, s64 = jwt.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)                            # noqa: E731
    claims = json.loads(base64.urlsafe_b64decode(pad(c64)))
    sig = base64.urlsafe_b64decode(pad(s64))
    pub_obj = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), base64.urlsafe_b64decode(pad(PUB)))
    try:
        pub_obj.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"),
                                            int.from_bytes(sig[32:], "big")),
                       f"{h64}.{c64}".encode(), ec.ECDSA(hashes.SHA256()))
        verified = True
    except Exception:                                       # noqa: BLE001
        verified = False
    ck("39 the VAPID token verifies with OUR public key, and names it",
       authz.startswith("vapid ") and verified and parts.get("k") == PUB)
    ck("40 its audience is the push service's origin, its subject our contact",
       claims.get("aud") == base and claims.get("sub") == P.CONTACT, claims)
    gone = dict(sub, endpoint=base + "/gone")
    ck("41 a 410 from the push service reads as 'gone'", P.send_one(gone, data, PRIV)[0] == "gone")
    # two push services in ONE fan-out: each token must carry its own audience
    srv2 = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    base2 = f"http://127.0.0.1:{srv2.server_port}"
    got.clear()
    P.fan_out([sub, dict(sub, endpoint=base2 + "/push/x")], data, PRIV)
    auds = set()
    for _, h, _ in got:
        t = dict(p.strip().split("=", 1) for p in h.get("Authorization")[6:].split(","))["t"]
        auds.add(json.loads(base64.urlsafe_b64decode(pad(t.split(".")[1])))["aud"])
    ck("42 each push service gets a token for ITSELF (claims are not shared)",
       auds == {base, base2}, auds)
    srv.shutdown()
    srv2.shutdown()

# ------------------------------------------------------------- 5. the wiring
wf = open(".github/workflows/publish.yml", encoding="utf-8").read()
i = wf.find("Push notification for a new article")
step = wf[i:i + 900] if i >= 0 else ""
ck("43 publish.yml: the step exists, runs after a real deploy, never fails the publish",
   bool(step) and "steps.deploy.outcome == 'success'" in step and "continue-on-error: true" in step)
ck("44 ... with the private key and the store credentials",
   "secrets.VAPID_PRIVATE_KEY" in step and "CF_D1_ID" in step and "push_send.py --auto" in step)
ck("45 the verdict step reports it", "O_PUSH" in wf and "push:$O_PUSH" in wf)
req = open("requirements.txt", encoding="utf-8").read()
ck("46 pywebpush is a requirement", "pywebpush" in req)
priv_t = open("site_src/templates/privacy.html", encoding="utf-8").read()
ck("47 /privacy states the same rules the code enforces",
   P.DAILY_CAP == 5 and "خمسة إشعارات" in priv_t and P.QUIET == (1, 8)
   and "بين الواحدة والثامنة" in priv_t)
sw = open("root-extras/sw.js", encoding="utf-8").read()
ck("48 sw.js caches NOTHING (no fetch handler - the site rebuilds every 15 min)",
   'addEventListener("fetch"' not in sw and "caches." not in sw)
ck("49 sw.js shows the push and opens its url on tap",
   "showNotification" in sw and "notificationclick" in sw and "openWindow" in sw)
man = json.load(open("root-extras/manifest.webmanifest", encoding="utf-8"))
ck("50 the manifest is RTL Arabic with 192 + 512 icons that exist",
   man["dir"] == "rtl" and man["lang"] == "ar"
   and {i["sizes"] for i in man["icons"]} == {"192x192", "512x512"}
   and all(os.path.exists("assets-src/" + os.path.basename(i["src"])) for i in man["icons"])
   and os.path.exists("assets-src/badge-96.png"))

# ------------------------------------------------------------- 6. the pages
from site_lib import shell as S                    # noqa: E402
S.VAPID_PUBLIC_KEY = ""
dark = S.head("t", "d", "https://yallascore.site/") + S.foot() + S.push_cta()
ck("51 with no key the pages carry NO push markup",
   "push-btn" not in dark and "manifest" not in dark and "__VAPID" not in dark
   and "serviceWorker" not in dark)
S.VAPID_PUBLIC_KEY = PUB
on = S.head("t", "d", "https://yallascore.site/") + S.foot()
ck("52 with the key: manifest, theme colour, a HIDDEN bell, the script with the key",
   'rel="manifest"' in on and 'name="theme-color"' in on
   and 'class="push-btn head-bell" hidden' in on and f"var KEY='{PUB}'" in on
   and "__VAPID_PUBLIC_KEY__" not in on)
cta = S.push_cta()
ck("53 the article line is hidden until the script reveals it",
   cta.startswith('<div class="push-cta" hidden>') and "push-btn" in cta)
js = S.PUSH_JS
# a CALL of on(): not "function on()", not the "on()" inside "function()"
_calls = [ln for ln in js.splitlines() if re.search(r"(?<![\w.])on\(\)", ln)
          and "function on()" not in ln]
ck("54 permission is asked ONLY from a tap, never on load",
   js.count("Notification.requestPermission(") == 1 and len(_calls) == 1
   and "addEventListener('click'" in js and "register('/sw.js'" in js
   and js.index("addEventListener('click'") < js.index(_calls[0].strip()), _calls)
ck("55 the in-app browsers (Facebook/Instagram) never see a dead button",
   "FBAN" in js and "Instagram" in js)
art_t = open("site_src/templates/article.html", encoding="utf-8").read()
ck("56 the article template renders the line", "{{ push_cta }}" in art_t)
S.VAPID_PUBLIC_KEY = ""

print()
print("FAILED:" if fails else "all push checks passed", ", ".join(fails))
sys.exit(1 if fails else 0)
