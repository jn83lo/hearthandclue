import { getStore } from "@netlify/blobs";

// Counts anonymous events for The Daily Clue. No IP, no cookie, no identifier of
// any kind is stored - only a per-day tally per event name.

const ALLOWED = ["visit", "puzzle_completed", "restarted", "hint_used", "result_shared"];

export default async (req) => {
  if (req.method !== "POST") return new Response("POST only", { status: 405 });

  let body = {};
  try {
    body = await req.json();
  } catch (e) {
    return new Response(null, { status: 204 });
  }

  const name = typeof body.name === "string" ? body.name : "";
  if (ALLOWED.indexOf(name) === -1) return new Response(null, { status: 204 });

  const day = new Date().toISOString().slice(0, 10);
  const store = getStore("clue-events");

  try {
    const counts = (await store.get(day, { type: "json" })) || {};
    counts[name] = (counts[name] || 0) + 1;
    await store.setJSON(day, counts);
  } catch (e) {
    // Never let analytics break the page.
  }

  return new Response(null, { status: 204 });
};
