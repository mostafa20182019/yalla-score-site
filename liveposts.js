/* Live Facebook posts from the edge (growth plan weeks 2-3, 2026-10-08).
 *
 * The one thing Egyptian football pages are followed for is being FIRST with
 * the lineup, the goal and the score. The live store already learns a goal
 * within seconds of 365scores (worker.js storeApply diffs every refresh), so
 * the post is written here, at the edge, the moment the diff lands - not
 * minutes later from a GitHub runner.
 *
 *   - «⚽ هدف!»      one post per goal the store DISCOVERED while the match
 *                    was live (a goal already on the board when a match is
 *                    first seen is never posted: we cannot vouch for when it
 *                    fell - the «never show possibly-wrong live data» rule)
 *   - VAR reversal   the goal's own post is EDITED, never left standing
 *   - «📋 التشكيل»   once per match, 45-80 minutes before kick-off, when the
 *                    detail carries eleven named starters on each side
 *
 * Scope is Egyptian only (user's plan): الأهلي / الزمالك / بيراميدز in the
 * Egyptian league (552) and the CAF Champions League (624), and the national
 * team «مصر» in the AFCON qualifiers (588) - matched EXACTLY, because «مصر»
 * is a substring of «المصري» (the Port Said club).
 *
 * Dedup is the same lock the Python side uses: an INSERT on fb_posted's
 * PRIMARY KEY (kind, ref_id) - kinds "goal" (ref "<game>:<seq>") and "xi"
 * (ref "<game>"). Two refreshes racing on the same goal cannot both post.
 *
 * Photo = our matchup card when the site has drawn it for that match
 * (media/matchup-<id>-preview.jpg, checked through the ASSETS binding, no
 * network); else a plain text post. Needs the Worker secret FB_PAGE_TOKEN
 * (the same page token the GitHub workflows hold); without it everything
 * here is a no-op that logs once per tick.
 */

const FB_GRAPH = "https://graph.facebook.com/v23.0";
const SITE = "https://yallascore.site";
export const XI_MIN_MS = 45 * 60 * 1000;    // post the XI when kick-off is
export const XI_MAX_MS = 80 * 60 * 1000;    // 45..80 minutes away

const COMP_AR = { 552: "الدوري المصري", 624: "دوري أبطال أفريقيا", 588: "تصفيات كأس أمم أفريقيا" };

const POST_SCOPE = [
  { t: "الأهلي", comps: [552, 624] },
  { t: "الزمالك", comps: [552, 624] },
  { t: "بيراميدز", comps: [552, 624] },
  { t: "مصر", comps: [588], exact: true },
];
const arNorm = (x) => (x || "").replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي").trim();

export function postScope(g) {
  const c = Number(g.c || 0);
  return POST_SCOPE.some(s => s.comps.includes(c) && (s.exact
    ? [arNorm(g.h), arNorm(g.a)].includes(arNorm(s.t))
    : (arNorm(g.h) + "|" + arNorm(g.a)).includes(arNorm(s.t))));
}

const tag = (name) => "#" + (name || "").trim().replace(/\s+/g, "_");
// «الأهلي 1 - 0 الزمالك» with SPACES: a glued «1-0» is one LTR run and shows
// the away score next to the home name in an RTL line (the .tl lesson)
const scoreLine = (g) => `${g.h} ${g.hs} - ${g.as} ${g.a}`;

export function goalMessage(g, ev) {
  const lines = [`⚽ هدف! ${scoreLine(g)}`];
  const who = [];
  if (ev && ev.p) who.push(ev.p);
  if (ev && ev.m) who.push(`الدقيقة ${ev.m}`);
  if (ev && ev.t === "ج") who.push("ركلة جزاء");
  if (ev && ev.t === "عكسية") who.push("هدف عكسي");
  if (who.length) lines.push("🥅 " + who.join(" · "));
  lines.push(`${COMP_AR[g.c] || ""} · المباراة لحظة بلحظة: ${SITE}/m/${g.id}`.replace(/^ · /, ""));
  lines.push(`#يلا_سكور ${tag(g.h)} ${tag(g.a)}`);
  return lines.join("\n");
}

export function xiMessage(g, xi) {
  const side = (name, s) => [`▪️ ${name}${s.f ? ` (${s.f})` : ""}:`, s.xi.join("، ")];
  return [`📋 التشكيل الرسمي: ${g.h} × ${g.a}`, COMP_AR[g.c] || "",
          ...side(g.h, xi.h), ...side(g.a, xi.a),
          `المباراة لحظة بلحظة: ${SITE}/m/${g.id}`,
          `#يلا_سكور ${tag(g.h)} ${tag(g.a)}`].filter(Boolean).join("\n");
}

/* ------------------------------------------------------------ the lock */
const FB_CLAIM = "/*fb_claim*/ INSERT OR IGNORE INTO fb_posted (kind, ref_id, title, claimed_at) VALUES (?,?,?,?)";
const FB_REC = "/*fb_rec*/ UPDATE fb_posted SET post_id = ?, posted_at = ? WHERE kind = ? AND ref_id = ?";
const FB_FIND = "/*fb_find*/ SELECT post_id FROM fb_posted WHERE kind = ? AND ref_id = ?";
const FB_DROP = "/*fb_drop*/ DELETE FROM fb_posted WHERE kind = ? AND ref_id = ? AND post_id IS NULL";
const LG_CANCELLED = "/*lg_cancelled*/ SELECT seq FROM live_goals WHERE game_id = ? AND side = ? AND cancelled = 1 " +
  "AND (? = '' OR COALESCE(player,'') = ?) AND (? = '' OR COALESCE(minute,'') = ?) ORDER BY cancelled_at DESC, seq DESC LIMIT 1";

async function claim(env, kind, ref, title) {
  const r = await env.DB.prepare(FB_CLAIM).bind(kind, ref, title, Math.floor(Date.now() / 1000)).run();
  return !!(r && r.meta && r.meta.changes);
}
async function record(env, kind, ref, postId) {
  await env.DB.prepare(FB_REC).bind(postId, Math.floor(Date.now() / 1000), kind, ref).run();
}
async function drop(env, kind, ref) {
  await env.DB.prepare(FB_DROP).bind(kind, ref).run();
}
async function findPost(env, kind, ref) {
  const r = await env.DB.prepare(FB_FIND).bind(kind, ref).first();
  return r && r.post_id ? String(r.post_id) : null;
}

/* ----------------------------------------------------------- Facebook */
async function graph(env, path, params) {
  const body = new URLSearchParams({ ...params, access_token: env.FB_PAGE_TOKEN });
  const r = await fetch(`${FB_GRAPH}/${path}`, {
    method: "POST", body,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  if (!r.ok) { console.log("facebook", path, r.status, (await r.text()).slice(0, 200)); return null; }
  return r.json();
}

// our card for this match, if the site has drawn it (no network: the ASSETS
// binding answers from the deployed dist/)
export async function cardUrl(env, gid) {
  const url = `${SITE}/media/matchup-${gid}-preview.jpg`;
  try {
    if (!env.ASSETS) return null;
    const r = await env.ASSETS.fetch(new Request(url, { method: "HEAD" }));
    return r.ok ? url : null;
  } catch (e) { return null; }
}

async function publish(env, message, photo) {
  if (photo) {
    const j = await graph(env, "me/photos", { url: photo, caption: message });
    if (j && (j.post_id || j.id)) return String(j.post_id || j.id);
  }
  const j = await graph(env, "me/feed", { message });
  return j && j.id ? String(j.id) : null;
}

/* ------------------------------------------------------- goals + VAR */
// r = storeApply's result: posts [{g, seq, ev}], cancels [{g, ev}]
export async function livePosts(env, r) {
  const out = { posted: 0, edited: 0, skipped: 0 };
  const posts = (r && r.posts || []).filter(x => postScope(x.g));
  const cancels = (r && r.cancels || []).filter(x => postScope(x.g));
  if (!posts.length && !cancels.length) return out;
  if (!env.FB_PAGE_TOKEN) { console.log("live posts: no FB_PAGE_TOKEN -", posts.length, "goal(s) not posted"); return out; }
  for (const { g, seq, ev } of posts) {
    const ref = `${g.id}:${seq}`;
    const msg = goalMessage(g, ev);
    if (!(await claim(env, "goal", ref, msg.split("\n")[0]))) { out.skipped += 1; continue; }
    const pid = await publish(env, msg, await cardUrl(env, g.id));
    if (pid) { await record(env, "goal", ref, pid); out.posted += 1; }
    else await drop(env, "goal", ref);            // a later refresh may not retry (the diff is gone) - the lock must not stay
  }
  for (const { g, ev } of cancels) {
    const row = await env.DB.prepare(LG_CANCELLED)
      .bind(g.id, ev.s, ev.p || "", ev.p || "", ev.m || "", ev.m || "").first();
    if (!row) continue;
    const pid = await findPost(env, "goal", `${g.id}:${row.seq}`);
    if (!pid) continue;
    const msg = `❌ أُلغي الهدف بعد مراجعة الفيديو (VAR)\n` + goalMessage(g, ev).replace("⚽ هدف! ", "كان: ");
    const j = await graph(env, pid, { message: msg });
    if (j) out.edited += 1;
  }
  return out;
}

/* ---------------------------------------------------------- lineups */
// game/ detail -> {h: {f, xi: [names]}, a: {...}} only when BOTH sides carry
// eleven named starters (mirrors fetch_data's "anything else = broken feed")
export function parseLineups(game) {
  const members = {};
  for (const m of game.members || []) members[m.id] = (m.name || "").trim();
  const out = {};
  for (const [side, comp] of [["h", game.homeCompetitor || {}], ["a", game.awayCompetitor || {}]]) {
    const lu = comp.lineups;
    if (!lu || typeof lu !== "object") return null;
    const xi = [];
    for (const mm of lu.members || []) {
      if (mm.status !== 1) continue;
      const name = members[mm.id || mm.playerId || mm.athleteId];
      if (name) xi.push(name);
    }
    if (xi.length !== 11) return null;
    const f = lu.formation;
    out[side] = { f: typeof f === "string" ? f : (f && f.name) || "", xi };
  }
  return out;
}

async function gameLineups(gid, headers) {
  try {
    const r = await fetch(`https://webws.365scores.com/web/game/?appTypeId=5&langId=27&gameId=${gid}`,
      { headers, cf: { cacheTtl: 30, cacheEverything: true } });
    if (!r.ok) return null;
    return parseLineups((await r.json()).game || {});
  } catch (e) { return null; }
}

// upcoming = [{id, c, h, a, start}] from the list (statusGroup 2), every minute
export async function lineupPosts(env, upcoming, now, headers) {
  const out = { due: 0, posted: 0, waiting: 0 };
  const due = (upcoming || []).filter(g => postScope(g) && g.start - now >= XI_MIN_MS && g.start - now <= XI_MAX_MS);
  out.due = due.length;
  if (!due.length) return out;
  if (!env.FB_PAGE_TOKEN) { console.log("xi posts: no FB_PAGE_TOKEN -", due.length, "match(es) not posted"); return out; }
  for (const g of due) {
    const ref = String(g.id);
    if (await findPost(env, "xi", ref)) continue;          // already out
    const xi = await gameLineups(g.id, headers);
    if (!xi) { out.waiting += 1; continue; }                // not announced yet: next minute
    const msg = xiMessage(g, xi);
    if (!(await claim(env, "xi", ref, msg.split("\n")[0]))) continue;
    const pid = await publish(env, msg, await cardUrl(env, g.id));
    if (pid) { await record(env, "xi", ref, pid); out.posted += 1; }
    else await drop(env, "xi", ref);
  }
  return out;
}
