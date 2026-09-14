import { getStore } from "@netlify/blobs";

// Counts anonymous events for The Daily Clue.
//
// One blob per event, keyed "<day>/<event>/<random>". Counting is then just
// counting keys. An earlier version kept a single per-day tally and did
// read-modify-write, which silently dropped roughly half of any rapid burst -
// blob reads are eventually consistent, so two events seconds apart clobbered
// each other. Never reintroduce that shape.
//
// No IP, no cookie, no identifier of any kind is stored.

const ALLOWED = ["visit", "puzzle_completed", "restarted", "hint_used", "result_shared"];

export default async (req) => {
  if (req.method !== "POST") return new Response("POST only", { status: 405 });

  let name = "";
  try {
    const body = await req.json();
    if (typeof body.name === "string") name = body.name;
  } catch (e) {
    return new Response(null, { status: 204 });
  }

  if (ALLOWED.indexOf(name) === -1) return new Response(null, { status: 204 });

  try {
    const day = new Date().toISOString().slice(0, 10);
    const id = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    await getStore("clue-events").set(`${day}/${name}/${id}`, "1");
  } catch (e) {
    // The browser sends this with sendBeacon and never reads the response, so a
    // non-2xx here cannot affect the page. Surfacing the reason is worth more
    // than swallowing it.
    return new Response(JSON.stringify({ error: String(e && e.message ? e.message : e) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(null, { status: 204 });
};
