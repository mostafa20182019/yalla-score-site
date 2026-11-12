// worker.js turns the static assets' TEMPORARY 307 (/a/1.html -> /a/1,
// /matches/ -> /matches) into a 301 to the same target (SEO review
// 2026-11-12), keeps the query string, and leaves every other answer alone.
import assert from "node:assert/strict";

const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
function envWith(res) {
  return { ASSETS: { fetch: async () => res } };
}
const r307 = () => new Response(null, { status: 307, headers: { location: "/a/1146" } });

let r = await worker.fetch(new Request("https://elgoon.com/a/1146.html"), envWith(r307()), {});
assert.equal(r.status, 301);
assert.equal(r.headers.get("location"), "/a/1146");

r = await worker.fetch(new Request("https://elgoon.com/a/1146.html?utm=fb"), envWith(r307()), {});
assert.equal(r.status, 301);
assert.equal(r.headers.get("location"), "/a/1146?utm=fb");

// an absolute or protocol-relative target is never rewritten
r = await worker.fetch(new Request("https://elgoon.com/x"),
  envWith(new Response(null, { status: 307, headers: { location: "//evil.example/x" } })), {});
assert.equal(r.status, 307);

// a page is served as it was
r = await worker.fetch(new Request("https://elgoon.com/a/1146"),
  envWith(new Response("<html>", { status: 200 })), {});
assert.equal(r.status, 200);
assert.equal(await r.text(), "<html>");

// a 404 still gets no-store
r = await worker.fetch(new Request("https://elgoon.com/nope"),
  envWith(new Response("nf", { status: 404 })), {});
assert.equal(r.status, 404);
assert.equal(r.headers.get("cache-control"), "no-store");

console.log("ok worker redirect: 307 -> 301 (query kept), 200 and 404 unchanged");
