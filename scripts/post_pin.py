#!/usr/bin/env python3
"""
Post today's Daily Clue pin to Pinterest.

Usage: python scripts/post_pin.py [pins_dir]

Reads pins/manifest.json (written by generate_pins.py), works out today's
issue, and creates a standard Pinterest pin pointing at hearthandclue.com.

Never raises. A failure here must not fail the daily workflow or block the
image commit, so every error path prints and exits 0.

Environment:
  PINTEREST_TOKEN   required, repo secret
  PINTEREST_BOARD   optional, defaults to the Word Search Puzzle Books board
  SITE              optional, defaults to https://hearthandclue.com
"""
import os, sys, json, datetime, urllib.request, urllib.error

API = "https://api.pinterest.com/v5/pins"
DEFAULT_BOARD = "300615412567048694"
DEFAULT_SITE = "https://hearthandclue.com"

TITLE_MAX, DESC_MAX, ALT_MAX = 100, 800, 500


def clip(text, limit):
    """Trim to a limit on a word boundary rather than mid-word."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:-")


def build_title(entry):
    # Front-load the theme, then the evergreen search term.
    return clip("%s - a free word search puzzle" % entry["title"], TITLE_MAX)


def build_description(entry, issue):
    # No hashtags: Pinterest stopped weighting them and they read as spam.
    return clip(
        "%s. %s. Eight words hidden in the grid. "
        "A free word search puzzle, new every morning, same puzzle for everyone. "
        "No app, no signup, no ads. Play today's at hearthandclue.com. "
        "Today's is No. %d." % (entry["title"], entry["note"].rstrip(". "), issue),
        DESC_MAX,
    )


def build_alt_text(entry, issue):
    # Alt text is indexed and was missing from every earlier pin.
    return clip(
        "A ten by ten word search grid titled %s, issue number %d of The Daily Clue, "
        "with eight hidden words listed underneath: %s."
        % (entry["title"], issue, ", ".join(w.title() for w in entry["words"])
           if entry.get("words") else "eight themed words"),
        ALT_MAX,
    )


def todays_issue(manifest, today):
    """The manifest is keyed by issue number; find the entry dated today."""
    for issue, entry in manifest.items():
        if entry.get("date") == today.isoformat():
            return int(issue), entry
    return None, None


def already_posted(record_path, issue):
    try:
        with open(record_path) as f:
            return str(issue) in json.load(f)
    except Exception:
        return False


def remember(record_path, issue, pin_id):
    try:
        try:
            with open(record_path) as f:
                posted = json.load(f)
        except Exception:
            posted = {}
        posted[str(issue)] = {
            "pin_id": pin_id,
            "posted_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        # Keep the file small: the last 60 entries are plenty to stop repeats.
        for key in sorted(posted, key=int)[:-60]:
            del posted[key]
        with open(record_path, "w") as f:
            json.dump(posted, f, indent=1, sort_keys=True)
    except Exception as e:
        print("could not update record:", type(e).__name__, e)


def post(token, payload):
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    pins_dir = sys.argv[1] if len(sys.argv) > 1 else "pins"
    token = os.environ.get("PINTEREST_TOKEN", "").strip()
    board = os.environ.get("PINTEREST_BOARD", DEFAULT_BOARD).strip()
    site = os.environ.get("SITE", DEFAULT_SITE).rstrip("/")

    if not token:
        print("PINTEREST_TOKEN not set - skipping the post, images are unaffected")
        return

    manifest_path = os.path.join(pins_dir, "manifest.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except Exception as e:
        print("no usable manifest at %s: %s" % (manifest_path, type(e).__name__))
        return

    today = datetime.date.today()
    issue, entry = todays_issue(manifest, today)
    if entry is None:
        print("no manifest entry dated", today.isoformat())
        return

    record_path = os.path.join(pins_dir, "posted.json")
    if already_posted(record_path, issue):
        print("issue %d already posted - nothing to do" % issue)
        return

    image_url = "%s/pins/%d.png" % (site, issue)
    payload = {
        "board_id": board,
        "title": build_title(entry),
        "description": build_description(entry, issue),
        "alt_text": build_alt_text(entry, issue),
        "link": site + "/",
        "media_source": {"source_type": "image_url", "url": image_url},
    }

    print("posting issue %d (%s)" % (issue, entry["title"]))
    print("  image:", image_url)
    try:
        result = post(token, payload)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        print("Pinterest rejected the pin: HTTP %s %s" % (e.code, body))
        return
    except Exception as e:
        print("post failed:", type(e).__name__, e)
        return

    pin_id = result.get("id", "unknown")
    print("posted pin", pin_id)
    remember(record_path, issue, pin_id)


if __name__ == "__main__":
    main()
