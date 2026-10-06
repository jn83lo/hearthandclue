import { getStore } from "@netlify/blobs";
import { postToday, recordRun } from "../lib/pinterest.mjs";

// The "Post today's pin" button. Creates today's pin on the real board unless
// one is already there. Uses the signed-in visitor's own cookie token.

const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function readCookie(header, name) {
  if (!header) return null;
  for (const part of header.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return null;
}

export default async (req) => {
  if (req.method !== "POST") return json(405, { error: "POST only" });
  const token = readCookie(req.headers.get("cookie"), "pin_token");
  if (!token) return json(401, { error: "not connected - run the Pinterest connect step first" });

  const result = await postToday(token);
  await recordRun(getStore({ name: "pinterest", consistency: "strong" }), "button", result);
  return json(result.status === "failed" ? 502 : 200, result);
};
