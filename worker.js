// Yalla Score edge worker.
// - fetch: serve the static site (dist/) exactly as before via the ASSETS binding.
// - scheduled: Cloudflare cron (exact, reliable) triggers the GitHub Action
//   `publish.yml` through the workflow_dispatch API, so data refreshes every
//   30 minutes even though GitHub's own free-tier cron is best-effort/delayed.
//   Requires a `GH_TOKEN` secret on the Worker (fine-grained PAT with
//   Actions: Read & write on mostafa20182019/yalla-score-site).

export default {
  async fetch(request, env) {
    // Permanent redirect from the legacy *.workers.dev URL (and any other
    // host) to the canonical custom domain — keeps old links, bookmarks and
    // Google-indexed pages working after the 2026-08-03 domain move.
    const url = new URL(request.url);
    const canonical = "yallascore.site";
    if (url.hostname !== canonical && url.hostname !== "www." + canonical) {
      url.hostname = canonical;
      return Response.redirect(url.toString(), 301);
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
