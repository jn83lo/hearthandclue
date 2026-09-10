// Creates one standard pin from today's entry in pins/manifest.json.
// Trial-access apps cannot create pins on the production host, so this posts to
// the sandbox — which is what Pinterest tells Trial developers to demo against.

const SANDBOX = "https://api-sandbox.pinterest.com";
const MANIFEST = "https://hearthandclue.com/pins/manifest.json";
const BOARD_NAME = "Word Search Puzzle Books";

function readCookie(header, name) {
  if (!header) return null;
  for (const part of header.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return null;
}

function sydneyToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Australia/Sydney",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: JSON.stringify({ error: "POST only" }) };
  }

  const cookies = event.headers.cookie || event.headers.Cookie;
  const token = readCookie(cookies, "pin_token");
  if (!token) {
    return {
      statusCode: 401,
      body: JSON.stringify({ error: "not connected - run the Pinterest connect step first" }),
    };
  }
  const auth = { Authorization: `Bearer ${token}` };

  // today's puzzle image, from the manifest the daily job already writes
  const today = sydneyToday();
  let entry = null;
  try {
    const m = await fetch(MANIFEST);
    if (!m.ok) throw new Error(`manifest HTTP ${m.status}`);
    const mj = await m.json();
    const items = Array.isArray(mj) ? mj : mj.pins || mj.items || [];
    entry = items.find((p) => (p.date || "").slice(0, 10) === today) || items[0] || null;
  } catch (err) {
    return { statusCode: 502, body: JSON.stringify({ error: `manifest: ${err}` }) };
  }
  if (!entry) {
    return { statusCode: 404, body: JSON.stringify({ error: "no entry in manifest" }) };
  }

  const imageUrl = entry.image_url || entry.url || entry.image;
  if (!imageUrl) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: "manifest entry has no image url", entry }),
    };
  }

  // sandbox boards are separate from production ones, so find or create one
  let boardId = null;
  try {
    const br = await fetch(`${SANDBOX}/v5/boards?page_size=25`, { headers: auth });
    if (br.ok) {
      const bj = await br.json();
      const hit = (bj.items || []).find((b) => b.name === BOARD_NAME);
      if (hit) boardId = hit.id;
    }
    if (!boardId) {
      const mk = await fetch(`${SANDBOX}/v5/boards`, {
        method: "POST",
        headers: { ...auth, "Content-Type": "application/json" },
        body: JSON.stringify({ name: BOARD_NAME, privacy: "PUBLIC" }),
      });
      const mj = await mk.json();
      if (!mk.ok) {
        return {
          statusCode: mk.status,
          body: JSON.stringify({ error: "could not create board", detail: mj }),
        };
      }
      boardId = mj.id;
    }
  } catch (err) {
    return { statusCode: 502, body: JSON.stringify({ error: `boards: ${err}` }) };
  }

  const title = entry.title || `The Daily Clue - ${entry.theme || "word search"}`;
  const words = Array.isArray(entry.words) ? entry.words.join(", ") : "";
  const body = {
    board_id: boardId,
    title: title.slice(0, 100),
    description: (
      entry.description ||
      `Today's free word search from The Daily Clue. Theme: ${entry.theme || "daily"}. Play it free at hearthandclue.com`
    ).slice(0, 500),
    alt_text: (words
      ? `A word search grid with eight hidden words: ${words}`
      : "A daily word search puzzle grid"
    ).slice(0, 500),
    link: "https://hearthandclue.com/",
    media_source: { source_type: "image_url", url: imageUrl },
  };

  try {
    const res = await fetch(`${SANDBOX}/v5/pins`, {
      method: "POST",
      headers: { ...auth, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    return {
      statusCode: res.ok ? 200 : res.status,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ok: res.ok,
        date: today,
        board_id: boardId,
        request: { title: body.title, alt_text: body.alt_text, link: body.link },
        response: json,
      }),
    };
  } catch (err) {
    return { statusCode: 502, body: JSON.stringify({ error: String(err) }) };
  }
};
