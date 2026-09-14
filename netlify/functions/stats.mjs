import { getStore } from "@netlify/blobs";

// Returns the last 30 days of event tallies as JSON, newest key last.

export default async () => {
  const store = getStore("clue-events");
  const out = {};

  try {
    const listed = await store.list();
    const keys = (listed.blobs || []).map((b) => b.key).sort().slice(-30);
    for (const k of keys) {
      out[k] = (await store.get(k, { type: "json" })) || {};
    }
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e && e.message ? e.message : e) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify(out), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
};
