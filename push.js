/* Web push subscriptions (2026-09-27) - the two routes the bell talks to.
 *
 *   POST /push/subscribe     body = PushSubscription.toJSON()
 *                            {endpoint, keys: {p256dh, auth}}
 *   POST /push/unsubscribe   body = {endpoint}
 *
 * The browser creates the subscription; this only keeps it in D1 (push_subs)
 * so push_send.py can encrypt a notification to it after a deploy. SENDING
 * does not happen here: a Worker on the free plan may make only a few dozen
 * outbound requests per invocation, one per subscriber - the GitHub runner has
 * no such limit (see push_send.py).
 *
 * The routes are public (every reader's browser calls them), so they refuse
 * anything that is not what a real browser sends:
 *   - same-origin only (the Origin header of a fetch from our own pages or
 *     from sw.js), POST only, a small JSON body;
 *   - the endpoint must be HTTPS on a KNOWN push service - otherwise this
 *     table would be an open list of URLs our runner POSTs to;
 *   - both keys must look like the base64url keys a browser generates.
 * Each accepted subscribe costs ONE row write (an upsert keyed on the
 * endpoint), so a reader who taps the bell twice does not grow the table.
 *
 * «تابع فريقك» (2026-11-19): the body may carry `team` - the slug of the ONE
 * club page the reader follows (snippets/follow_js.html). It is kept on the
 * row so push_team.py can send that club's goals, results and news to its
 * followers only. A body WITHOUT the key leaves the stored team alone (sw.js
 * re-subscribes without it when the push service rotates a subscription);
 * `team: ""` clears it.
 */

const ORIGIN = "https://elgoon.com";
const MAX_BODY = 4096;

// the push services the browsers actually use (Chrome/Edge-Android/Samsung =
// FCM, Firefox = Mozilla autopush, Edge desktop = WNS, Safari = Apple)
const PUSH_HOSTS = [
  /^fcm\.googleapis\.com$/,
  /^updates\.push\.services\.mozilla\.com$/,
  /^push\.services\.mozilla\.com$/,
  /^[a-z0-9-]+\.notify\.windows\.com$/,
  /^web\.push\.apple\.com$/,
  /^[a-z0-9-]+\.push\.apple\.com$/,
];

const SCHEMA = "CREATE TABLE IF NOT EXISTS push_subs (endpoint TEXT PRIMARY KEY, " +
  "p256dh TEXT NOT NULL, auth TEXT NOT NULL, created_at INTEGER NOT NULL)";
// the followed club, added 2026-11-19 to a table that already existed
const ADD_TEAM = "/*push_team_col*/ ALTER TABLE push_subs ADD COLUMN team TEXT";
// up to four followed clubs since 2026-11-26, joined by commas in the SAME
// column: a row that holds one club is a list of one
const TEAM = /^[a-z0-9-]{2,40}(,[a-z0-9-]{2,40}){0,3}$/;
let ready = false;
async function ensure(env) {
  if (ready) return;
  await env.DB.prepare(SCHEMA).run();
  // SQLite has no ADD COLUMN IF NOT EXISTS: "duplicate column name" means the
  // column is there, which is the state we want. Once per Worker instance.
  try { await env.DB.prepare(ADD_TEAM).run(); } catch (e) {
    if (!/duplicate column/i.test(String(e && e.message))) throw e;
  }
  ready = true;
}

/** [is the key present, the slug or null] */
export function pushTeam(body) {
  const has = Object.prototype.hasOwnProperty.call(body, "team");
  const t = has && typeof body.team === "string" && TEAM.test(body.team) ? body.team : null;
  return [has, t];
}

function reply(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

export function pushEndpointOk(u) {
  if (typeof u !== "string" || u.length > 1024) return false;
  let h;
  try { h = new URL(u); } catch (e) { return false; }
  if (h.protocol !== "https:" || h.username || h.password || h.port) return false;
  return PUSH_HOSTS.some(re => re.test(h.hostname.toLowerCase()));
}

// a P-256 public key uncompressed = 65 bytes = 87 base64url chars (88 padded);
// the auth secret = 16 bytes = 22 chars (24 padded)
const B64URL = /^[A-Za-z0-9_-]+=*$/;
export function pushKeysOk(k) {
  if (!k || typeof k !== "object") return false;
  const p = String(k.p256dh || ""), a = String(k.auth || "");
  return B64URL.test(p) && p.length >= 86 && p.length <= 88 &&
         B64URL.test(a) && a.length >= 21 && a.length <= 24;
}

async function readJson(request) {
  const text = await request.text();
  if (text.length > MAX_BODY) return null;
  try { return JSON.parse(text); } catch (e) { return null; }
}

export async function pushApi(request, env, url) {
  if (request.method !== "POST") return reply({ error: "POST only" }, 405);
  if ((request.headers.get("Origin") || "") !== ORIGIN) return reply({ error: "forbidden" }, 403);
  if (!env.DB) return reply({ error: "store unavailable" }, 503);
  const body = await readJson(request);
  if (!body || typeof body !== "object") return reply({ error: "bad json" }, 400);
  if (!pushEndpointOk(body.endpoint)) return reply({ error: "not a push service endpoint" }, 400);
  try {
    await ensure(env);
    if (url.pathname === "/push/subscribe") {
      if (!pushKeysOk(body.keys)) return reply({ error: "bad keys" }, 400);
      const [hasTeam, team] = pushTeam(body);
      await env.DB.prepare(
        "/*push_sub*/ INSERT INTO push_subs (endpoint, p256dh, auth, created_at, team) VALUES (?, ?, ?, ?, ?) " +
        "ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth, " +
        "team = CASE WHEN ? = 1 THEN excluded.team ELSE push_subs.team END"
      ).bind(body.endpoint, body.keys.p256dh, body.keys.auth, Math.floor(Date.now() / 1000), team, hasTeam ? 1 : 0).run();
      return reply({ ok: true });
    }
    if (url.pathname === "/push/unsubscribe") {
      await env.DB.prepare("/*push_unsub*/ DELETE FROM push_subs WHERE endpoint = ?")
        .bind(body.endpoint).run();
      return reply({ ok: true });
    }
  } catch (e) {
    // a D1 quota wall: say so, never a bare 500 page
    console.log("push store failed:", e && e.message);
    return reply({ error: "store unavailable" }, 503);
  }
  return reply({ error: "no such route" }, 404);
}
