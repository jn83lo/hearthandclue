import { getStore } from "@netlify/blobs";
import { accessToken, postToday, recordRun } from "../lib/pinterest.mjs";

// Posts the day's pin with nobody present. Runs on a schedule (UTC).
// It checks the board first and does nothing if today's pin is already there,
// so it is safe alongside any other poster. The outcome of every run - posted,
// skipped or failed, with the reason - is written where
// /.netlify/functions/pinterest-status can show it. A run that fails says so.

export default async () => {
  const store = getStore({ name: "pinterest", consistency: "strong" });
  let result;
  try {
    const token = await accessToken(store);
    result = await postToday(token);
  } catch (e) {
    result = { status: "failed", reason: String(e.message || e) };
  }
  const entry = await recordRun(store, "schedule", result);
  console.log("pinterest-daily:", JSON.stringify(entry));
  return new Response(JSON.stringify(entry), { headers: { "Content-Type": "application/json" } });
};

// 00:30 UTC = 11:30am Melbourne in summer, 10:30am in winter: after the
// existing 9-10am poster, so for now this only fills a day that one missed.
export const config = { schedule: "30 0 * * *" };
