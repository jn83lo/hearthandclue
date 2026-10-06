// Shared Pinterest logic for The Daily Clue (PRODUCTION API - Standard access).
//
// Used by three functions:
//   pinterest-auth   - sign-in; saves the tokens so the daily job can run unattended
//   pinterest-pin    - the "Post today's pin" button on pinterest-connect.html
//   pinterest-daily  - scheduled; posts the day's pin with no one present
//
// Every function takes its fetch and its store as arguments so the whole thing
// can be tested with fakes. Nothing here ever returns a token to a caller.

export const API = "https://api.pinterest.com";
export const SITE = "https://hearthandclue.com";
export const MANIFEST = SITE + "/pins/manifest.json";
export const REDIRECT_URI = SITE + "/pinterest-connect.html";
export const DEFAULT_BOARD = "300615412567048694"; // "Word Search Puzzle Books"
export const SITE_TZ = "Australia/Sydney";

const TITLE_MAX = 100, DESC_MAX = 800, ALT_MAX = 500;
const REFRESH_WHEN_LEFT_MS = 5 * 24 * 3600 * 1000; // renew 5 days before expiry

export function boardId() {
  return (process.env.PINTEREST_BOARD || DEFAULT_BOARD).trim();
}

// The date the SITE is on. The puzzle rolls over at local midnight.
export function siteDate(d = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: SITE_TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(d);
}

// Pinterest has mangled fancy punctuation in pin text before, so keep it plain.
function plain(text) {
  return String(text)
    .replace(/[\u2018\u2019\u2032]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/\s*[\u2013\u2014]\s*/g, " - ")
    .replace(/\u2026/g, "...")
    .replace(/\u00A0/g, " ")
    .normalize("NFKD")
    .replace(/[^\x20-\x7E]/g, "");
}

function clip(text, limit) {
  text = plain(text).split(/\s+/).filter(Boolean).join(" ");
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const i = cut.lastIndexOf(" ");
  return (i > 0 ? cut.slice(0, i) : cut).replace(/[ ,.;:-]+$/, "");
}

function titleCase(w) {
  return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
}

// ---- manifest ------------------------------------------------------------

// Only ever returns the entry dated exactly `today`. No "nearest" fallback:
// posting the wrong day's puzzle is worse than posting nothing.
export async function loadEntry(today, fetchImpl = fetch) {
  const r = await fetchImpl(MANIFEST, { headers: { "Cache-Control": "no-cache" } });
  if (!r.ok) throw new Error("manifest HTTP " + r.status);
  const m = await r.json();
  for (const [issue, entry] of Object.entries(m)) {
    if (entry && entry.date === today) return { issue: parseInt(issue, 10), entry };
  }
  return null;
}

// Same wording as the old scripts/post_pin.py: no hashtags, alt text included.
export function buildPayload(issue, entry, board) {
  const note = String(entry.note || "").replace(/[. ]+$/, "");
  const words = Array.isArray(entry.words) && entry.words.length
    ? entry.words.map(titleCase).join(", ")
    : "eight themed words";
  return {
    board_id: board,
    title: clip(`${entry.title} - a free word search puzzle`, TITLE_MAX),
    description: clip(
      `${entry.title}. ${note}. Eight words hidden in the grid. ` +
      "A free word search puzzle, new every morning, same puzzle for everyone. " +
      "No app, no signup, no ads. Play today's at hearthandclue.com. " +
      `Today's is No. ${issue}.`, DESC_MAX),
    alt_text: clip(
      `A ten by ten word search grid titled ${entry.title}, issue number ${issue} of The Daily Clue, ` +
      `with eight hidden words listed underneath: ${words}.`, ALT_MAX),
    link: SITE + "/",
    media_source: { source_type: "image_url", url: `${SITE}/pins/${issue}.png` },
  };
}

// ---- duplicate guard -------------------------------------------------------

function pinSiteDate(createdAt) {
  if (!createdAt) return null;
  let s = String(createdAt);
  if (!/(Z|[+-]\d\d:?\d\d)$/.test(s)) s += "Z"; // Pinterest times are UTC
  const d = new Date(s);
  return isNaN(d) ? null : siteDate(d);
}

// Looks at what is ACTUALLY on the board, so it also sees pins made by another
// route (the Zapier poster, or a manual post from the phone). A pin counts as
// today's if it was created on today's site date and either links to the site
// or carries today's puzzle title.
export async function findTodaysPin(token, board, today, entry, fetchImpl = fetch) {
  const want = String(entry.title || "").toLowerCase();
  let bookmark = null;
  for (let page = 0; page < 4; page++) {
    const url = `${API}/v5/boards/${board}/pins?page_size=100` +
      (bookmark ? "&bookmark=" + encodeURIComponent(bookmark) : "");
    const r = await fetchImpl(url, { headers: { Authorization: "Bearer " + token } });
    if (!r.ok) {
      let detail = "";
      try { detail = JSON.stringify(await r.json()).slice(0, 300); } catch (e) {}
      throw new Error(`board pin list HTTP ${r.status} ${detail}`);
    }
    const j = await r.json();
    for (const p of j.items || []) {
      if (pinSiteDate(p.created_at) !== today) continue;
      const text = [p.title, p.description, p.alt_text].filter(Boolean).join(" ").toLowerCase();
      const link = String(p.link || "").toLowerCase();
      if (link.includes("hearthandclue.com") || (want && text.includes(want))) return p.id;
    }
    bookmark = j.bookmark;
    if (!bookmark) break;
  }
  return null;
}

// ---- posting ---------------------------------------------------------------

// Returns one of:
//   { status: "posted", issue, title, pin_id }
//   { status: "skipped", reason, ... }       nothing was created, by design
//   { status: "failed", reason, ... }        nothing was created, something broke
// If the duplicate check itself fails we do NOT post: a missed day is
// recoverable, a double post is not.
export async function postToday(token, { fetchImpl = fetch, now = new Date() } = {}) {
  const today = siteDate(now);
  const board = boardId();
  let found;
  try {
    found = await loadEntry(today, fetchImpl);
  } catch (e) {
    return { status: "failed", date: today, reason: String(e.message || e) };
  }
  if (!found) return { status: "failed", date: today, reason: "no manifest entry dated " + today };
  const { issue, entry } = found;
  const base = { date: today, issue, title: entry.title };

  let existing;
  try {
    existing = await findTodaysPin(token, board, today, entry, fetchImpl);
  } catch (e) {
    return { ...base, status: "failed", reason: "could not check the board for an existing pin: " + String(e.message || e) };
  }
  if (existing) return { ...base, status: "skipped", reason: "today's pin is already on the board", pin_id: existing };

  const payload = buildPayload(issue, entry, board);
  let r, j;
  try {
    r = await fetchImpl(`${API}/v5/pins`, {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    j = await r.json();
  } catch (e) {
    return { ...base, status: "failed", reason: "pin create: " + String(e.message || e) };
  }
  if (!r.ok || !j || !j.id) {
    return { ...base, status: "failed", reason: `Pinterest rejected the pin: HTTP ${r.status}`, detail: j };
  }
  return { ...base, status: "posted", pin_id: j.id };
}

// ---- tokens ----------------------------------------------------------------

function basicAuth() {
  const id = process.env.PINTEREST_APP_ID, secret = process.env.PINTEREST_APP_SECRET;
  if (!id || !secret) throw new Error("PINTEREST_APP_ID or PINTEREST_APP_SECRET is not set in Netlify");
  return "Basic " + Buffer.from(`${id}:${secret}`).toString("base64");
}

async function tokenCall(params, fetchImpl) {
  const r = await fetchImpl(`${API}/v5/oauth/token`, {
    method: "POST",
    headers: { Authorization: basicAuth(), "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(params).toString(),
  });
  let j = null;
  try { j = await r.json(); } catch (e) {}
  if (!r.ok || !j || !j.access_token) {
    const err = new Error(`token endpoint HTTP ${r.status}`);
    err.status = r.status;
    err.detail = j;
    throw err;
  }
  return j;
}

export function exchangeCode(code, fetchImpl = fetch) {
  return tokenCall({ grant_type: "authorization_code", code, redirect_uri: REDIRECT_URI }, fetchImpl);
}

// Shape kept in the store. `prev` carries the old refresh token forward when a
// refresh response does not include a new one.
export function tokenRecord(j, prev = null, now = Date.now()) {
  const rec = {
    access_token: j.access_token,
    access_expires_at: now + (Number(j.expires_in) || 30 * 86400) * 1000,
    refresh_token: j.refresh_token || (prev && prev.refresh_token) || null,
    refresh_expires_at: j.refresh_token
      ? now + (Number(j.refresh_token_expires_in) || 60 * 86400) * 1000
      : (prev && prev.refresh_expires_at) || null,
    scope: j.scope || (prev && prev.scope) || null,
    saved_at: now,
  };
  return rec;
}

// True only if this token can see the Daily Clue board - i.e. it belongs to the
// Hearth & Clue account. Stops a stranger who finds the connect page from
// replacing the stored sign-in with their own.
export async function ownsBoard(token, fetchImpl = fetch) {
  try {
    const r = await fetchImpl(`${API}/v5/boards/${boardId()}`, { headers: { Authorization: "Bearer " + token } });
    return r.ok;
  } catch (e) {
    return false;
  }
}

// Returns a usable access token for the unattended job, renewing it when it is
// close to expiry. Throws with a plain reason if there is nothing usable.
export async function accessToken(store, { fetchImpl = fetch, now = Date.now() } = {}) {
  const rec = await store.get("tokens", { type: "json" });
  if (!rec || !rec.access_token) throw new Error("not connected - sign in once at /pinterest-connect.html");
  if (rec.access_expires_at - now > REFRESH_WHEN_LEFT_MS) return rec.access_token;

  if (!rec.refresh_token || (rec.refresh_expires_at && rec.refresh_expires_at <= now)) {
    if (rec.access_expires_at > now) return rec.access_token; // still valid, just cannot renew
    throw new Error("sign-in has expired - sign in again at /pinterest-connect.html");
  }
  try {
    const j = await tokenCall({ grant_type: "refresh_token", refresh_token: rec.refresh_token }, fetchImpl);
    const next = tokenRecord(j, rec, now);
    await store.setJSON("tokens", next);
    return next.access_token;
  } catch (e) {
    if (rec.access_expires_at > now) return rec.access_token; // renewal failed but the old one still works
    throw new Error("could not renew the sign-in (" + String(e.message || e) + ") - sign in again at /pinterest-connect.html");
  }
}

// What the status page may show. Dates only - never a token.
export async function publicStatus(store, now = Date.now()) {
  const rec = await store.get("tokens", { type: "json" });
  const last = await store.get("last_run", { type: "json" });
  const iso = (t) => (t ? new Date(t).toISOString() : null);
  return {
    connected: !!(rec && rec.access_token),
    signed_in_at: rec ? iso(rec.saved_at) : null,
    access_expires_at: rec ? iso(rec.access_expires_at) : null,
    refresh_expires_at: rec ? iso(rec.refresh_expires_at) : null,
    needs_sign_in: !rec || !rec.access_token ||
      (rec.access_expires_at <= now && (!rec.refresh_token || (rec.refresh_expires_at || 0) <= now)),
    site_date: siteDate(new Date(now)),
    last_run: last || null,
  };
}

export async function recordRun(store, source, result, now = Date.now()) {
  const { detail, ...slim } = result || {};
  const entry = { at: new Date(now).toISOString(), source, ...slim };
  if (detail) entry.detail = JSON.stringify(detail).slice(0, 400);
  try {
    await store.setJSON("last_run", entry);
    if (result && result.status === "posted") await store.setJSON("last_posted", entry);
  } catch (e) { /* the record is a convenience, never a reason to fail */ }
  return entry;
}
