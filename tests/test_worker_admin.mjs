/* The /admin/api routes in worker.js, driven with a fake D1 binding.
 *
 * What this proves: routing, that the API FAILS CLOSED (no token / no secret /
 * wrong token), input validation, the shape of the SQL it sends (the id must
 * be allocated inside the INSERT), the CORS headers, the duplicate-match
 * answer, and that a successful write asks GitHub to rebuild.
 *
 * What it does NOT prove: that the SQL runs. It is the same SQL article_put.py
 * sends, and test_article_write.py runs that against real sqlite - so the two
 * suites together cover both halves.
 *
 *   node tests/test_worker_admin.mjs
 */
import worker from "../worker.js";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

/* ---------------------------------------------------------------- fake D1 */
function fakeDB(rows = [], opts = {}) {
  const sqlSeen = [];
  const mk = (sql) => ({
    sql,
    _binds: [],
    bind(...a) { this._binds = a; return this; },
    async first() {
      sqlSeen.push([sql, this._binds]);
      if (opts.throwOn && sql.includes(opts.throwOn)) throw new Error(opts.throwWith);
      if (/RETURNING article_id/.test(sql)) return { article_id: 459 };
      if (/SELECT article_id FROM articles WHERE/.test(sql)) {
        return rows.find(r => String(r.article_id) === String(this._binds[0])) || null;
      }
      if (/FROM articles WHERE article_id/.test(sql)) {
        return rows.find(r => String(r.article_id) === String(this._binds[0])) || null;
      }
      return null;
    },
    async all() { sqlSeen.push([sql, this._binds]); return { results: rows }; },
    async run() {
      sqlSeen.push([sql, this._binds]);
      if (opts.throwOn && sql.includes(opts.throwOn)) throw new Error(opts.throwWith);
      return { success: true };
    },
  });
  return {
    sqlSeen,
    prepare: (sql) => mk(sql),
    batch: async (stmts) => {
      for (const s of stmts) sqlSeen.push([s.sql, s._binds]);
      return stmts.map(() => ({ results: [] }));
    },
  };
}

/* fetch is only used for the GitHub dispatch */
let dispatches = [];
globalThis.fetch = async (url, init) => {
  dispatches.push({ url: String(url), body: init && init.body });
  return { ok: true, status: 204 };
};

const TOKEN = "s3cret";
const req = (path, { method = "GET", token = TOKEN, body, origin } = {}) => {
  const h = { "Origin": origin || "http://localhost:8123" };
  if (token !== null) h["x-admin-token"] = token;
  if (body) h["content-type"] = "application/json";
  return new Request("https://yallascore.site" + path,
    { method, headers: h, body: body ? JSON.stringify(body) : undefined });
};
const ART = {
  title: "عنوان", summary: "ملخص", body: "<p>" + "كلمة ".repeat(400) + "</p>",
  author: "فريق التحرير", pub_date: "2026-09-10",
  sources: [{ name: "مصدر", url: "https://x", note: "ملاحظة" }],
  faq: [{ q: "س", a: "ج" }],
};

/* ------------------------------------------------------------ fails closed */
let r = await worker.fetch(req("/admin/api/articles"), { ASSETS: null, DB: fakeDB() }, {});
ck("1 no ADMIN_TOKEN on the Worker = closed, not open", r.status === 503,
   String(r.status));

r = await worker.fetch(req("/admin/api/articles"),
  { ADMIN_TOKEN: TOKEN, DB: null }, {});
ck("2 a missing D1 binding says so", r.status === 503, String(r.status));

r = await worker.fetch(req("/admin/api/articles", { token: null }),
  { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("3 no token on the request = 401", r.status === 401, String(r.status));

r = await worker.fetch(req("/admin/api/articles", { token: "wrong" }),
  { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("4 a wrong token = 401", r.status === 401, String(r.status));

/* ------------------------------------------------------------------ read */
const listRows = [
  { article_id: "458", title: "أحدث", pub_date: "2026-09-10", words: 620, thin: 0 },
  { article_id: "457", title: "أقدم", pub_date: "2026-09-09", words: 210, thin: 1 },
];
let db = fakeDB(listRows);
r = await worker.fetch(req("/admin/api/articles"), { ADMIN_TOKEN: TOKEN, DB: db }, {});
let j = await r.json();
ck("5 the list comes back from D1", r.status === 200 && j.items.length === 2,
   `${r.status} / ${j.items && j.items.length}`);
ck("6 the list is ordered newest id first, and carries no bodies",
   /ORDER BY CAST\(article_id AS INTEGER\) DESC/.test(db.sqlSeen[0][0])
   && !/\bbody\b/.test(db.sqlSeen[0][0]), db.sqlSeen[0][0].slice(0, 60));
ck("7 the reply is not cacheable and allows the admin origin",
   r.headers.get("cache-control") === "no-store"
   && r.headers.get("access-control-allow-origin") === "http://localhost:8123");

db = fakeDB([{ article_id: "458", title: "أحدث", body: "<p>x</p>" }]);
r = await worker.fetch(req("/admin/api/article/458"), { ADMIN_TOKEN: TOKEN, DB: db }, {});
j = await r.json();
ck("8 one article comes back with its children",
   r.status === 200 && j.title === "أحدث" && Array.isArray(j.sources) && Array.isArray(j.faq),
   String(r.status));
r = await worker.fetch(req("/admin/api/article/999"), { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("9 an unknown id is a 404", r.status === 404, String(r.status));

/* ----------------------------------------------------------------- write */
dispatches = [];
db = fakeDB();
r = await worker.fetch(req("/admin/api/article", { method: "POST", body: ART }),
  { ADMIN_TOKEN: TOKEN, DB: db, GH_TOKEN: "gh" }, {});
j = await r.json();
ck("10 a new article is inserted and gets its id back",
   r.status === 201 && j.article_id === "459", `${r.status} ${j.article_id || j.error}`);
const ins = db.sqlSeen.find(([s]) => /INSERT INTO articles/.test(s));
ck("11 the id is allocated INSIDE the insert (the race fix)",
   /SELECT CAST\(COALESCE\(MAX\(CAST\(article_id AS INTEGER\)\), 0\) \+ 1 AS TEXT\)/.test(ins[0]),
   ins[0].slice(0, 70));
ck("12 word count and the thin flag are computed server-side",
   j.words === 400 && j.thin === false, `${j.words} words, thin=${j.thin}`);
ck("13 the children are written too",
   db.sqlSeen.some(([s]) => /INSERT INTO article_sources/.test(s))
   && db.sqlSeen.some(([s]) => /INSERT INTO article_faq/.test(s)));
ck("14 saving asks GitHub to rebuild the site",
   dispatches.length === 1 && /publish\.yml\/dispatches/.test(dispatches[0].url)
   && /"reason":"article"/.test(dispatches[0].body),
   dispatches[0] ? dispatches[0].url.slice(-40) : "none");

for (const f of ["title", "summary", "body", "author", "pub_date"]) {
  const bad = { ...ART }; delete bad[f];
  r = await worker.fetch(req("/admin/api/article", { method: "POST", body: bad }),
    { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
  ck(`15 a draft with no ${f} is refused`, r.status === 400, String(r.status));
}
r = await worker.fetch(req("/admin/api/article",
  { method: "POST", body: { ...ART, match_id: "1" } }),
  { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("16 match_id without kind is refused", r.status === 400, String(r.status));

db = fakeDB([], { throwOn: "INSERT INTO articles", throwWith: "UNIQUE constraint failed" });
r = await worker.fetch(req("/admin/api/article", { method: "POST", body: { ...ART, match_id: "1", kind: "preview" } }),
  { ADMIN_TOKEN: TOKEN, DB: db }, {});
j = await r.json();
ck("17 a duplicate match piece answers 409, not 500",
   r.status === 409 && /already has a piece/.test(j.error), `${r.status} ${j.error}`);

/* ---------------------------------------------------------------- update */
dispatches = [];
db = fakeDB([{ article_id: "458", title: "قديم" }]);
r = await worker.fetch(req("/admin/api/article/458",
  { method: "PUT", body: { title: "جديد", body: "<p>" + "كلمة ".repeat(500) + "</p>" } }),
  { ADMIN_TOKEN: TOKEN, DB: db, GH_TOKEN: "gh" }, {});
j = await r.json();
const upd = db.sqlSeen.find(([s]) => /UPDATE articles SET/.test(s));
ck("18 an edit updates only the fields it sent",
   r.status === 200 && /title = \?/.test(upd[0]) && !/summary = \?/.test(upd[0]),
   upd ? upd[0].slice(0, 60) : "no update");
ck("19 an edit recomputes the word count", j.words === 500, String(j.words));
ck("20 an edit leaves the children alone when it did not send them",
   !db.sqlSeen.some(([s]) => /DELETE FROM article_sources/.test(s)));
ck("21 an edit also asks for a rebuild", dispatches.length === 1);

r = await worker.fetch(req("/admin/api/article/999", { method: "PUT", body: { title: "x" } }),
  { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("22 editing an unknown id is a 404", r.status === 404, String(r.status));

/* --------------------------------------------------------------- plumbing */
r = await worker.fetch(req("/admin/api/articles", { method: "OPTIONS" }),
  { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("23 the CORS preflight is answered without a token",
   r.status === 204 && r.headers.get("access-control-allow-headers").includes("x-admin-token"),
   String(r.status));

r = await worker.fetch(req("/admin/api/nonsense"), { ADMIN_TOKEN: TOKEN, DB: fakeDB() }, {});
ck("24 an unknown route is a 404", r.status === 404, String(r.status));

/* the public site must not be affected: a normal path still hits ASSETS */
let served = false;
r = await worker.fetch(new Request("https://yallascore.site/a/458"),
  { ADMIN_TOKEN: TOKEN, DB: fakeDB(),
    ASSETS: { fetch: async () => { served = true; return new Response("page"); } } }, {});
ck("25 a normal page still comes from the static assets, not from D1", served);

/* and D1 being down cannot take the public site with it */
served = false;
r = await worker.fetch(new Request("https://yallascore.site/"),
  { ADMIN_TOKEN: TOKEN, DB: null,
    ASSETS: { fetch: async () => { served = true; return new Response("home"); } } }, {});
ck("26 the site still serves with no D1 binding at all", served && r.status === 200);

/* ------------------------------------------------------------ embeds (2026-09-13) */
{
  const db = fakeDB();
  r = await worker.fetch(req("/admin/api/article", { method: "POST", body: { ...ART, embeds: ["https://example.com/not-a-post"] } }),
    { ADMIN_TOKEN: TOKEN, DB: db }, {});
  ck("27 a POST with a non-platform embed URL is refused with 400", r.status === 400, String(r.status));
  const db2 = fakeDB();
  r = await worker.fetch(req("/admin/api/article", { method: "POST", body: { ...ART, embeds: ["https://x.com/AlAhly/status/1", "https://www.instagram.com/p/abc/"] } }),
    { ADMIN_TOKEN: TOKEN, DB: db2 }, {});
  const embSql = db2.sqlSeen.filter(([q]) => /article_embeds/.test(q));
  ck("28 a POST with official-post URLs creates the table lazily and writes one row per embed with its platform",
     // (the lazy CREATE ran once per Worker isolate - an earlier GET in this file already did it)
     r.status === 201 && embSql.filter(([q]) => /INSERT INTO article_embeds/.test(q)).length === 2
     && embSql.some(([q, b]) => /INSERT INTO article_embeds/.test(q) && b[3] === "instagram"),
     String(r.status));
  const db3 = fakeDB([{ article_id: "459", title: "t" }]);
  r = await worker.fetch(req("/admin/api/article/459", { method: "PUT", body: { title: "t2" } }),
    { ADMIN_TOKEN: TOKEN, DB: db3 }, {});
  ck("29 a PUT without the embeds key leaves article_embeds alone",
     r.status === 200 && !db3.sqlSeen.some(([q]) => /DELETE FROM article_embeds/.test(q)), String(r.status));
}

console.log("\n" + (fails.length ? `${fails.length} FAILED: ${fails}`
                                 : "ALL WORKER ADMIN TESTS PASSED"));
process.exit(fails.length ? 1 : 0);
