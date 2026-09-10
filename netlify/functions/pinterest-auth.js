// Exchanges a Pinterest authorisation code for an access token.
// The app secret lives in a Netlify environment variable and never reaches the
// browser; the token comes back in an httpOnly cookie, so page JavaScript can
// never read it either. That is what the Standard-access demo needs to show.

const REDIRECT_URI = "https://hearthandclue.com/pinterest-connect.html";
const SANDBOX = "https://api-sandbox.pinterest.com";

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: JSON.stringify({ error: "POST only" }) };
  }

  const appId = process.env.PINTEREST_APP_ID;
  const appSecret = process.env.PINTEREST_APP_SECRET;
  if (!appId || !appSecret) {
    return {
      statusCode: 500,
      body: JSON.stringify({
        error: "PINTEREST_APP_ID or PINTEREST_APP_SECRET is not set in Netlify",
      }),
    };
  }

  let code;
  try {
    code = JSON.parse(event.body || "{}").code;
  } catch (e) {
    return { statusCode: 400, body: JSON.stringify({ error: "bad JSON body" }) };
  }
  if (!code) {
    return { statusCode: 400, body: JSON.stringify({ error: "no code supplied" }) };
  }

  const basic = Buffer.from(`${appId}:${appSecret}`).toString("base64");

  // Token exchange always goes to the production host, even on Trial access.
  let tokenRes, tokenJson;
  try {
    tokenRes = await fetch("https://api.pinterest.com/v5/oauth/token", {
      method: "POST",
      headers: {
        Authorization: `Basic ${basic}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: REDIRECT_URI,
      }).toString(),
    });
    tokenJson = await tokenRes.json();
  } catch (err) {
    return { statusCode: 502, body: JSON.stringify({ error: String(err) }) };
  }

  if (!tokenRes.ok || !tokenJson.access_token) {
    return {
      statusCode: tokenRes.status || 502,
      body: JSON.stringify({ error: "token exchange failed", detail: tokenJson }),
    };
  }

  const token = tokenJson.access_token;

  // Show something real came back: the account, and the sandbox boards.
  let account = null;
  let boards = [];
  try {
    const me = await fetch(`${SANDBOX}/v5/user_account`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (me.ok) account = await me.json();
  } catch (e) {
    /* non-fatal for the demo */
  }
  try {
    const b = await fetch(`${SANDBOX}/v5/boards?page_size=25`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (b.ok) {
      const bj = await b.json();
      boards = (bj.items || []).map((x) => ({ id: x.id, name: x.name }));
    }
  } catch (e) {
    /* non-fatal for the demo */
  }

  const cookie = [
    `pin_token=${encodeURIComponent(token)}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    `Max-Age=${60 * 60 * 24}`,
  ].join("; ");

  return {
    statusCode: 200,
    headers: { "Set-Cookie": cookie, "Content-Type": "application/json" },
    body: JSON.stringify({
      connected: true,
      username: account && account.username ? account.username : null,
      boards,
    }),
  };
};
