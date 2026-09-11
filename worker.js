// Yalla Score edge worker.
// - fetch: serve the static site (dist/) exactly as before via the ASSETS binding.
// - scheduled: Cloudflare cron (exact, reliable) triggers the GitHub Action
//   `publish.yml` through the workflow_dispatch API, so data refreshes every
//   30 minutes even though GitHub's own free-tier cron is best-effort/delayed.
//   Requires a `GH_TOKEN` secret on the Worker (fine-grained PAT with
//   Actions: Read & write on mostafa20182019/yalla-score-site).

// Live-scores edge endpoint (/live.json): proxies 365scores' current-games
// feed with a 30s edge cache, so every visitor polls US (cheap, same-origin)
// and 365scores sees at most ~2 requests/minute regardless of traffic.
// Fail-empty by design: any upstream problem returns {games:[]} and the
// static site simply behaves as before (15-min refresh).
const LIVE_COMPS = "552,78,649,7,11,17,25,35,572,624"; // EGY,TUR,KSA,PL,PD,SA,BL1,FL1,UCL,CAF-CL

const S365_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "ar,en;q=0.9",
  "Origin": "https://www.365scores.com",
  "Referer": "https://www.365scores.com/",
};

const DETAIL_CAP = 12;   // per cache-miss ceiling on game/ detail calls
// 365scores competitions whose live games get detail calls FIRST (Egyptian
// league + CAF CL) — the rest fill the remaining cap slots.
const DETAIL_FIRST = new Set([552, 624]);

// half-time: measured live on 2026-08-23 (Hull x Man Utd) - during the break
// statusText AND shortStatusText are the bare word "شوط" with gameTimeDisplay
// frozen at 45'; in play they are "الشوط الأول/الثاني" and "1"/"2". So the
// break test is EXACT equality with the bare word - a substring would match
// every in-play status too. The استراحة/half-time/HT checks stay as tolerance
// for other wordings. "نهاية الشوط الأول" is the transitional wording right
// after the HT whistle (FULL phrase only — "نهاية الشوط الثاني" is full-time,
// not a break).
function halfTime(g) {
  const stx = (g.statusText || "").trim(), ssx = (g.shortStatusText || "").trim();
  const st = `${stx} ${ssx} ${g.gameTimeDisplay || ""}`;
  return stx === "شوط" || ssx === "شوط"
    || stx.includes("نهاية الشوط الأول") || ssx.includes("نهاية الشوط الأول")
    || st.includes("استراح") || /half\s*-?\s*time/i.test(st) || /\bHT\b/.test(st);
}

// minute fields for a LIVE game object (list item or detail game — same shape):
// min = display text, gt = numeric minute for the client-side minute clock
// (LIVE_JS advances it locally between polls), hf = half (45+/90+ cap)
function liveFields(g) {
  const ht = halfTime(g);
  return {
    min: ht ? "استراحة" : (g.gameTimeDisplay || ""),
    gt: !ht && g.gameTime > 0 ? g.gameTime : 0,
    hf: (g.shortStatusText || "").trim() === "2" ? 2 : 1,
  };
}

// One game/ detail call. 2026-09-02 (Ceramica x Modern Sport): the games/current
// LIST lagged this endpoint by ~2 minutes — a 63' goal was listed while the
// list still said 1-0 at 61'. So the detail is the source of ALL numbers for a
// live game (score, minute, half, goals) and the list only discovers which
// games are live. Returns null on any failure → the caller keeps list values.
// Scorer lines mirror fetch_data._goal_rows(): goal events only (VAR-disallowed
// excluded), own-goal side flip, and the reconciliation guard against THIS
// reply's score — a list that doesn't add up is never published.
async function gameDetail(gid) {
  try {
    const r = await fetch(
      `https://webws.365scores.com/web/game/?appTypeId=5&langId=27&gameId=${gid}`,
      { headers: S365_HEADERS, cf: { cacheTtl: 12, cacheEverything: true } });
    if (!r.ok) return null;
    const game = (await r.json()).game || {};
    const home = game.homeCompetitor || {}, away = game.awayCompetitor || {};
    if (home.score == null || home.score < 0 || away.score == null || away.score < 0) return null;
    const hs = Math.round(home.score), as_ = Math.round(away.score);
    const sg = game.statusGroup;
    const out = {
      hs, as: as_,
      // apply score/status only when the detail carries a known status group
      // (3 live / 4 ended); goals are usable either way
      apply: sg === 3 || sg === 4,
      live: sg === 3,
      ...(sg === 3 ? liveFields(game) : { min: "", gt: 0, hf: 0 }),
      goals: null,
    };
    const members = {};
    for (const m of game.members || []) members[m.id] = m.name;
    const goals = [];
    for (const ev of game.events || []) {
      const et = ev.eventType || ev.type || {};
      const nm = typeof et === "object" ? (et.name || "") : String(et);
      if (!nm.includes("هدف")) continue;
      if (nm.includes("ملغ") || nm.includes("ألغي") || nm.includes("الغي")) continue;
      let cid = ev.competitorId;
      if (cid == null) cid = ev.num === 1 ? home.id : -1;
      const player = members[ev.playerId]
        || (ev.player && ev.player.name) || ev.playerName;
      if (!player) continue;
      let minute = "";
      const gt = Math.trunc(Number(ev.gameTime));
      if (gt > 0) {
        const add = Math.trunc(Number(ev.addedTime || 0));
        minute = add > 0 ? `${gt}+${add}` : String(gt);
      }
      const sub = `${nm} ${ev.subTypeName || ""}`;
      const tag = sub.includes("عكس") ? "عكسية" : (sub.includes("جزاء") ? "ج" : "");
      goals.push({ s: cid === home.id ? "h" : "a", p: player, m: minute, t: tag });
    }
    const cnt = () => [goals.filter(g => g.s === "h").length,
                       goals.filter(g => g.s === "a").length];
    let [ch, ca] = cnt();
    if (ch !== hs || ca !== as_) {
      for (const g of goals) if (g.t === "عكسية") g.s = g.s === "h" ? "a" : "h";
      [ch, ca] = cnt();
    }
    if (ch === hs && ca === as_ && goals.length) out.goals = goals;
    return out;
  } catch (e) { return null; }
}

async function fetchGames(url) {
  const r = await fetch(url, {
    headers: S365_HEADERS,
    cf: { cacheTtl: 12, cacheEverything: true },
  });
  if (!r.ok) return null;
  return (await r.json()).games || [];
}

async function liveScores() {
  const base =
    "https://webws.365scores.com/web/games/current/?appTypeId=5" +
    "&langId=27&timezoneName=Africa/Cairo&showOdds=false";
  const games = [];
  const wantDetail = [];  // {idx, gid, live, first} — live games + just-ended with a goal
  let ok = false, src = "multi", dt = 0;
  try {
    let raw = null;
    try { raw = await fetchGames(`${base}&competitions=${LIVE_COMPS}`); } catch (e) { raw = null; }
    // 365scores intermittently serves the multi-competition query a degraded
    // near-empty reply (2026-09-01: ONE scheduled PL game, HTTP 200, while a
    // live Egyptian match was in play — single-competition queries kept
    // returning everything). A healthy multi reply carries today's whole
    // window (~dozens of games), so a tiny list = degraded → refetch split
    // per competition and merge (lists are disjoint, no dedup needed).
    if (!raw || raw.length < 5) {
      src = "split";
      const per = await Promise.all(LIVE_COMPS.split(",").map(c =>
        fetchGames(`${base}&competitions=${c}`).catch(() => null)));
      raw = [];
      ok = false;
      for (const list of per) if (list) { ok = true; raw.push(...list); }
    } else {
      ok = true;
      // Partial degradation (2026-09-04): the multi-comp reply was a healthy
      // size yet MISSED the just-ended CAF CL game (AS Port x Zamalek, sg 4)
      // that the single-comp query returned - so /live.json had no final
      // score for it and the match page stayed on the baked "مباشر" dashes.
      // The Egyptian-scope comps are what the site is FOR: always fetch them
      // individually too and merge by game id (2 extra edge-cached calls).
      const extra = await Promise.all([...DETAIL_FIRST].map(c =>
        fetchGames(`${base}&competitions=${c}`).catch(() => null)));
      const seen = new Set(raw.map(g => g.id));
      for (const list of extra) for (const g of list || []) {
        if (!seen.has(g.id)) { seen.add(g.id); raw.push(g); src = "multi+egy"; }
      }
    }
    for (const g of raw) {
        const sg = g.statusGroup;            // 2 scheduled / 3 live / 4 ended
        if (sg !== 3 && sg !== 4) continue;  // live + finished (final score)
        const h = g.homeCompetitor || {}, a = g.awayCompetitor || {};
        if (h.score == null || h.score < 0 || a.score == null || a.score < 0) continue;
        // half-time / minute fields: see halfTime() + liveFields() above
        const lf = sg === 3 ? liveFields(g) : { min: "", gt: 0, hf: 0 };
        const c = g.competitionId || 0;
        games.push({
          h: h.name || "", a: a.name || "",
          hs: Math.round(h.score), as: Math.round(a.score),
          live: sg === 3,
          // min/gt/hf: minute text + numeric minute + half for the client-side
          // minute clock (LIVE_JS advances it locally between polls)
          min: lf.min, gt: lf.gt, hf: lf.hf,
          // 365scores competition id — LIVE_JS disambiguates same-name clubs
          // across leagues with it (الأهلي = Al Ahly Egypt AND Al-Ahli Saudi)
          c,
        });
        // detail call: EVERY live game (fresher score/minute than the list)
        // plus just-ended games with a goal the static build hasn't caught yet
        if (g.id && (sg === 3 || (g.justEnded === true && (h.score > 0 || a.score > 0)))) {
          wantDetail.push({ idx: games.length - 1, gid: g.id, live: sg === 3,
                            first: DETAIL_FIRST.has(c) });
        }
    }
    // priority: live before just-ended, Egyptian/CAF before the rest, capped —
    // each detail call is itself edge-cached 12s so bursts collapse upstream.
    // Games past the cap simply keep their list values (the old behaviour).
    wantDetail.sort((x, y) => ((y.live ? 2 : 0) + (y.first ? 1 : 0))
                            - ((x.live ? 2 : 0) + (x.first ? 1 : 0)));
    await Promise.all(wantDetail.slice(0, DETAIL_CAP).map(async (w) => {
      const d = await gameDetail(w.gid);
      if (!d) return;
      const g = games[w.idx];
      // override ONLY games the LIST says are live: a match the list has
      // already ended must never come back to life because the detail
      // endpoint is slower to record the final whistle (live data may move
      // forward from another source, never backwards). Just-ended games get
      // their goals only.
      if (d.apply && w.live) {
        g.hs = d.hs; g.as = d.as; g.live = d.live;
        g.min = d.min; g.gt = d.gt; g.hf = d.hf;
        dt++;
      }
      if (d.goals) g.goals = d.goals;
    }));
  } catch (e) { /* fail-empty */ }
  // an upstream failure must NOT be cached for 30s - visitors would all go
  // quiet for minutes mid-match; mark it uncacheable instead
  return new Response(JSON.stringify({ games, ok, ts: Date.now(), src, dt }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": ok ? "public, max-age=10, s-maxage=15" : "no-store",
    },
  });
}

/* ==========================================================================
 * /admin/api — the admin page's door to D1.
 *
 * A browser cannot talk to D1: access is through a Worker binding (or an
 * account-wide API token, which would then be sitting in localStorage on a
 * laptop). So the Worker that already serves this site holds the binding and
 * exposes the few operations the admin page needs.
 *
 * FAIL CLOSED. Every route needs the x-admin-token header to match the
 * ADMIN_TOKEN Worker secret, and when that secret is not set the routes
 * answer 503 rather than being open. Cloudflare Access can be layered in
 * front later for a second factor; trusting its Cf-Access-* headers without
 * verifying the JWT would be security theatre, so that is deliberately not
 * done here.
 *
 * Writes go through the SAME rules as article_put.py: the id is allocated
 * inside the INSERT, and the unique index on (match_id, kind) refuses a
 * duplicate match piece.
 * ======================================================================== */

const ADMIN_ORIGINS = ["http://localhost:8123", "http://127.0.0.1:8123",
                       "https://yallascore.site"];

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allow = ADMIN_ORIGINS.includes(origin) ? origin : ADMIN_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "content-type, x-admin-token",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function jsonReply(request, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...corsHeaders(request),
    },
  });
}

/* the json shape the admin page and data/articles.json both use */
const ART_FIELDS = ["title", "summary", "body", "author", "pub_date", "pub_ts",
                    "match_id", "kind", "image_url", "image_credit", "fb_post",
                    "updated_ts", "upgraded_ts"];

function words(html) {
  return (String(html || "").replace(/<[^>]+>/g, " ").trim().split(/\s+/)
          .filter(Boolean)).length;
}

async function articleRow(env, id) {
  const a = await env.DB.prepare(
    "SELECT article_id, title, summary, body, author, pub_date, pub_ts, " +
    "match_id, kind, image_url, image_credit, fb_post, updated_ts, " +
    "upgraded_ts, words, thin FROM articles WHERE article_id = ?"
  ).bind(String(id)).first();
  if (!a) return null;
  const kids = await env.DB.batch([
    env.DB.prepare("SELECT name, url, note FROM article_sources WHERE article_id = ? ORDER BY seq").bind(String(id)),
    env.DB.prepare("SELECT q, a FROM article_faq WHERE article_id = ? ORDER BY seq").bind(String(id)),
  ]);
  a.sources = kids[0].results || [];
  a.faq = kids[1].results || [];
  return a;
}

async function writeChildren(env, id, sources, faq) {
  const stmts = [
    env.DB.prepare("DELETE FROM article_sources WHERE article_id = ?").bind(id),
    env.DB.prepare("DELETE FROM article_faq WHERE article_id = ?").bind(id),
  ];
  (sources || []).forEach((x, i) => stmts.push(env.DB.prepare(
    "INSERT INTO article_sources (article_id, seq, name, url, note) VALUES (?, ?, ?, ?, ?)"
  ).bind(id, i, x.name || null, x.url || null, x.note || null)));
  (faq || []).forEach((x, i) => stmts.push(env.DB.prepare(
    "INSERT INTO article_faq (article_id, seq, q, a) VALUES (?, ?, ?, ?)"
  ).bind(id, i, x.q || null, x.a || null)));
  await env.DB.batch(stmts);
}

/* ask GitHub to rebuild: writing to D1 makes the article EXIST, but the site
 * is static HTML - it only appears once publish.yml has rebuilt the pages.
 * reason=article marks the run uncancellable (it carries new content). */
async function dispatchPublish(env) {
  if (!env.GH_TOKEN) return "no GH_TOKEN - publish not triggered";
  const r = await fetch(
    "https://api.github.com/repos/mostafa20182019/yalla-score-site/actions/workflows/publish.yml/dispatches",
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "yalla-score-worker",
      },
      body: JSON.stringify({ ref: "main", inputs: { reason: "article" } }),
    }
  );
  return r.ok ? "publish dispatched" : `publish dispatch failed (${r.status})`;
}

async function adminApi(request, env, url) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  if (!env.DB) {
    return jsonReply(request, { error: "D1 binding missing on the Worker" }, 503);
  }
  if (!env.ADMIN_TOKEN) {
    return jsonReply(request, {
      error: "ADMIN_TOKEN is not set on the Worker - the admin API is closed",
    }, 503);
  }
  if (request.headers.get("x-admin-token") !== env.ADMIN_TOKEN) {
    return jsonReply(request, { error: "bad or missing x-admin-token" }, 401);
  }

  const parts = url.pathname.replace(/^\/admin\/api\/?/, "").split("/");

  // GET /admin/api/articles — the list, WITHOUT bodies (403 bodies is ~800KB
  // and the list only shows titles)
  if (request.method === "GET" && parts[0] === "articles") {
    const { results } = await env.DB.prepare(
      "SELECT article_id, title, pub_date, pub_ts, author, image_url, kind, " +
      "match_id, words, thin, has_sources, has_faq, upgraded_ts FROM articles " +
      "ORDER BY CAST(article_id AS INTEGER) DESC"
    ).all();
    return jsonReply(request, { items: results || [] });
  }

  // GET /admin/api/article/<id> — the full record, for the edit form
  if (request.method === "GET" && parts[0] === "article" && parts[1]) {
    const a = await articleRow(env, parts[1]);
    return a ? jsonReply(request, a)
             : jsonReply(request, { error: "no such article" }, 404);
  }

  // POST /admin/api/article — publish a new one
  if (request.method === "POST" && parts[0] === "article") {
    let rec;
    try { rec = await request.json(); }
    catch (e) { return jsonReply(request, { error: "body is not json" }, 400); }
    for (const f of ["title", "summary", "body", "author", "pub_date"]) {
      if (!String(rec[f] || "").trim()) {
        return jsonReply(request, { error: `missing ${f}` }, 400);
      }
    }
    if (!!rec.match_id !== !!rec.kind) {
      return jsonReply(request, { error: "match_id and kind go together" }, 400);
    }
    const w = words(rec.body);
    const cols = ART_FIELDS.concat(["words", "thin", "has_sources", "has_faq"]);
    const vals = ART_FIELDS.map(f => (rec[f] === undefined || rec[f] === "" ? null : rec[f]))
      .concat([w, w < 300 ? 1 : 0,
               (rec.sources || []).length ? 1 : 0, (rec.faq || []).length ? 1 : 0]);
    let row;
    try {
      // the id is allocated INSIDE the statement, so two saves at the same
      // moment cannot be handed the same one
      row = await env.DB.prepare(
        "INSERT INTO articles (article_id, " + cols.join(", ") + ", as_of) " +
        "SELECT CAST(COALESCE(MAX(CAST(article_id AS INTEGER)), 0) + 1 AS TEXT), " +
        cols.map(() => "?").join(", ") + ", date('now') FROM articles " +
        "RETURNING article_id"
      ).bind(...vals).first();
    } catch (e) {
      const m = String(e);
      if (/UNIQUE|constraint/i.test(m)) {
        return jsonReply(request, {
          error: "that match already has a piece of this kind",
        }, 409);
      }
      return jsonReply(request, { error: m }, 500);
    }
    const id = String(row.article_id);
    await writeChildren(env, id, rec.sources, rec.faq);
    return jsonReply(request, {
      article_id: id, words: w, thin: w < 300,
      publish: await dispatchPublish(env),
    }, 201);
  }

  // PUT /admin/api/article/<id> — edit an existing one. Only the fields in the
  // body are touched, so a partial save cannot blank a column it never sent.
  if (request.method === "PUT" && parts[0] === "article" && parts[1]) {
    const id = String(parts[1]);
    let rec;
    try { rec = await request.json(); }
    catch (e) { return jsonReply(request, { error: "body is not json" }, 400); }
    const exists = await env.DB.prepare(
      "SELECT article_id FROM articles WHERE article_id = ?").bind(id).first();
    if (!exists) return jsonReply(request, { error: "no such article" }, 404);

    const sets = [], vals = [];
    for (const f of ART_FIELDS) {
      if (f in rec) { sets.push(`${f} = ?`); vals.push(rec[f] === "" ? null : rec[f]); }
    }
    let w = null;
    if ("body" in rec) {
      w = words(rec.body);
      sets.push("words = ?", "thin = ?");
      vals.push(w, w < 300 ? 1 : 0);
    }
    if ("sources" in rec) { sets.push("has_sources = ?"); vals.push((rec.sources || []).length ? 1 : 0); }
    if ("faq" in rec) { sets.push("has_faq = ?"); vals.push((rec.faq || []).length ? 1 : 0); }
    if (sets.length) {
      try {
        await env.DB.prepare(
          `UPDATE articles SET ${sets.join(", ")} WHERE article_id = ?`
        ).bind(...vals, id).run();
      } catch (e) {
        const m = String(e);
        if (/UNIQUE|constraint/i.test(m)) {
          return jsonReply(request, {
            error: "that match already has a piece of this kind",
          }, 409);
        }
        return jsonReply(request, { error: m }, 500);
      }
    }
    if ("sources" in rec || "faq" in rec) {
      await writeChildren(env, id, rec.sources, rec.faq);
    }
    return jsonReply(request, {
      article_id: id, words: w, publish: await dispatchPublish(env),
    });
  }

  return jsonReply(request, { error: `no route for ${request.method} ${url.pathname}` }, 404);
}

// The match-article slots, on the Cairo clock. Exported for the test.
const MATCH_SLOTS = ["13:00", "17:00", "20:00", "23:30"];
const MATCH_CRONS = new Set(["0 9,10,13,14,16,17 * * *", "30 19,20 * * *"]);
export function matchSlotCairo(date) {
  const hm = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Cairo", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date).replace(/^24/, "00");
  return MATCH_SLOTS.includes(hm) ? hm : null;
}

export default {
  async fetch(request, env, ctx) {
    // Permanent redirect from any non-canonical host — the legacy
    // *.workers.dev URL and the www. variant — to the bare custom domain.
    // One canonical URL keeps old links working and avoids duplicate
    // content in Google after the 2026-08-03 domain move.
    const url = new URL(request.url);
    const canonical = "yallascore.site";
    if (url.hostname !== canonical) {
      url.hostname = canonical;
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/admin/api" || url.pathname.startsWith("/admin/api/")) {
      return adminApi(request, env, url);
    }
    if (url.pathname === "/live.json") {
      const cache = caches.default;
      const key = new Request("https://yallascore.site/live.json");
      const hit = await cache.match(key);
      if (hit) return hit;
      const res = await liveScores();
      if ((res.headers.get("cache-control") || "").includes("s-maxage")) {
        ctx.waitUntil(cache.put(key, res.clone()));
      }
      return res;
    }
    return env.ASSETS.fetch(request);
  },

  async scheduled(event, env, ctx) {
    if (!env.GH_TOKEN) {
      console.log("GH_TOKEN secret not set yet; skipping workflow dispatch");
      return;
    }
    // four crons share this handler — event.cron says which one fired (each
    // string must equal its line in wrangler.toml [triggers] EXACTLY):
    //   cron 2          -> daily-article.yml
    //   cron 3 / cron 4 -> match-article.yml, but only when the CAIRO clock is
    //                      on one of the four slots (the crons list both the
    //                      summer and the winter UTC hour of every slot)
    //   anything else   -> publish.yml (the 15-minute refresh)
    let workflow = "publish.yml";
    if (event.cron === "0 6,8,10,12,14,15,17,18,19,20 * * *") {
      workflow = "daily-article.yml";
    } else if (MATCH_CRONS.has(event.cron)) {
      const slot = matchSlotCairo(new Date(event.scheduledTime || Date.now()));
      if (!slot) {
        console.log("match-article cron fired off-slot (DST twin) - skipping");
        return;
      }
      workflow = "match-article.yml";
    }
    const res = await fetch(
      `https://api.github.com/repos/mostafa20182019/yalla-score-site/actions/workflows/${workflow}/dispatches`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GH_TOKEN}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "yalla-score-cron",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );
    // 204 = accepted; anything else is logged for debugging (visible in
    // Cloudflare dashboard -> Worker -> Logs).
    console.log("workflow dispatch:", workflow, res.status, res.status === 204 ? "OK" : await res.text());
  },
};
