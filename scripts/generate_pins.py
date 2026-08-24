#!/usr/bin/env python3
"""
Render Daily Clue pin images to pins/<issue>.png (1000x1500, Pinterest 2:3).

Usage: python scripts/generate_pins.py [days_ahead] [index.html] [outdir]

Only writes files that do not already exist, so a daily run is cheap and the
commit is empty on days when nothing changed.
"""
import os, sys, json, datetime
from PIL import Image, ImageDraw, ImageFont
from engine import load_themes, theme_for, build, day_number

W, H = 1000, 1500
CREAM, PAPER, OX = (248, 243, 237), (255, 253, 250), (142, 42, 42)
GREEN, BRASS, RULE = (47, 75, 60), (198, 162, 102), (228, 220, 208)
INK, BAND, CELL = (51, 48, 44), (243, 234, 224), (251, 248, 243)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Fonts are fetched at run time. Every step degrades rather than raising, so a
# missing font changes how the pin looks but never fails the build.
FONT_SOURCES = {
    "Fraunces.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/fraunces/Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf",
    ],
    "Spectral-Regular.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/spectral/Spectral-Regular.ttf",
    ],
    "Spectral-Italic.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/spectral/Spectral-Italic.ttf",
    ],
    "Spectral-SemiBold.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/spectral/Spectral-SemiBold.ttf",
    ],
    "Spectral-Bold.ttf": [
        "https://raw.githubusercontent.com/google/fonts/main/ofl/spectral/Spectral-Bold.ttf",
    ],
}

SYSTEM_FALLBACKS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
]


def fetch_fonts():
    import urllib.request
    os.makedirs(FONT_DIR, exist_ok=True)
    for name, urls in FONT_SOURCES.items():
        dest = os.path.join(FONT_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            continue
        for url in urls:
            try:
                urllib.request.urlretrieve(url, dest)
                if os.path.getsize(dest) > 1000:
                    print("font ok:", name)
                    break
                os.remove(dest)
            except Exception as e:
                print("font miss:", name, type(e).__name__)


def loadable(path, size=24):
    """A font only counts if Pillow can actually open it."""
    if not path or not os.path.exists(path):
        return False
    try:
        ImageFont.truetype(path, size)
        return True
    except Exception:
        return False


def resolve(*candidates):
    for c in candidates:
        p = c if os.path.isabs(c) else os.path.join(FONT_DIR, c)
        if loadable(p):
            return p
    for p in SYSTEM_FALLBACKS:
        if loadable(p):
            return p
    return None            # last resort: PIL's built-in face


DISPLAY = BODY = BODY_I = BODY_SB = None


def choose_fonts():
    global DISPLAY, BODY, BODY_I, BODY_SB
    DISPLAY = resolve("Fraunces.ttf", "Spectral-Bold.ttf")
    BODY = resolve("Spectral-Regular.ttf")
    BODY_I = resolve("Spectral-Italic.ttf", "Spectral-Regular.ttf")
    BODY_SB = resolve("Spectral-SemiBold.ttf", "Spectral-Regular.ttf")
    print("display font:", DISPLAY or "PIL default")
    print("body font   :", BODY or "PIL default")


def font(path, size, bold=False):
    if not path:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()
    f = ImageFont.truetype(path, size)
    if bold:
        # Fraunces ships as a variable font; ask for its bold instance if available.
        try:
            f.set_variation_by_name("Bold")
        except Exception:
            pass
    return f


def centre(d, y, text, f, fill, tracking=0):
    if tracking:
        ws = [d.textlength(c, font=f) for c in text]
        total = sum(ws) + tracking * (len(text) - 1)
        x = (W - total) / 2
        for c, w in zip(text, ws):
            d.text((x, y), c, font=f, fill=fill)
            x += w + tracking
        return
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def render(theme, grid, issue, date, out_path):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    centre(d, 78, "The Daily Clue", font(DISPLAY, 76, bold=True), INK)
    d.line([(W / 2 - 44, 186), (W / 2 + 44, 186)], fill=BRASS, width=3)
    d.line([(W / 2 - 44, 194), (W / 2 + 44, 194)], fill=BRASS, width=3)
    centre(d, 214, "A free word search, every day", font(BODY_I, 30), GREEN)

    d.rounded_rectangle([70, 282, W - 70, 410], radius=4, fill=BAND)
    centre(d, 306, theme["title"], font(DISPLAY, 40, bold=True), OX)
    centre(d, 362, theme["note"], font(BODY_I, 25), GREEN)

    top, size, gap = 440, 64, 5
    board = 10 * size + 9 * gap
    left = (W - board) / 2
    d.rounded_rectangle([left - 16, top - 16, left + board + 16, top + board + 16],
                        radius=4, fill=PAPER, outline=RULE, width=2)
    gf = font(BODY_SB, 33)
    for y in range(10):
        for x in range(10):
            cx, cy = left + x * (size + gap), top + y * (size + gap)
            d.rounded_rectangle([cx, cy, cx + size, cy + size], radius=3,
                                fill=CELL, outline=RULE, width=1)
            ch = grid[y][x]
            d.text((cx + (size - d.textlength(ch, font=gf)) / 2, cy + 11), ch, font=gf, fill=INK)

    wy, wf = top + board + 42, font(BODY, 24)
    for row in range(2):
        chunk = theme["words"][row * 4:(row + 1) * 4]
        widths = [d.textlength(w, font=wf) + 40 for w in chunk]
        total = sum(widths) + 14 * (len(chunk) - 1)
        x = (W - total) / 2
        for w, bw in zip(chunk, widths):
            d.rounded_rectangle([x, wy, x + bw, wy + 50], radius=3, fill=PAPER, outline=RULE, width=1)
            d.text((x + 20, wy + 12), w, font=wf, fill=INK)
            x += bw + 14
        wy += 64

    d.line([(180, H - 190), (W - 180, H - 190)], fill=RULE, width=2)
    centre(d, H - 164, "hearthandclue.com", font(DISPLAY, 38, bold=True), OX)
    centre(d, H - 100, "NO. %d  \u00b7  %s" % (issue, date.strftime("%a %b %d %Y").upper()),
           font(BODY, 20), BRASS, tracking=2)

    img.save(out_path, "PNG", optimize=True)


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    index = sys.argv[2] if len(sys.argv) > 2 else "index.html"
    outdir = sys.argv[3] if len(sys.argv) > 3 else "pins"

    fetch_fonts()
    choose_fonts()

    themes = load_themes(index)
    os.makedirs(outdir, exist_ok=True)
    today = datetime.date.today()
    manifest, made = {}, 0

    for i in range(days):
        d = today + datetime.timedelta(days=i)
        t = theme_for(themes, d)
        issue = day_number(d) + 1
        path = os.path.join(outdir, "%d.png" % issue)
        manifest[str(issue)] = {
            "date": d.isoformat(), "title": t["title"], "note": t["note"],
            "subject": t["subject"], "url": t["url"], "image": "/pins/%d.png" % issue
        }
        if os.path.exists(path):
            continue
        grid = build(t["words"], d.year * 10000 + d.month * 100 + d.day)
        if grid is None:
            print("could not build", d, t["title"])
            continue
        render(t, grid, issue, d, path)
        made += 1
        print("rendered", path, "-", t["title"])

    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    # Keep the folder from growing without bound: drop anything older than a week.
    cutoff = day_number(today) + 1 - 7
    for name in os.listdir(outdir):
        if name.endswith(".png"):
            try:
                if int(name[:-4]) < cutoff:
                    os.remove(os.path.join(outdir, name))
                    print("pruned", name)
            except ValueError:
                pass

    print("done: %d new image(s), %d in manifest" % (made, len(manifest)))


if __name__ == "__main__":
    main()
