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
const LIVE_COMPS = "552,78,649,7,11,17,25,35,572"; // EGY,TUR,KSA,PL,PD,SA,BL1,FL1,UCL

const S365_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "ar,en;q=0.9",
  "Origin": "https://www.365scores.com",
  "Referer": "https://www.365scores.com/",
};

// Live scorer lines. One game/ detail call per live match that has a goal,
// mirroring fetch_data._goal_rows(): goal events only (VAR-disallowed ones
// excluded), own-goal side flip, and the scoreboard-reconciliation guard —
// a list that doesn't add up to the score is dropped (null) rather than
// published wrong; the static 15-min build remains the fallback.
const GOAL_DETAIL_CAP = 10;   // per cache-miss ceiling on game/ detail calls

async function gameGoals(gid) {
  try {
    const r = await fetch(
      `https://webws.365scores.com/web/game/?appTypeId=5&langId=27&gameId=${gid}`,
      { headers: S365_HEADERS, cf: { cacheTtl: 20, cacheEverything: true } });
    if (!r.ok) return null;
    const game = (await r.json()).game || {};
    const members = {};
    for (const m of game.members || []) members[m.id] = m.name;
    const home = game.homeCompetitor || {}, away = game.awayCompetitor || {};
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
    const hs = Math.round(home.score || 0), as_ = Math.round(away.score || 0);
    const cnt = () => [goals.filter(g => g.s === "h").length,
                       goals.filter(g => g.s === "a").length];
    let [ch, ca] = cnt();
    if (ch !== hs || ca !== as_) {
      for (const g of goals) if (g.t === "عكسية") g.s = g.s === "h" ? "a" : "h";
      [ch, ca] = cnt();
      if (ch !== hs || ca !== as_) return null;
    }
    return goals;
  } catch (e) { return null; }
}

async function liveScores() {
  const upstream =
    `https://webws.365scores.com/web/games/current/?competitions=${LIVE_COMPS}` +
    `&langId=27&timezoneName=Africa/Cairo&showOdds=false`;
  const games = [];
  const wantGoals = [];   // {idx, gid, live} — live/just-ended games with a goal
  let ok = false;
  try {
    const r = await fetch(upstream, {
      headers: S365_HEADERS,
      cf: { cacheTtl: 25, cacheEverything: true },
    });
    if (r.ok) {
      ok = true;
      const d = await r.json();
      for (const g of d.games || []) {
        const sg = g.statusGroup;            // 2 scheduled / 3 live / 4 ended
        if (sg !== 3 && sg !== 4) continue;  // live + finished (final score)
        const h = g.homeCompetitor || {}, a = g.awayCompetitor || {};
        if (h.score == null || h.score < 0 || a.score == null || a.score < 0) continue;
        // half-time: measured live on 2026-08-23 (Hull x Man Utd) - during
        // the break this endpoint reports statusText AND shortStatusText as
        // the bare word "شوط" with gameTimeDisplay frozen at 45'; in play they
        // are "الشوط الأول/الثاني" and "1"/"2". So the break test is EXACT
        // equality with the bare word - a substring would match every in-play
        // status too. The استراحة/half-time/HT checks stay as tolerance for
        // other wordings 365scores may use elsewhere.
        const stx = (g.statusText || "").trim(), ssx = (g.shortStatusText || "").trim();
        const st = `${stx} ${ssx} ${g.gameTimeDisplay || ""}`;
        const ht = sg === 3 && (stx === "شوط" || ssx === "شوط"
          || st.includes("استراح") || /half\s*-?\s*time/i.test(st) || /\bHT\b/.test(st));
        games.push({
          h: h.name || "", a: a.name || "",
          hs: Math.round(h.score), as: Math.round(a.score),
          live: sg === 3,
          min: sg === 3 ? (ht ? "استراحة" : (g.gameTimeDisplay || "")) : "",
          // 365scores competition id — LIVE_JS needs it to disambiguate
          // same-name clubs across leagues (الأهلي = Al Ahly Egypt AND
          // Al-Ahli Saudi; the favourite-club card once showed the wrong one)
          c: g.competitionId || 0,
        });
        // scorer lines: live games (and just-ended ones the static build
        // hasn't caught yet) that actually have a goal to name
        if (g.id && (sg === 3 || g.justEnded === true)
            && (h.score > 0 || a.score > 0)) {
          wantGoals.push({ idx: games.length - 1, gid: g.id, live: sg === 3 });
        }
      }
    }
    // live matches first, then just-ended, capped — each detail call is
    // itself edge-cached 20s so bursts collapse upstream
    wantGoals.sort((x, y) => (y.live ? 1 : 0) - (x.live ? 1 : 0));
    await Promise.all(wantGoals.slice(0, GOAL_DETAIL_CAP).map(async (w) => {
      const gl = await gameGoals(w.gid);
      if (gl && gl.length) games[w.idx].goals = gl;
    }));
  } catch (e) { /* fail-empty */ }
  // an upstream failure must NOT be cached for 30s - visitors would all go
  // quiet for minutes mid-match; mark it uncacheable instead
  return new Response(JSON.stringify({ games, ok, ts: Date.now() }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": ok ? "public, max-age=15, s-maxage=30" : "no-store",
    },
  });
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
    const res = await fetch(
      "https://api.github.com/repos/mostafa20182019/yalla-score-site/actions/workflows/publish.yml/dispatches",
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
    console.log("workflow dispatch:", res.status, res.status === 204 ? "OK" : await res.text());
  },
};
