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
 *                    detail carries eleven named starters on each side. Since
 *                    2026-10-17 it is a PICTURE: the Worker cannot draw, so
 *                    it takes the "xi" lock and dispatches fb-post.yml with
 *                    xi=<game>; fb_post.py --xi draws the pitch (lineup_card
 *                    .py) and posts it. No GH_TOKEN, a failed dispatch, or a
 *                    runner that has not posted within XI_FALLBACK_MS = the
 *                    text post from here, as before
 *
 * Scope (user, 2026-10-17: «تابع نتائج الفرق المميزة ونزّل بوستات لما يتم
 * إحراز أهداف أو انتهاء الشوط الأول أو انتهاء المباراة») = EVERY curated club:
 * الأهلي / الزمالك / بيراميدز in the Egyptian league (552) and the CAF
 * Champions League (624), the national team «مصر» in the AFCON qualifiers
 * (588) - matched EXACTLY, because «مصر» is a substring of «المصري» (the Port
 * Said club) -, طرابزون سبور in the Turkish league and the Europa League, and
 * the seven European clubs in any competition we follow. CURATED_LIVE here
 * is the ONE list; worker.js imports it for the report queue too.
 *
 *   - «⏸️ نهاية الشوط الأول»  once, the refresh that first sees the break
 *   - «🏁 انتهت المباراة»      once, the refresh that sees live -> ended,
 *                             with the scorers the store logged
 *
 * Dedup is the same lock the Python side uses: an INSERT on fb_posted's
 * PRIMARY KEY (kind, ref_id) - kinds "goal" (ref "<game>:<seq>"), "xi",
 * "ht" and "ft" (ref "<game>"). Two refreshes racing cannot both post.
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
export const XI_FALLBACK_MS = 12 * 60 * 1000;   // a dispatched card not posted by then -> the text
export const GOAL_FALLBACK_MS = 4 * 60 * 1000;  // a goal card not posted by then -> the text (a goal cannot wait 12)

const COMP_AR = {
  552: "الدوري المصري", 624: "دوري أبطال أفريقيا", 627: "كأس الكونفدرالية الأفريقية", 588: "تصفيات كأس أمم أفريقيا",
  7: "الدوري الإنجليزي", 11: "الدوري الإسباني", 17: "الدوري الإيطالي", 25: "الدوري الألماني",
  35: "الدوري الفرنسي", 78: "الدوري التركي", 649: "الدوري السعودي",
  572: "دوري أبطال أوروبا", 573: "الدوري الأوروبي", 7016: "دوري الأمم الأوروبية",
};

// The curated clubs as 365scores spells them (the live feed is langId=27, so
// every name is Arabic - NOT the football-data names in matches.json).
// الأهلي is also a Saudi club and a Dubai club, so the Egyptian three count
// only in the Egyptian league (552) and the CAF Champions League (624);
// «مصر» only exactly (it is a substring of «المصري»); comps null = anywhere.
const EGY_LIVE_COMPS = [552, 624, 627];   // league, CAF CL, CAF Confederation Cup
export const CURATED_LIVE = [
  // exact (2026-10-17): «الأهلي طرابلس» plays the same Confederation Cup
  { t: "الأهلي", comps: EGY_LIVE_COMPS, exact: true },
  { t: "الزمالك", comps: EGY_LIVE_COMPS, exact: true },
  { t: "بيراميدز", comps: EGY_LIVE_COMPS, exact: true },
  { t: "مصر", comps: [588], exact: true },
  { t: "طرابزون سبور", comps: [78, 573] },
  { t: "ريال مدريد", comps: null },
  { t: "برشلونة", comps: null },
  { t: "مانشستر يونايتد", comps: null },
  { t: "مانشستر سيتي", comps: null },
  { t: "أرسنال", comps: null },
  { t: "ليفربول", comps: null },
  { t: "تشيلسي", comps: null },
];
// same normalisation match_brief._norm uses, so آرسنال matches أرسنال
export const arNorm = (x) => (x || "").replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي").trim();

export function curatedLive(g) {
  const c = Number(g.c || 0);
  return CURATED_LIVE.some(s => (!s.comps || s.comps.includes(c)) && (s.exact
    ? [arNorm(g.h), arNorm(g.a)].includes(arNorm(s.t))
    : (arNorm(g.h) + "|" + arNorm(g.a)).includes(arNorm(s.t))));
}
export const postScope = curatedLive;

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

// the scorers as one line per side. `goals` = [{s, p, m, t}] - the store's
// own goal log (live_goals, cancelled rows left out), read by goalsLogged();
// a game object's own list may be missing on an ended game, the log is not
export function scorerLines(g, goals) {
  const by = { h: [], a: [] };
  for (const ev of goals || g.goals || []) {
    if (!ev || !ev.p) continue;
    const t = ev.t === "ج" ? " (ج)" : ev.t === "عكسية" ? " (عكسي)" : "";
    (by[ev.s] || by.h).push(ev.m ? `${ev.p} ${ev.m}'${t}` : `${ev.p}${t}`);
  }
  const out = [];
  if (by.h.length) out.push(`${g.h}: ${by.h.join("، ")}`);
  if (by.a.length) out.push(`${g.a}: ${by.a.join("، ")}`);
  return out;
}

export function htMessage(g, goals) {
  return [`⏸️ نهاية الشوط الأول: ${scoreLine(g)}`, ...scorerLines(g, goals),
          `${COMP_AR[g.c] || ""} · المباراة لحظة بلحظة: ${SITE}/m/${g.id}`.replace(/^ · /, ""),
          `#يلا_سكور ${tag(g.h)} ${tag(g.a)}`].join("\n");
}

export function ftMessage(g, goals) {
  return [`🏁 انتهت المباراة: ${scoreLine(g)}`, ...scorerLines(g, goals),
          `${COMP_AR[g.c] || ""} · تفاصيل المباراة والهدافون: ${SITE}/m/${g.id}`.replace(/^ · /, ""),
          `#يلا_سكور ${tag(g.h)} ${tag(g.a)}`].join("\n");
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
const FB_ROW = "/*fb_row*/ SELECT post_id, claimed_at FROM fb_posted WHERE kind = ? AND ref_id = ?";
const FB_STALE = "/*fb_stale*/ SELECT ref_id, title FROM fb_posted WHERE kind = ? AND post_id IS NULL AND claimed_at < ? AND claimed_at > ?";
const FB_DROP = "/*fb_drop*/ DELETE FROM fb_posted WHERE kind = ? AND ref_id = ? AND post_id IS NULL";
const LG_LIST = "/*lg_list*/ SELECT side, player, minute, tag FROM live_goals WHERE game_id = ? AND cancelled = 0 ORDER BY seq";
const LG_CANCELLED = "/*lg_cancelled*/ SELECT seq FROM live_goals WHERE game_id = ? AND side = ? AND cancelled = 1 " +
  "AND (? = '' OR COALESCE(player,'') = ?) AND (? = '' OR COALESCE(minute,'') = ?) ORDER BY cancelled_at DESC, seq DESC LIMIT 1";

async function goalsLogged(env, gid) {
  try {
    const r = await env.DB.prepare(LG_LIST).bind(gid).all();
    return (r.results || []).map(x => ({ s: x.side, p: x.player || "", m: x.minute || "", t: x.tag || "" }));
  } catch (e) { return null; }
}
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
async function fbRow(env, kind, ref) {
  const r = await env.DB.prepare(FB_ROW).bind(kind, ref).first();
  return r ? { post_id: r.post_id ? String(r.post_id) : null, claimed_at: Number(r.claimed_at || 0) } : null;
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
// Goal cards (2026-10-17, user: «صورة زي دي مع الهدف»): the Worker cannot
// draw, so with a dispatcher it claims the goal (the title column keeps the
// WHOLE text) and starts fb-post.yml goal=<json>; fb_post.py --goal draws
// goal_card.py and posts within a minute or two. goalFallbacks() posts the
// text itself for any goal claim the runner has not finished within
// GOAL_FALLBACK_MS, so a goal is never lost to a slow or failed run.
export async function goalFallbacks(env, now) {
  const out = { posted: 0 };
  const since = Math.floor((now - 6 * 3600 * 1000) / 1000);      // never dig up old claims
  const until = Math.floor((now - GOAL_FALLBACK_MS) / 1000);
  let rows = [];
  try { rows = (await env.DB.prepare(FB_STALE).bind("goal", until, since).all()).results || []; }
  catch (e) { return out; }
  for (const row of rows) {
    if (!row.title || !row.title.includes("\n")) continue;      // a claim from the old text path: nothing to resend
    const gid = String(row.ref_id).split(":")[0];
    const pid = await publish(env, row.title, await cardUrl(env, gid));
    if (pid) { await record(env, "goal", String(row.ref_id), pid); out.posted += 1; }
  }
  return out;
}

// r = storeApply's result: posts [{g, seq, ev}], cancels [{g, ev}], hts, ends;
// `dispatch(inputs)` = worker.js's fb-post.yml dispatcher (null = no GH_TOKEN)
export async function livePosts(env, r, dispatch = null) {
  const out = { posted: 0, edited: 0, skipped: 0, dispatched: 0 };
  const posts = (r && r.posts || []).filter(x => postScope(x.g));
  const cancels = (r && r.cancels || []).filter(x => postScope(x.g));
  const hts = (r && r.hts || []).filter(x => postScope(x.g));
  const ends = (r && r.ends || []).filter(x => postScope(x.g));
  if (!posts.length && !cancels.length && !hts.length && !ends.length) return out;
  if (!env.FB_PAGE_TOKEN) { console.log("live posts: no FB_PAGE_TOKEN -", posts.length + hts.length + ends.length, "post(s) not posted"); return out; }
  for (const { g, seq, ev } of posts) {
    const ref = `${g.id}:${seq}`;
    const msg = goalMessage(g, ev);
    // the claim keeps the whole text: goalFallbacks() resends it if the card never comes
    if (!(await claim(env, "goal", ref, dispatch ? msg : msg.split("\n")[0]))) { out.skipped += 1; continue; }
    if (dispatch) {
      let ok = false;
      try {
        ok = await dispatch({ goal: JSON.stringify({ g: { id: g.id, c: g.c, h: g.h, a: g.a, hs: g.hs, as: g.as }, seq, ev }) });
      } catch (e) { ok = false; }
      if (ok) { out.dispatched += 1; continue; }  // the runner draws, posts and records
    }
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
  // half-time and full-time, after the goals so a 90' goal is announced before
  // the whistle; one post per game per kind (the lock), the card as the photo
  for (const [kind, list, text] of [["ht", hts, htMessage], ["ft", ends, ftMessage]]) {
    for (const { g } of list) {
      const ref = String(g.id);
      const msg = text(g, await goalsLogged(env, g.id));
      if (!(await claim(env, kind, ref, msg.split("\n")[0]))) { out.skipped += 1; continue; }
      const pid = await publish(env, msg, await cardUrl(env, g.id));
      if (pid) { await record(env, kind, ref, pid); out.posted += 1; }
      else await drop(env, kind, ref);
    }
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

// upcoming = [{id, c, h, a, start}] from the list (statusGroup 2), every minute.
// `dispatch(inputs)` = worker.js's fb-post.yml dispatcher (null when there is
// no GH_TOKEN): the card path. Returns true when the run was started.
export async function lineupPosts(env, upcoming, now, headers, dispatch = null) {
  const out = { due: 0, posted: 0, waiting: 0, dispatched: 0 };
  const due = (upcoming || []).filter(g => postScope(g) && g.start - now >= XI_MIN_MS && g.start - now <= XI_MAX_MS);
  out.due = due.length;
  if (!due.length) return out;
  if (!env.FB_PAGE_TOKEN) { console.log("xi posts: no FB_PAGE_TOKEN -", due.length, "match(es) not posted"); return out; }
  for (const g of due) {
    const ref = String(g.id);
    const row = await fbRow(env, "xi", ref);
    if (row && row.post_id) continue;                       // already out
    const xi = await gameLineups(g.id, headers);
    if (!xi) { out.waiting += 1; continue; }                // not announced yet: next minute
    const msg = xiMessage(g, xi);
    if (row && !row.post_id) {
      // claimed earlier (a dispatched card): give the runner XI_FALLBACK_MS,
      // then post the text ourselves - the page must not miss the line-up
      if (now - row.claimed_at * 1000 < XI_FALLBACK_MS) continue;
      const pid = await publish(env, msg, await cardUrl(env, g.id));
      if (pid) { await record(env, "xi", ref, pid); out.posted += 1; }
      continue;
    }
    if (!(await claim(env, "xi", ref, msg.split("\n")[0]))) continue;
    if (dispatch) {
      let ok = false;
      try { ok = await dispatch({ xi: ref }); } catch (e) { ok = false; }
      if (ok) { out.dispatched += 1; continue; }          // the runner draws + posts + records
    }
    const pid = await publish(env, msg, await cardUrl(env, g.id));
    if (pid) { await record(env, "xi", ref, pid); out.posted += 1; }
    else await drop(env, "xi", ref);
  }
  return out;
}
