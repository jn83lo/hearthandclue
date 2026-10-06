#!/usr/bin/env python3
"""Etsy listing photos for a book: five 2000x2000 JPEGs drawn from the finished PDF.

    python printables/book_listing.py <book.json> <book.pdf> <out_dir>

Etsy's own guidance (Seller Handbook, and its 2023 announcement on image
ratios): 2000 px on the shortest side, square displays well everywhere, under
1 MB uploads fastest, and the first photo should not be a collage.

The set follows the house order: cover, what's inside, an easy page, a hard
page, an answer page. Every page in a photo is rendered from the PDF given
here, so a photo can never show a page from an older draft, and the run
prints that PDF's sha256 so a handover can name the exact file.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import book as B    # noqa: E402
import fonts        # noqa: E402
import ws           # noqa: E402
from pdfs import PROMISED  # noqa: E402

SS = 2              # drawn at twice the size, then scaled down for smooth edges
SIDE = 2000
CREAM, GREEN, BRASS = (248, 243, 237), (47, 75, 60), (198, 162, 102)
INK, SOFT = (51, 48, 44), (95, 90, 82)
WORDS = {   # how each level's words run, in two short lines
    "easy": ("Words run across", "and down only"),
    "medium": ("Across, down and", "diagonal, never backwards"),
    "hard": ("Every direction,", "backwards too"),
}


def face(name, px):
    return ImageFont.truetype(fonts.path(name), int(round(px * SS)))


def _covers(name, text):
    """Raise if the face has no glyph for a character (it would print as a box)."""
    from fontTools.ttLib import TTFont
    cmap = TTFont(fonts.path(name), lazy=True).getBestCmap()
    missing = sorted({ch for ch in text if ord(ch) not in cmap and not ch.isspace()})
    if missing:
        raise AssertionError("%s has no glyph for %r" % (name, "".join(missing)))


class Canvas:
    def __init__(self):
        self.img = Image.new("RGBA", (SIDE * SS, SIDE * SS), CREAM + (255,))
        self.d = ImageDraw.Draw(self.img)
        self.used = []

    def text(self, x, y, s, name, px, fill, anchor="ls", tracking=0.0):
        """Text at (x, y) in final pixels; y is the baseline. Returns its width."""
        _covers(name, s)
        f = face(name, px)
        d = self.d
        if not tracking:
            d.text((x * SS, y * SS), s, font=f, fill=fill, anchor=anchor)
            w = d.textlength(s, font=f) / SS
        else:
            w = (sum(d.textlength(ch, font=f) for ch in s) + tracking * SS * (len(s) - 1)) / SS
            x0 = {"l": x, "m": x - w / 2.0, "r": x - w}[anchor[0]] * SS
            for ch in s:
                d.text((x0, y * SS), ch, font=f, fill=fill, anchor="l" + anchor[1])
                x0 += d.textlength(ch, font=f) + tracking * SS
        left = {"l": x, "m": x - w / 2.0, "r": x - w}[anchor[0]]
        self.used.append((left, left + w, s))
        return w

    def width(self, s, name, px):
        return self.d.textlength(s, font=face(name, px)) / SS

    def fit(self, s, name, px, maxw):
        while self.width(s, name, px) > maxw and px > 20:
            px -= 2
        return px

    def chip(self, x, y, label, colour, px=44):
        """An outlined pill, left edge at x, centred on y."""
        w = self.width(label, "Atkinson-Bold.ttf", px) + 2.0 * (len(label) - 1)
        h = px * 2.0
        box = (x * SS, (y - h / 2) * SS, (x + w + 2 * px * 1.1) * SS, (y + h / 2) * SS)
        self.d.rounded_rectangle(box, radius=h / 2 * SS, outline=colour, width=int(5 * SS), fill=(255, 253, 250))
        self.text(x + px * 1.1, y + px * 0.36, label, "Atkinson-Bold.ttf", px, colour, tracking=2.0)
        return w + 2 * px * 1.1

    def tick(self, x, y, size, colour):
        """A check mark whose box has its top-left corner at (x, y)."""
        s = size
        pts = [(x + 0.08 * s, y + 0.55 * s), (x + 0.38 * s, y + 0.85 * s), (x + 0.95 * s, y + 0.15 * s)]
        self.d.line([(px * SS, py * SS) for px, py in pts], fill=colour, width=int(s * 0.16 * SS), joint="curve")

    def rule(self, x0, x1, y, colour=BRASS, width=4):
        self.d.line((x0 * SS, y * SS, x1 * SS, y * SS), fill=colour, width=int(width * SS))

    def place(self, card, cx, cy):
        self.img.alpha_composite(card, (int(cx * SS - card.width / 2), int(cy * SS - card.height / 2)))
        self.d = ImageDraw.Draw(self.img)

    def save(self, path):
        out = self.img.convert("RGB").resize((SIDE, SIDE), Image.LANCZOS)
        for q in (90, 86, 82, 78):
            buf = io.BytesIO()
            out.save(buf, "JPEG", quality=q, optimize=True, progressive=True, dpi=(72, 72))
            if buf.tell() < 1000 * 1000:
                break
        else:
            raise AssertionError("%s will not go under 1 MB" % path)
        open(path, "wb").write(buf.getvalue())
        return {"bytes": buf.tell(), "quality": q}


def render(pdf, page_no, dpi, colour=False):
    with tempfile.TemporaryDirectory() as tmp:
        args = ["pdftoppm", "-r", str(dpi), "-f", str(page_no), "-l", str(page_no), "-png"]
        if not colour:
            args.append("-gray")
        subprocess.run(args + [pdf, os.path.join(tmp, "p")], check=True)
        name = [f for f in os.listdir(tmp) if f.endswith(".png")][0]
        return Image.open(os.path.join(tmp, name)).convert("RGB").copy()


def card(page, width, angle):
    """A printed page with a soft shadow, turned a little. Width in final pixels."""
    w = int(width * SS)
    h = int(page.height * w / page.width)
    pg = page.resize((w, h), Image.LANCZOS)
    pad = int(w * 0.12)
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    for blur, off, alpha in ((w * 0.04, w * 0.026, 70), (w * 0.01, w * 0.007, 95)):
        sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((pad + off * 0.5, pad + off, pad + w + off * 0.5, pad + h + off), fill=(30, 20, 10, alpha))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    out.paste(pg, (pad, pad))
    ImageDraw.Draw(out).rectangle((pad, pad, pad + w - 1, pad + h - 1), outline=(222, 214, 200, 255), width=max(2, w // 700))
    return out.rotate(angle, resample=Image.BICUBIC, expand=True)


# ---------------------------------------------------------------- the photos

def photo_cover(pdf, book, P, accent):
    c = Canvas()
    x, dy = 130, 48
    c.text(x, 330 + dy, "HEARTH & CLUE", "Atkinson-Bold.ttf", 40, GREEN, tracking=9)
    px = c.fit(str(P["total"]), "Fraunces-Bold.ttf", 470, 760)
    c.text(x - 8, 760 + dy, str(P["total"]), "Fraunces-Bold.ttf", px, accent)
    c.text(x, 915 + dy, "large print", "Fraunces-BoldItalic.ttf", 124, GREEN)
    c.text(x, 1045 + dy, "puzzles", "Fraunces-BoldItalic.ttf", 124, GREEN)
    c.rule(x, x + 150, 1125 + dy)
    c.text(x, 1220 + dy, "Easy, medium and hard,", "Spectral-Italic.ttf", 58, INK)
    c.text(x, 1296 + dy, "with every answer.", "Spectral-Italic.ttf", 58, INK)
    c.chip(x, 1440 + dy, "PRINTABLE PDF", GREEN)
    c.chip(x, 1560 + dy, "US LETTER + A4", accent)
    behind = card(render(pdf, P["first"] + book["listing"]["inside_sample"] - 1, 220), 700, 6.5)
    c.place(behind, 1520, 1035)
    front = card(render(pdf, 1, 300, colour=True), 760, -2.5)
    c.place(front, 1395, 1000)
    return c


def photo_inside(pdf, book, P, accent):
    c = Canvas()
    c.text(1000, 225, "What" + chr(8217) + "s inside", "Fraunces-Bold.ttf", 118, INK, anchor="ms")
    c.text(1000, 320, "%d pages, ready to print at home" % P["pages"], "Spectral-Italic.ttf", 60, SOFT, anchor="ms")
    pages = [(P["contents_first"], "Contents"), (P["tracker"], "Tick-off tracker"),
             (P["first"] + book["listing"]["inside_sample"] - 1, "One puzzle a page")]
    for (pno, label), cx, angle in zip(pages, (400, 1000, 1600), (-1.5, 0.0, 1.5), strict=True):
        c.place(card(render(pdf, pno, 200), 500, angle), cx, 740)
        c.text(cx, 1150, label, "Spectral-SemiBold.ttf", 54, INK, anchor="ms")
    by = {g["level"]: g["last"] - g["first"] + 1 for g in P["groups"]}
    sizes = sorted({PROMISED[g["level"]] for g in P["groups"]}, reverse=True)
    lines = [
        "%d puzzles: %d easy, %d medium and %d hard" % (P["total"], by["easy"], by["medium"], by["hard"]),
        "Big grid letters: %s and %d point" % (", ".join(str(s) for s in sizes[:-1]), sizes[-1]),
        "Every answer at the back, words highlighted",
        "US Letter and A4 files, both included",
        "Contents and answer pages you can tap",
        "Instant download, any home printer",
    ]
    y = 1300
    for line in lines:
        c.tick(250, y - 46, 50, GREEN)
        c.text(330, y, line, "Spectral-Regular.ttf", 58, INK)
        y += 96
    return c


def photo_level(pdf, book, P, accent, level, n):
    c = Canvas()
    g = [g for g in P["groups"] if g["level"] == level][0]
    if not g["first"] <= n <= g["last"]:
        raise AssertionError("puzzle %d is not a %s puzzle" % (n, level))
    spec = ws.LEVELS[level]
    x, dy = 120, 170
    c.text(x, 560 + dy, spec["label"], "Fraunces-Bold.ttf", 150, accent)
    c.rule(x, x + 130, 625 + dy)
    y = 745 + dy
    for line in ("%d puzzles" % (g["last"] - g["first"] + 1),
                 "%d %s %d grids" % (spec["size"], chr(215), spec["size"]),
                 "%d pt letters" % PROMISED[level]):
        c.text(x, y, line, "Spectral-Regular.ttf", 62, INK)
        y += 92
    y += 40
    for line in WORDS[level]:
        c.text(x, y, line, "Spectral-Italic.ttf", 54, SOFT)
        y += 74
    c.place(card(render(pdf, P["first"] + n - 1, 300), 1180, -1.2), 1300, 1000)
    return c


def photo_answers(pdf, book, P, accent, n):
    c = Canvas()
    x, dy = 120, 140
    c.text(x, 520 + dy, "Every", "Fraunces-Bold.ttf", 140, accent)
    c.text(x, 660 + dy, "answer", "Fraunces-Bold.ttf", 140, accent)
    c.rule(x, x + 130, 725 + dy)
    y = 845 + dy
    for line in ("At the back,", "two to a page"):
        c.text(x, y, line, "Spectral-Regular.ttf", 62, INK)
        y += 84
    y += 40
    for line in ("Every word", "highlighted"):
        c.text(x, y, line, "Spectral-Regular.ttf", 62, INK)
        y += 84
    y += 40
    for line in ("Each puzzle names", "its answer page"):
        c.text(x, y, line, "Spectral-Italic.ttf", 54, SOFT)
        y += 74
    c.place(card(render(pdf, B.answer_page_no(P, n), 300), 1180, 1.0), 1300, 1000)
    return c


def build(book_path, pdf, out_dir):
    fonts.ensure_book()
    book = B.load(book_path)
    P = B.plan(book)
    accent = tuple(book["cover"]["accent"])
    L = book["listing"]
    os.makedirs(out_dir, exist_ok=True)
    stem = book["id"]
    shots = [
        ("01-cover", photo_cover(pdf, book, P, accent)),
        ("02-whats-inside", photo_inside(pdf, book, P, accent)),
        ("03-easy-page", photo_level(pdf, book, P, accent, "easy", L["easy_sample"])),
        ("04-hard-page", photo_level(pdf, book, P, accent, "hard", L["hard_sample"])),
        ("05-answers", photo_answers(pdf, book, P, accent, L["hard_sample"])),
    ]
    report = {"pdf": os.path.basename(pdf), "pdf_sha256": hashlib.sha256(open(pdf, "rb").read()).hexdigest(), "photos": {}}
    for name, c in shots:
        for left, right, s in c.used:
            if left < 60 or right > SIDE - 60:
                raise AssertionError("%s: %r runs into the edge" % (name, s))
        path = os.path.join(out_dir, "%s-%s.jpg" % (stem, name))
        report["photos"][os.path.basename(path)] = c.save(path)
    json.dump(report, open(os.path.join(out_dir, "listing.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3])
