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

async function liveScores() {
  const upstream =
    `https://webws.365scores.com/web/games/current/?competitions=${LIVE_COMPS}` +
    `&langId=27&timezoneName=Africa/Cairo&showOdds=false`;
  const games = [];
  let ok = false;
  try {
    const r = await fetch(upstream, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ar,en;q=0.9",
        "Origin": "https://www.365scores.com",
        "Referer": "https://www.365scores.com/",
      },
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
        games.push({
          h: h.name || "", a: a.name || "",
          hs: Math.round(h.score), as: Math.round(a.score),
          live: sg === 3,
          min: sg === 3 ? (g.gameTimeDisplay || "") : "",
        });
      }
    }
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
