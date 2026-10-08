import { getStore } from "@netlify/blobs";
import { API, SITE, accessToken } from "../lib/pinterest.mjs";

// One-off tidy of the Pinterest boards (October 2026), using the site's own
// sign-in. It does exactly what /assets/pin-moves.json lists - move a pin to a
// board, point it at a link - and nothing else, so calling it again, or by
// anyone, only re-applies that same list. Pins already right are left alone.
//
//   GET  /.netlify/functions/pinterest-tidy           shows what it would change
//   GET  /.netlify/functions/pinterest-tidy?apply=1   makes the changes

const MAX_MOVES = 40;
const AT_ONCE = 5;

const json = (body, status = 200) =>
  new Response(JSON.stringify(body, null, 1), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

export async function tidy(token, moves, { apply = false, fetchImpl = fetch } = {}) {
  const auth = { Authorization: "Bearer " + token };
  const one = async (m) => {
    if (!/^\d+$/.test(String(m.pin_id))) return { pin_id: m.pin_id, status: "skipped", reason: "bad pin id" };
    const r = await fetchImpl(`${API}/v5/pins/${m.pin_id}`, { headers: auth });
    if (!r.ok) return { pin_id: m.pin_id, status: "not found", http: r.status };
    const p = await r.json();
    const change = {};
    if (m.board_id && String(p.board_id) !== String(m.board_id)) change.board_id = String(m.board_id);
    if (m.link && p.link !== m.link) change.link = m.link;
    const was = { board_id: p.board_id, link: p.link, title: p.title };
    if (!Object.keys(change).length) return { pin_id: m.pin_id, status: "already right", was };
    if (!apply) return { pin_id: m.pin_id, status: "would change", change, was };
    const u = await fetchImpl(`${API}/v5/pins/${m.pin_id}`, {
      method: "PATCH",
      headers: { ...auth, "Content-Type": "application/json" },
      body: JSON.stringify(change),
    });
    let detail = null;
    try { detail = await u.json(); } catch (e) {}
    if (!u.ok) return { pin_id: m.pin_id, status: "failed", http: u.status, change, detail: JSON.stringify(detail).slice(0, 300) };
    return { pin_id: m.pin_id, status: "changed", change, now: { board_id: detail && detail.board_id, link: detail && detail.link } };
  };
  const results = [];
  for (let i = 0; i < moves.length; i += AT_ONCE) {
    results.push(...(await Promise.all(moves.slice(i, i + AT_ONCE).map((m) =>
      one(m).catch((e) => ({ pin_id: m.pin_id, status: "failed", reason: String(e.message || e) }))))));
  }
  return results;
}

export default async (req) => {
  if (req.method !== "GET") return json({ error: "GET only" }, 405);
  const apply = new URL(req.url).searchParams.get("apply") === "1";
  const out = { at: new Date().toISOString(), apply };
  try {
    const r = await fetch(SITE + "/assets/pin-moves.json", { headers: { "Cache-Control": "no-cache" } });
    if (!r.ok) throw new Error("pin-moves.json HTTP " + r.status);
    const moves = ((await r.json()).moves || []).slice(0, MAX_MOVES);
    const token = await accessToken(getStore({ name: "pinterest", consistency: "strong" }));
    out.results = await tidy(token, moves, { apply });
    out.counts = out.results.reduce((c, x) => ((c[x.status] = (c[x.status] || 0) + 1), c), {});
  } catch (e) {
    out.error = String(e.message || e);
  }
  return json(out);
};
