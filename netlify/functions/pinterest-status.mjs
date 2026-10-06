import { getStore } from "@netlify/blobs";
import { publicStatus } from "../lib/pinterest.mjs";

// Read-only health check for the Pinterest poster. Dates and outcomes only -
// no token or secret is ever returned.

export default async () => {
  let body;
  try {
    body = await publicStatus(getStore({ name: "pinterest", consistency: "strong" }));
  } catch (e) {
    body = { error: String(e.message || e) };
  }
  return new Response(JSON.stringify(body, null, 1), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
};
