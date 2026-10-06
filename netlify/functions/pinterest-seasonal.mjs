import { getStore } from "@netlify/blobs";
import { API, SITE, siteDate, accessToken } from "../lib/pinterest.mjs";

// Posts the printable-pack pins listed in /assets/pin-schedule.json, each on
// its own date. Separate from pinterest-daily so the two cannot disturb each
// other. Runs once a day (UTC); 01:15 UTC is early afternoon in Melbourne and
// the evening before in North America.
//
// A pin is posted at most once: it is recorded in the store when it goes up,
// and before posting the board is checked for a pin with the same title and
// link, so a lost record cannot cause a repeat. A pin that fails is tried
// again on the next two days, then left alone and reported as missed.
// Every run is written where pinterest-seasonal-status can show it.

const SCHEDULE = SITE + "/assets/pin-schedule.json";
const MAX_PER_RUN = 2;
const CATCH_UP_DAYS = 2;

function addDays(day, n) {
  const d = new Date(day + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

async function loadSchedule() {
  const r = await fetch(SCHEDULE, { headers: { "Cache-Control": "no-cache" } });
  if (!r.ok) throw new Error("schedule HTTP " + r.status);
  const j = await r.json();
  return Array.isArray(j.pins) ? j.pins : [];
}

function problem(p) {
  for (const k of ["id", "date", "board_id", "title", "description", "alt_text", "link", "image"]) {
    if (typeof p[k] !== "string" || !p[k]) return "missing " + k;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(p.date)) return "bad date";
  if (!p.link.startsWith(SITE + "/") || !p.image.startsWith(SITE + "/")) return "link or image is not on " + SITE;
  if (p.title.length > 100 || p.description.length > 800 || p.alt_text.length > 500) return "text too long";
  return null;
}

const bare = (u) => String(u || "").split("?")[0].replace(/\/+$/, "").toLowerCase();

async function alreadyOnBoard(token, p, cache) {
  if (!cache[p.board_id]) {
    const pins = [];
    let bookmark = null;
    for (let page = 0; page < 4; page++) {
      const url = `${API}/v5/boards/${p.board_id}/pins?page_size=100` +
        (bookmark ? "&bookmark=" + encodeURIComponent(bookmark) : "");
      const r = await fetch(url, { headers: { Authorization: "Bearer " + token } });
      if (!r.ok) throw new Error("board pin list HTTP " + r.status);
      const j = await r.json();
      for (const x of j.items || []) pins.push(x);
      bookmark = j.bookmark;
      if (!bookmark) break;
    }
    cache[p.board_id] = pins;
  }
  const hit = cache[p.board_id].find((x) => String(x.title || "").trim() === p.title && bare(x.link) === bare(p.link));
  return hit ? hit.id : null;
}

export default async () => {
  const store = getStore({ name: "pinterest", consistency: "strong" });
  const today = siteDate();
  const run = { at: new Date().toISOString(), date: today, posted: [], skipped: [], failed: [], waiting: 0 };
  try {
    const pins = await loadSchedule();
    const earliest = addDays(today, -CATCH_UP_DAYS);
    const due = pins.filter((p) => p && p.date <= today && p.date >= earliest)
      .sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id));
    const pending = [];
    for (const p of due) {
      if (!(await store.get("seasonal/" + p.id, { type: "json" }))) pending.push(p);
    }
    if (pending.length) {
      const token = await accessToken(store);
      const cache = {};
      for (const p of pending.slice(0, MAX_PER_RUN)) {
        try {
          const bad = problem(p);
          if (bad) throw new Error("schedule entry: " + bad);
          // If the board cannot be checked we do not post: a late pin can be
          // put right, a duplicate cannot be un-shown.
          const there = await alreadyOnBoard(token, p, cache);
          if (there) {
            await store.setJSON("seasonal/" + p.id, { pin_id: there, at: run.at, how: "already on the board" });
            run.skipped.push({ id: p.id, pin_id: there });
            continue;
          }
          const res = await fetch(`${API}/v5/pins`, {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({
              board_id: p.board_id, title: p.title, description: p.description, alt_text: p.alt_text,
              link: p.link, media_source: { source_type: "image_url", url: p.image },
            }),
          });
          let j = null;
          try { j = await res.json(); } catch (e) { /* reported below */ }
          if (!res.ok || !j || !j.id) {
            run.failed.push({ id: p.id, reason: "Pinterest rejected the pin: HTTP " + res.status, detail: JSON.stringify(j).slice(0, 300) });
            continue;
          }
          await store.setJSON("seasonal/" + p.id, { pin_id: j.id, at: run.at, how: "posted" });
          run.posted.push({ id: p.id, pin_id: j.id });
        } catch (e) {
          run.failed.push({ id: p.id, reason: String(e.message || e) });
        }
      }
      run.waiting = Math.max(0, pending.length - MAX_PER_RUN);
    }
  } catch (e) {
    run.error = String(e.message || e);
  }
  try { await store.setJSON("seasonal_last_run", run); } catch (e) { /* the record is a convenience */ }
  console.log("pinterest-seasonal:", JSON.stringify(run));
  return new Response(JSON.stringify(run), { headers: { "Content-Type": "application/json" } });
};

export const config = { schedule: "15 1 * * *" };
