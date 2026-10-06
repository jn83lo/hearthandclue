import { getStore } from "@netlify/blobs";
import { SITE, siteDate } from "../lib/pinterest.mjs";

// Read-only: where each scheduled printable pin stands, and what the last
// run did. Titles, dates and pin ids only - nothing private, no tokens.

const SCHEDULE = SITE + "/assets/pin-schedule.json";

export default async () => {
  const out = { site_date: siteDate(), pins: [], last_run: null };
  try {
    const store = getStore({ name: "pinterest", consistency: "strong" });
    const r = await fetch(SCHEDULE, { headers: { "Cache-Control": "no-cache" } });
    if (!r.ok) throw new Error("schedule HTTP " + r.status);
    const pins = (await r.json()).pins || [];
    const cut = new Date(out.site_date + "T00:00:00Z");
    cut.setUTCDate(cut.getUTCDate() - 2);
    const earliest = cut.toISOString().slice(0, 10);
    for (const p of pins) {
      const rec = await store.get("seasonal/" + p.id, { type: "json" });
      const state = rec ? (rec.how === "posted" ? "posted" : "on the board")
        : p.date > out.site_date ? "scheduled" : p.date >= earliest ? "due" : "missed";
      out.pins.push({ id: p.id, date: p.date, state, pin_id: rec ? rec.pin_id : null, title: p.title });
    }
    out.counts = out.pins.reduce((m, p) => { m[p.state] = (m[p.state] || 0) + 1; return m; }, {});
    out.last_run = await store.get("seasonal_last_run", { type: "json" });
  } catch (e) {
    out.error = String(e.message || e);
  }
  return new Response(JSON.stringify(out, null, 1), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
};
