import { getStore } from "@netlify/blobs";
import { exchangeCode, tokenRecord, ownsBoard } from "../lib/pinterest.mjs";

// Exchanges a Pinterest authorisation code for tokens (PRODUCTION API).
// The app secret lives in a Netlify environment variable and never reaches the
// browser. The access token goes back only as an httpOnly cookie, and - if the
// account is the Hearth & Clue one - the tokens are also saved server-side so
// the daily job can post without anyone signing in again.

const json = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

export default async (req) => {
  if (req.method !== "POST") return json(405, { error: "POST only" });

  let code;
  try {
    code = (await req.json()).code;
  } catch (e) {
    return json(400, { error: "bad JSON body" });
  }
  if (!code) return json(400, { error: "no code supplied" });

  let tok;
  try {
    tok = await exchangeCode(code);
  } catch (e) {
    return json(e.status && e.status >= 400 ? e.status : 502, {
      error: "token exchange failed", reason: String(e.message || e), detail: e.detail || null,
    });
  }

  let automation = false;
  let automationNote = "this Pinterest account cannot see the Daily Clue board, so it was not saved for daily posting";
  if (await ownsBoard(tok.access_token)) {
    try {
      await getStore({ name: "pinterest", consistency: "strong" }).setJSON("tokens", tokenRecord(tok));
      automation = true;
      automationNote = "saved - the daily pin will now post on its own";
    } catch (e) {
      automationNote = "sign-in worked but could not be saved: " + String(e.message || e);
    }
  }

  const cookie = [
    `pin_token=${encodeURIComponent(tok.access_token)}`,
    "Path=/", "HttpOnly", "Secure", "SameSite=Lax", `Max-Age=${60 * 60 * 24}`,
  ].join("; ");

  return json(200, { connected: true, automation, automation_note: automationNote }, { "Set-Cookie": cookie });
};
