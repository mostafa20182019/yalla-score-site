/* ==========================================================================
 * /health + the watchdog (2026-09-24).
 *
 * WHY. Every failure that hurt this site so far was SILENT: a green publish
 * run whose deploy step was skipped (scorers missing for hours, 2026-09-13), a
 * fetch or Claude step failing under continue-on-error while the run stayed
 * green (upgrade runs 2026-09-16), the D1 quota running out mid-evening. The
 * GitHub API itself reports a failed continue-on-error step as "success", so
 * nothing looking at GitHub can see them. We found each one because a reader,
 * or the user, noticed the site was wrong.
 *
 * WHAT. Two sources nobody can fake:
 *   1. build-info.json from the DEPLOYED assets - the age of what readers are
 *      actually served, the fetch time and failed sources behind it, the
 *      newest article in it (written by build_site.build_info).
 *   2. health_beats in D1 - one row per workflow, written by heartbeat.py at
 *      the end of every run, with the REAL step outcomes and a count of
 *      consecutive failures.
 * plus the live store's own snapshot age.
 *
 * WHERE IT RUNS. Here, in the Worker, on the 15-minute cron: outside GitHub,
 * so a dead Actions queue or a broken dispatch token is caught too.
 *
 * WHO HEARS. The user, privately, on Telegram (TG_BOT_TOKEN + TG_ALERT_CHAT_ID
 * Worker secrets - NOT the public channel). Only on a change: a new failure, a
 * recovery, or a reminder every 6 h while it lasts. Warnings never page; they
 * are for /health. A watchdog that cries wolf gets muted, so the thresholds
 * below are deliberately loose and each one names the normal cadence it
 * allows for.
 *
 * COST. Per check: 1 asset fetch + 2 small D1 reads (≈10 rows), a write only
 * when the alert state changes. /health is cached for 60 s at the edge.
 * ======================================================================== */

const MIN = 60 * 1000, HOUR = 60 * MIN;

export const LIMITS = {
  // publish runs ~4x an hour (~6 min each) and ~10% are cancelled by the next
  // refresh; one or two skipped deploys in a row are normal
  deployWarn: 45 * MIN, deployFail: 90 * MIN,
  // the fetch runs inside every publish run; football-data/365scores hiccups
  // are routine, so only a long silence is an incident
  fetchWarn: 60 * MIN, fetchFail: 3 * HOUR,
  // a publish heartbeat must arrive even when nothing changed
  beatFail: 90 * MIN, runFails: 3,
  // articles: last slot 23:30 Cairo, first 09:00 -> a ~9.5 h overnight gap
  articleWarn: 10 * HOUR, articleFail: 16 * HOUR,
  // the Claude step: one failed slot is retried by the next (user's rule),
  // three in a row is an expired token or an empty quota
  claudeWarn: 2, claudeFail: 3,
  // the live store refreshes every minute from the Worker cron
  liveWarn: 3 * MIN, liveFail: 10 * MIN,
  remindEvery: 6 * HOUR,
};

const RANK = { ok: 0, warn: 1, fail: 2 };
const worst = (a, b) => (RANK[b] > RANK[a] ? b : a);
const ago = (ms) => ms < HOUR ? `${Math.round(ms / MIN)} min`
                  : ms < 48 * HOUR ? `${(ms / HOUR).toFixed(1)} h`
                  : `${Math.round(ms / (24 * HOUR))} days`;

/* Pure: inputs -> verdict. Everything time-based takes `now` so the tests can
 * move the clock. `d1Error` set = the database did not answer. */
export function evaluate({ build, beats, snapshot, d1Error }, now) {
  const checks = {};
  const put = (name, status, msg, extra = {}) => { checks[name] = { status, msg, ...extra }; };

  // 1. what readers are served
  if (!build || !build.built_at) {
    put("deploy", "warn", "build-info.json missing (first deploy after this change?)");
  } else {
    const age = now - build.built_at;
    put("deploy", age > LIMITS.deployFail ? "fail" : age > LIMITS.deployWarn ? "warn" : "ok",
        `deployed build is ${ago(age)} old`, { age_min: Math.round(age / MIN) });

    if (!build.fetch_at) {
      put("fetch", "warn", "no fetch time in the build");
    } else {
      const fa = now - build.fetch_at;
      let st = fa > LIMITS.fetchFail ? "fail" : fa > LIMITS.fetchWarn ? "warn" : "ok";
      let msg = `data fetched ${ago(fa)} ago`;
      if (build.fetch_failed && build.fetch_failed.length) {
        st = worst(st, "warn");
        msg += `; failed sources: ${build.fetch_failed.join(", ")}`;
      }
      put("fetch", st, msg, { age_min: Math.round(fa / MIN) });
    }

    if (!build.newest_article_at) {
      put("articles", "warn", "no article time in the build");
    } else {
      const aa = now - build.newest_article_at;
      put("articles", aa > LIMITS.articleFail ? "fail" : aa > LIMITS.articleWarn ? "warn" : "ok",
          `newest article is ${ago(aa)} old`, { age_min: Math.round(aa / MIN) });
    }

    if (!build.predictions) put("predictions", "warn", "the build holds no predictions");
    else put("predictions", "ok", `${build.predictions} predictions in the build`);
  }

  // 2. the workflows' own reports, and 3. the live store - both need D1
  if (d1Error) {
    put("d1", "fail", `D1 did not answer (${d1Error}) - daily quota?`);
    return finish(checks, now);
  }
  put("d1", "ok", "D1 answers");

  const pub = beats && beats.publish;
  if (!pub) {
    put("publish", "warn", "no publish heartbeat yet");
  } else {
    const ba = now - pub.ts;
    let st = "ok", msg = `last publish run finished ${ago(ba)} ago`;
    if (ba > LIMITS.beatFail) { st = "fail"; msg = `no publish run has finished for ${ago(ba)}`; }
    if (pub.fails >= LIMITS.runFails) {
      st = "fail"; msg = `${pub.fails} publish runs in a row failed: ${pub.detail || "?"}`;
    } else if (!pub.ok) {
      st = worst(st, "warn"); msg += ` (failed: ${pub.detail || "?"})`;
    }
    put("publish", st, msg, { age_min: Math.round(ba / MIN), fails: pub.fails });
  }

  // every article-writing workflow reports as "article:<name>"
  const writers = Object.entries(beats || {}).filter(([k]) => k.startsWith("article:"));
  if (writers.length) {
    const [name, top] = writers.reduce((a, b) => (b[1].fails > a[1].fails ? b : a));
    const n = top.fails;
    put("claude", n >= LIMITS.claudeFail ? "fail" : n >= LIMITS.claudeWarn ? "warn" : "ok",
        n ? `${name.slice(8)}: the Claude step failed ${n} run(s) in a row - token or quota?`
          : "every article workflow's last Claude step succeeded", { fails: n });
  }

  if (!snapshot || !snapshot.ts) {
    put("live", "warn", "the live store has no snapshot yet");
  } else {
    const la = now - snapshot.ts;
    put("live", la > LIMITS.liveFail ? "fail" : la > LIMITS.liveWarn ? "warn" : "ok",
        `live store refreshed ${ago(la)} ago`, { age_min: Math.round(la / MIN) });
  }
  return finish(checks, now);
}

function finish(checks, now) {
  const status = Object.values(checks).reduce((s, c) => worst(s, c.status), "ok");
  return { status, checked_at: now, checks };
}

/* ---------------------------------------------------------------- inputs */
let beatsReady = false;
const BEATS_DDL = "CREATE TABLE IF NOT EXISTS health_beats (name TEXT PRIMARY KEY, " +
                  "ts INTEGER NOT NULL, ok INTEGER NOT NULL, fails INTEGER NOT NULL DEFAULT 0, detail TEXT)";

export async function gather(env) {
  let build = null;
  try {
    const r = await env.ASSETS.fetch(new Request("https://yallascore.site/build-info.json"));
    if (r.ok) build = await r.json();
  } catch (e) { /* stays null -> "deploy" warns */ }

  const out = { build, beats: {}, snapshot: null, d1Error: null };
  if (!env.DB) { out.d1Error = "no binding"; return out; }
  try {
    if (!beatsReady) { await env.DB.prepare(BEATS_DDL).run(); beatsReady = true; }
    const [b, s] = await env.DB.batch([
      env.DB.prepare("/*hb_rows*/ SELECT name, ts, ok, fails, detail FROM health_beats"),
      env.DB.prepare("/*hb_snap*/ SELECT v FROM live_meta WHERE k = 'snapshot'"),
    ]);
    for (const row of b.results || []) out.beats[row.name] = row;
    const v = ((s.results || [])[0] || {}).v;
    if (v) { try { out.snapshot = { ts: Number(JSON.parse(v).ts) }; } catch (e) { /* bad row */ } }
  } catch (e) {
    out.d1Error = (e && e.message || String(e)).slice(0, 120);
  }
  return out;
}

/* ---------------------------------------------------------------- /health */
export async function healthResponse(env, ctx) {
  const cache = caches.default;
  const key = new Request("https://yallascore.site/health");
  const hit = await cache.match(key);
  if (hit) return hit;
  const verdict = evaluate(await gather(env), Date.now());
  // 503 on a failure so any outside uptime monitor can watch this one URL
  const res = new Response(JSON.stringify(verdict, null, 1), {
    status: verdict.status === "fail" ? 503 : 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=0, s-maxage=60",
    },
  });
  if (ctx && ctx.waitUntil) ctx.waitUntil(cache.put(key, res.clone()));
  return res;
}

/* ---------------------------------------------------------------- watchdog */
const LABEL = {
  deploy: "النشر", fetch: "جلب البيانات", articles: "المقالات", predictions: "التوقعات",
  d1: "قاعدة D1", publish: "تشغيلات publish", claude: "كتابة المقالات", live: "النتائج المباشرة",
};

/* Pure: previous alert state + verdict -> what to send (or null) and the new
 * state (or null when nothing changed and nothing needs writing). */
export function decideAlert(prev, verdict, now) {
  const failing = Object.keys(verdict.checks).filter(k => verdict.checks[k].status === "fail").sort();
  const was = (prev && prev.failing) || [];
  const same = failing.length === was.length && failing.every((k, i) => k === was[i]);
  const lines = failing.map(k => `• ${LABEL[k] || k}: ${verdict.checks[k].msg}`);
  const link = "\nhttps://yallascore.site/health";

  if (!failing.length && !was.length) return { text: null, state: null };
  if (!failing.length) {
    const lasted = prev.since ? ` (استمرت ${ago(now - prev.since)})` : "";
    return { text: `✅ يلا سكور رجع طبيعي${lasted}` + link, state: { failing: [], since: null, sent: now } };
  }
  if (!was.length) {
    return { text: "🔴 يلا سكور: مشكلة\n" + lines.join("\n") + link,
             state: { failing, since: now, sent: now } };
  }
  if (!same) {
    return { text: "🟠 يلا سكور: تغيّرت المشكلة\n" + lines.join("\n") + link,
             state: { failing, since: prev.since || now, sent: now } };
  }
  if (now - (prev.sent || 0) >= LIMITS.remindEvery) {
    return { text: `⏰ يلا سكور: المشكلة مستمرة منذ ${ago(now - (prev.since || now))}\n` + lines.join("\n") + link,
             state: { ...prev, sent: now } };
  }
  return { text: null, state: null };
}

async function sendTelegram(env, text) {
  const r = await fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: env.TG_ALERT_CHAT_ID, text, disable_web_page_preview: true }),
  });
  if (!r.ok) throw new Error(`telegram HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
}

export async function watchdog(env, now = Date.now()) {
  const verdict = evaluate(await gather(env), now);
  if (!env.TG_BOT_TOKEN || !env.TG_ALERT_CHAT_ID) {
    console.log("watchdog:", verdict.status, "(no TG_BOT_TOKEN/TG_ALERT_CHAT_ID - not alerting)");
    return { verdict, sent: false };
  }
  // The alert state lives next to the live snapshot. When D1 itself is down
  // (the daily quota runs out until 03:00 Cairo) it cannot be read or saved,
  // so it goes to the edge cache instead - without SOME memory the watchdog
  // would page every 15 minutes all night.
  const d1ok = !!verdict.checks.d1 && verdict.checks.d1.status === "ok";
  let prev = null;
  if (d1ok) {
    const row = await env.DB.prepare("/*wd_get*/ SELECT v FROM live_meta WHERE k = 'watchdog'").first();
    try { prev = row && row.v ? JSON.parse(row.v) : null; } catch (e) { prev = null; }
  } else {
    prev = await cacheState();
  }
  const { text, state } = decideAlert(prev, verdict, now);
  let sent = false;
  if (text) { await sendTelegram(env, text); sent = true; }
  if (state) {
    if (d1ok) {
      await env.DB.prepare("/*wd_set*/ INSERT INTO live_meta (k, v) VALUES ('watchdog', ?) " +
                           "ON CONFLICT(k) DO UPDATE SET v = excluded.v").bind(JSON.stringify(state)).run();
    }
    await cacheState(state);        // both, so a D1 outage starts from the truth
  }
  console.log("watchdog:", verdict.status, sent ? "(alert sent)" : "");
  return { verdict, sent };
}

const STATE_KEY = "https://yallascore.site/__watchdog_state";
async function cacheState(state) {
  try {
    const cache = caches.default, key = new Request(STATE_KEY);
    if (state === undefined) {
      const hit = await cache.match(key);
      return hit ? await hit.json() : null;
    }
    await cache.put(key, new Response(JSON.stringify(state), {
      headers: { "content-type": "application/json", "cache-control": "public, s-maxage=86400" },
    }));
  } catch (e) { /* no cache (tests, local dev) - D1 remains the record */ }
  return null;
}
