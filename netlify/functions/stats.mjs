import { getStore } from "@netlify/blobs";

// Aggregates the per-event blobs written by event.mjs into per-day tallies.
// Keys look like "<day>/<event>/<random>", so counting keys is the whole job.
// Legacy keys (a bare "<day>" holding a JSON tally) are merged in for
// continuity with the first version of the collector.

export default async () => {
  const store = getStore("clue-events");
  const out = {};
  const legacy = [];

  const add = (day, name, n) => {
    out[day] = out[day] || {};
    out[day][name] = (out[day][name] || 0) + n;
  };

  try {
    for await (const page of store.list({ paginate: true })) {
      for (const b of page.blobs || []) {
        const parts = b.key.split("/");
        if (parts.length >= 2) add(parts[0], parts[1], 1);
        else legacy.push(b.key);
      }
    }

    for (const key of legacy) {
      const tally = (await store.get(key, { type: "json" })) || {};
      for (const name of Object.keys(tally)) add(key, name, tally[name]);
    }
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e && e.message ? e.message : e) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  const trimmed = {};
  Object.keys(out).sort().slice(-30).forEach((d) => { trimmed[d] = out[d]; });

  return new Response(JSON.stringify(trimmed), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
};
