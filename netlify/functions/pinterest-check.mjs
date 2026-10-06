import { getStore } from "@netlify/blobs";
import { API, boardId, siteDate, loadEntry, findTodaysPin } from "../lib/pinterest.mjs";

// Read-only dry run of the daily poster. Uses the saved sign-in to look at the
// real board and reports what the daily job WOULD do right now. It never
// creates, edits or deletes anything, and never renews or returns a token.
// It also lists the last three weeks of pins, so a missed day is visible.
// Throttled to one live look per minute; repeat calls get the saved answer.

const THROTTLE_MS = 60 * 1000;
const RECENT_DAYS = 21;
const MAX_PAGES = 4;

const json = (body, status = 200) =>
  new Response(JSON.stringify(body, null, 1), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

function toDate(createdAt) {
  let s = String(createdAt || "");
  if (!/(Z|[+-]\d\d:?\d\d)$/.test(s)) s += "Z"; // Pinterest times are UTC
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

async function listBoard(token, board) {
  const pins = [];
  let bookmark = null;
  let pages = 0;
  let more = false;
  for (let page = 0; page < MAX_PAGES; page++) {
    const url = `${API}/v5/boards/${board}/pins?page_size=100` +
      (bookmark ? "&bookmark=" + encodeURIComponent(bookmark) : "");
    const r = await fetch(url, { headers: { Authorization: "Bearer " + token } });
    if (!r.ok) throw new Error("board pin list HTTP " + r.status);
    const j = await r.json();
    pages = page + 1;
    for (const p of j.items || []) pins.push(p);
    bookmark = j.bookmark;
    more = !!bookmark;
    if (!bookmark) break;
  }
  return { pins, pages, more };
}

export default async (req) => {
  if (req.method !== "GET") return json({ error: "GET only" }, 405);

  const store = getStore({ name: "pinterest", consistency: "strong" });
  const now = Date.now();
  try {
    const saved = await store.get("last_check", { type: "json" });
    if (saved && now - saved.at_ms < THROTTLE_MS) return json({ ...saved, cached: true });
  } catch (e) { /* no saved answer - do a live look */ }

  const out = {
    at: new Date(now).toISOString(),
    at_ms: now,
    date: siteDate(new Date(now)),
    board_readable: false,
  };
  try {
    const rec = await store.get("tokens", { type: "json" });
    if (!rec || !rec.access_token) throw new Error("not connected - sign in at /pinterest-connect.html");
    if (rec.access_expires_at <= now) {
      throw new Error("the saved access token has expired; the daily job renews it, this check does not");
    }
    const found = await loadEntry(out.date);
    if (!found) throw new Error("no manifest entry dated " + out.date);
    out.issue = found.issue;
    out.title = found.entry.title;

    const board = boardId();
    // The real guard, exactly as the daily job runs it.
    const pinId = await findTodaysPin(rec.access_token, board, out.date, found.entry);
    out.board_readable = true;
    out.todays_pin_on_board = pinId;
    out.daily_job_would = pinId ? "skip (already posted)" : "post";

    // Evidence: what is actually on the board.
    const { pins, pages, more } = await listBoard(rec.access_token, board);
    out.pins_scanned = pins.length;
    out.pages_scanned = pages;
    out.more_pins_beyond_scan = more;
    out.first_listed = pins.length ? pins[0].created_at : null;
    out.last_listed = pins.length ? pins[pins.length - 1].created_at : null;
    const cutoff = now - RECENT_DAYS * 86400000;
    out.recent = pins
      .map((p) => ({ p, d: toDate(p.created_at) }))
      .filter((x) => x.d && x.d.getTime() >= cutoff)
      .sort((a, b) => b.d - a.d)
      .map(({ p, d }) => ({
        id: p.id,
        created_at: p.created_at,
        site_date: siteDate(d),
        title: p.title || null,
        link: p.link || null,
      }));
  } catch (e) {
    out.error = String(e.message || e);
  }
  try { await store.setJSON("last_check", out); } catch (e) { /* not worth failing for */ }
  return json(out);
};
