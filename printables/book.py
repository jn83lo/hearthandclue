#!/usr/bin/env python3
"""Build a puzzle book for sale: one PDF for each paper size.

    python printables/book.py <book.json> <out_dir>

A book is the free packs' puzzle page (the same engine and the same measured
large print) repeated for every puzzle, with a cover, a page on how the book
works, a contents list, a tracker for ticking puzzles off, the answers two to
a page and a closing page.

The page numbers printed in the book are the PDF's own page numbers, so
"Answer on page 110" is page 110 in a print window as well. The contents
list, the tracker, each "Answer on page" and each answer heading can also be
tapped.

Typefaces: the puzzles and the reading text are Atkinson Hyperlegible, as in
the packs. Anything with page or puzzle numbers in it (footers, the contents
and tracker figures, the table of pages) is Spectral, because Atkinson's zero
has a slash through it and "100" set that way can be taken for a misprint.
qc_pdf.check_book refuses a book with an Atkinson zero anywhere in it.

A book is a product. Keep the finished PDFs and the book's .json out of the
website's folder: everything in that folder is published.

The build stops with an error if any grid fails ws.verify(), or if a finished
PDF, read back by qc_pdf.check_book, differs from what was meant.
"""
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pdfs     # noqa: E402  (first: it switches the PDF library to same-bytes mode)
from reportlab.pdfbase.pdfmetrics import stringWidth     # noqa: E402

import fonts    # noqa: E402
import qc_pdf   # noqa: E402
import ws       # noqa: E402
from pdfs import PAGES, PAPER, M_SIDE, M_TOP, M_BOT, PROMISED, WORD_PT, DOT, COPY, _centre, _fit  # noqa: E402

CREAM, WHITE = (248, 243, 237), (255, 253, 250)
GREEN, BRASS, INK = (47, 75, 60), (198, 162, 102), (51, 48, 44)
FOOT_PT, FOOT_GREY = 12.5, 0.25     # footers carry the page numbers, so they are larger than the packs'
NUM = "SpS"                         # the face for figures (see the note on typefaces above)
SOFT = 0.25                         # grey for secondary text
APOS, DASH = chr(8217), chr(8211)
ROWS_PER_PAGE = 25                  # contents: rows of two entries on a page
FILE_TAG = {"letter": "US-Letter", "a4": "A4"}

# The bat from the pins (art.py), as points on a unit square.
BAT = [(0.00, 0.26), (0.17, 0.04), (0.33, 0.22), (0.42, 0.20), (0.44, 0.02), (0.48, 0.15),
       (0.52, 0.15), (0.56, 0.02), (0.58, 0.20), (0.67, 0.22), (0.83, 0.04), (1.00, 0.26),
       (0.91, 0.40), (0.83, 0.64), (0.73, 0.44), (0.64, 0.68), (0.56, 0.50), (0.50, 0.80),
       (0.44, 0.50), (0.36, 0.68), (0.27, 0.44), (0.17, 0.64), (0.09, 0.40)]


def nice(text):
    """A typewriter apostrophe becomes a real one."""
    return text.replace("'", APOS)


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower().replace("'", "")).strip("-")


def load(path):
    book = json.load(open(path))
    seen = set()
    for p in book["puzzles"]:
        p["slug"] = slug(p["title"])
        if p["slug"] in seen:
            raise AssertionError("two puzzles are both called %r" % p["title"])
        seen.add(p["slug"])
        p["title"], p["note"] = nice(p["title"]), nice(p["note"])
    return book


def level_groups(puzzles):
    """Runs of puzzles at the same level: [{"level", "first", "last"}], numbered from 1."""
    out = []
    for i, p in enumerate(puzzles, 1):
        if out and out[-1]["level"] == p["level"]:
            out[-1]["last"] = i
        else:
            out.append({"level": p["level"], "first": i, "last": i})
    return out


def contents_chunks(groups):
    """Share the level groups out over the contents pages."""
    sheets, cur, room = [], [], ROWS_PER_PAGE
    for g in groups:
        first = g["first"]
        while first <= g["last"]:
            if room == 0:
                sheets.append(cur)
                cur, room = [], ROWS_PER_PAGE
            rows = min(room, -(-(g["last"] - first + 1) // 2))
            last = min(g["last"], first + rows * 2 - 1)
            cur.append({"level": g["level"], "first": first, "last": last, "continued": first != g["first"]})
            room -= rows
            first = last + 1
    if cur:
        sheets.append(cur)
    return sheets


def plan(book):
    """Which page everything is on. Pages are numbered from 1, as a print window numbers them."""
    total = len(book["puzzles"])
    groups = level_groups(book["puzzles"])
    chunks = contents_chunks(groups)
    tracker = 3 + len(chunks)               # after the cover, the how-to page and the contents
    first = tracker + 1
    first_answer = first + total
    sheets = -(-total // 2)
    for g in groups:
        g["pages"] = (first + g["first"] - 1, first + g["last"] - 1)
    return {"total": total, "groups": groups, "chunks": chunks, "contents_first": 3, "tracker": tracker,
            "first": first, "first_answer": first_answer, "sheets": sheets,
            "closing": first_answer + sheets, "pages": first_answer + sheets}


def puzzle_page_no(P, n):
    return P["first"] + n - 1


def answer_page_no(P, n):
    return P["first_answer"] + (n - 1) // 2


def _rgb(c, colour, stroke=False):
    r, g, b = [v / 255.0 for v in colour]
    (c.setStrokeColorRGB if stroke else c.setFillColorRGB)(r, g, b)


def _rule(c, x, y, half=34.0):
    c.setStrokeGray(pdfs.EDGE)
    c.setLineWidth(0.8)
    for dy in (0, 3.2):
        c.line(x - half, y + dy, x + half, y + dy)


def footer(c, W, site, mid, right, dest=None):
    """Site on the left, what this page is in the middle, its page number on the right."""
    y = M_BOT - 6
    lw, mw, rw = (stringWidth(t, NUM, FOOT_PT) for t in (site, mid, right))
    if M_SIDE + lw + 14 > W / 2 - mw / 2 or W / 2 + mw / 2 + 14 > W - M_SIDE - rw:
        raise AssertionError("footer text collides: %r | %r | %r" % (site, mid, right))
    c.setFillGray(FOOT_GREY)
    c.setFont(NUM, FOOT_PT)
    c.drawString(M_SIDE, y, site)
    c.drawCentredString(W / 2, y, mid)
    c.drawRightString(W - M_SIDE, y, right)
    c.linkURL("https://" + site, (M_SIDE, y - 4, M_SIDE + lw, y + 11), relative=0)
    if dest:
        c.linkAbsolute("", dest, Rect=(W - M_SIDE - rw, y - 4, W - M_SIDE, y + 11), thickness=0)


# ---------------------------------------------------------------- the cover

def _pumpkin(c, cx, cy, w, body=(226, 113, 29), rib=(184, 82, 15), stem=(86, 98, 52)):
    h = w * 0.78
    _rgb(c, stem)
    c.roundRect(cx - w * 0.07, cy + h * 0.38, w * 0.14, h * 0.34, w * 0.03, stroke=0, fill=1)
    _rgb(c, body)
    _rgb(c, rib, stroke=True)
    c.setLineWidth(max(0.8, w * 0.018))
    for dx, ww in ((-0.30, 0.44), (0.30, 0.44), (-0.14, 0.46), (0.14, 0.46), (0.0, 0.42)):
        c.ellipse(cx + (dx - ww / 2) * w, cy - h / 2, cx + (dx + ww / 2) * w, cy + h / 2, stroke=1, fill=1)


def _bat(c, cx, cy, w, colour, tilt=0.0):
    h = w * 0.62
    a = math.radians(tilt)
    path = c.beginPath()
    for i, (u, v) in enumerate(BAT):
        x, y = (u - 0.5) * w, -(v - 0.4) * h
        px, py = cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)
        (path.moveTo if i == 0 else path.lineTo)(px, py)
    path.close()
    _rgb(c, colour)
    c.drawPath(path, stroke=0, fill=1)


def _ornament(c, cx, cy, w, body, band, cap=BRASS):
    """A glass bauble hanging from its cap: w is the ball's width."""
    r = w / 2.0
    _rgb(c, cap, stroke=True)
    c.setLineWidth(max(0.8, w * 0.03))
    c.circle(cx, cy + r + w * 0.17, w * 0.06, stroke=1, fill=0)
    _rgb(c, cap)
    c.roundRect(cx - w * 0.12, cy + r - w * 0.04, w * 0.24, w * 0.14, w * 0.02, stroke=0, fill=1)
    _rgb(c, body)
    c.circle(cx, cy, r, stroke=0, fill=1)
    # the band: the front half of a ring round the ball, cut off at its edge
    c.saveState()
    clip = c.beginPath()
    clip.circle(cx, cy, r)
    c.clipPath(clip, stroke=0, fill=0)
    _rgb(c, band, stroke=True)
    c.setLineWidth(max(0.8, w * 0.07))
    c.arc(cx - r * 1.1, cy - r * 0.22, cx + r * 1.1, cy + r * 0.22, startAng=180, extent=180)
    c.restoreState()
    # a curved glint, upper left
    _rgb(c, WHITE, stroke=True)
    c.setLineWidth(max(0.6, w * 0.05))
    c.setLineCap(1)
    c.arc(cx - r * 0.72, cy - r * 0.72, cx + r * 0.72, cy + r * 0.72, startAng=112, extent=46)
    c.setLineCap(0)


def _snowflake(c, cx, cy, w, colour):
    """Six arms, each with two pairs of short branches."""
    _rgb(c, colour, stroke=True)
    c.setLineWidth(max(0.7, w * 0.07))
    c.setLineCap(1)
    for k in range(6):
        a = math.radians(90 + 60 * k)
        ux, uy = math.cos(a), math.sin(a)
        c.line(cx, cy, cx + ux * w / 2, cy + uy * w / 2)
        for at, length in ((0.30, 0.16), (0.55, 0.12)):
            bx, by = cx + ux * w * at, cy + uy * w * at
            for turn in (-50, 50):
                b = a + math.radians(turn)
                c.line(bx, by, bx + math.cos(b) * w * length, by + math.sin(b) * w * length)
    c.setLineCap(0)


def cover(c, page, book):
    """Page 1: the house cover (cream, double border, two-colour title, a small grid).
    The grid's corner holds the book's motif: a pumpkin and two bats ("halloween",
    the default) or two baubles and two snowflakes ("christmas")."""
    W, H = PAGES[page]
    cv = book["cover"]
    accent = tuple(cv["accent"])
    motif = cv.get("motif", "halloween")
    k = H / 792.0                       # the taller A4 page spreads the same parts out a little
    s = min(W / 612.0, H / 792.0)       # ...and its narrower width shrinks them a little

    def top(v):
        return H - v * k

    c.setPageSize((W, H))
    _rgb(c, CREAM)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    _rgb(c, accent, stroke=True)
    c.setLineWidth(1.5)
    c.rect(24, 24, W - 48, H - 48, stroke=1, fill=0)
    _rgb(c, BRASS, stroke=True)
    c.setLineWidth(0.7)
    c.rect(29.5, 29.5, W - 59, H - 59, stroke=1, fill=0)

    # the imprint, with its brass rule and dot
    y = top(88)
    _rgb(c, GREEN)
    brand, size, track = "HEARTH & CLUE", 12.0 * s, 3.4 * s
    bw = stringWidth(brand, "AtkB", size) + track * (len(brand) - 1)
    t = c.beginText(W / 2 - bw / 2, y)
    t.setFont("AtkB", size)
    t.setCharSpace(track)
    t.textOut(brand)
    t.setCharSpace(0)
    c.drawText(t)
    _rgb(c, BRASS, stroke=True)
    c.setLineWidth(0.9)
    c.line(W / 2 - 66 * s, y - 13, W / 2 - 9, y - 13)
    c.line(W / 2 + 9, y - 13, W / 2 + 66 * s, y - 13)
    _rgb(c, BRASS)
    c.circle(W / 2, y - 13, 1.9, stroke=0, fill=1)

    # the title: upright in the accent colour, then italic in green
    room = W - 2 * 66
    size1 = min(92.0 * s, 92.0 * room / stringWidth(cv["title"], "Fr", 92.0))
    _rgb(c, accent)
    c.setFont("Fr", size1)
    c.drawCentredString(W / 2, top(196), cv["title"])
    size2 = min(74.0 * s, 74.0 * room / stringWidth(cv["title2"], "FrBI", 74.0))
    _rgb(c, GREEN)
    c.setFont("FrBI", size2)
    c.drawCentredString(W / 2, top(270), cv["title2"])
    _rgb(c, INK)
    c.setFont("Sp", 24.0 * s)
    c.drawCentredString(W / 2, top(316), cv["subtitle"])

    # the grid, two words ringed, a pumpkin on its corner and two bats leaving
    rows = cv["grid"]
    n = len(rows)
    side = 232.0 * s
    cell = side / n
    gx, gtop = (W - side) / 2.0, top(350)
    pad = 9.0 * s
    _rgb(c, WHITE)
    _rgb(c, GREEN, stroke=True)
    c.setLineWidth(1.5)
    c.roundRect(gx - pad, gtop - side - pad, side + 2 * pad, side + 2 * pad, 11 * s, stroke=1, fill=1)
    pw = 104.0 * s
    pcx, pcy = gx + side + pad - pw * 0.30, gtop - side - pad + pw * 0.26

    # the second, smaller bauble sits to the left of the first and a little lower
    ow, ocx, ocy = pw * 0.86, pcx + pw * 0.02, pcy + pw * 0.02
    sw, scx, scy = pw * 0.56, pcx - pw * 0.58, pcy - pw * 0.16

    def under_pumpkin(x, y):
        # a letter is left out if any of it would be hidden: the pumpkin's
        # outline, grown by half a letter, and the stem above it (or, on a
        # Christmas cover, each bauble and its cap)
        reach = cell * 0.30
        if motif == "christmas":
            for bw, bx, by in ((ow, ocx, ocy), (sw, scx, scy)):
                if math.hypot(x - bx, y - by) < bw / 2 + reach:
                    return True
                if abs(x - bx) < bw * 0.14 + reach and 0 < y - by < bw * 0.75 + reach:
                    return True
            return False
        body = ((x - pcx) / (pw * 0.52 + reach)) ** 2 + ((y - pcy) / (pw * 0.39 + reach)) ** 2 < 1.0
        stem = abs(x - pcx) < pw * 0.07 + reach and 0 < y - pcy < pw * 0.56 + reach
        return body or stem

    _rgb(c, INK)
    c.setFont("AtkB", cell * 0.52)
    drop = cell * 0.52 * 0.668 / 2.0
    for r in range(n):
        for col in range(n):
            x, y = gx + (col + 0.5) * cell, gtop - (r + 0.5) * cell
            if not under_pumpkin(x, y):
                c.drawCentredString(x, y - drop, rows[r][col])
    for r, col, length, colour in cv["rings"]:
        _rgb(c, accent if colour == "accent" else GREEN, stroke=True)
        c.setLineWidth(1.9 * s)
        rad = cell * 0.40
        x0, x1 = gx + (col + 0.5) * cell, gx + (col + length - 0.5) * cell
        yc = gtop - (r + 0.5) * cell
        c.roundRect(x0 - rad, yc - rad, x1 - x0 + 2 * rad, 2 * rad, rad, stroke=1, fill=0)
    if motif == "christmas":
        _ornament(c, scx, scy, sw, GREEN, BRASS)
        _ornament(c, ocx, ocy, ow, accent, BRASS)
        _snowflake(c, gx + side + pad + 30 * s, gtop + 4 * s, 46 * s, GREEN)
        _snowflake(c, gx + side + pad + 62 * s, gtop - 34 * s, 28 * s, accent)
    else:
        _pumpkin(c, pcx, pcy, pw)
        _bat(c, gx + side + pad + 30 * s, gtop + 4 * s, 50 * s, INK, tilt=14)
        _bat(c, gx + side + pad + 62 * s, gtop - 34 * s, 30 * s, INK, tilt=-8)

    # what it is
    line = "LARGE PRINT   %s   PRINTABLE PDF" % DOT
    size, track = 11.0 * s, 2.6 * s
    lw = stringWidth(line, "AtkB", size) + track * (len(line) - 1)
    _rgb(c, accent)
    t = c.beginText(W / 2 - lw / 2, top(646))
    t.setFont("AtkB", size)
    t.setCharSpace(track)
    t.textOut(line)
    t.setCharSpace(0)
    c.drawText(t)
    _rgb(c, INK)
    c.setFont("SpI", 16.5 * s)
    for i, text in enumerate(cv["tagline"]):
        c.drawCentredString(W / 2, top(684 + i * 22), nice(text))
    line = "EVERY PUZZLE TELLS A STORY"
    size, track = 8.0 * s, 2.4 * s
    lw = stringWidth(line, "Atk", size) + track * (len(line) - 1)
    c.setFillGray(0.42)
    t = c.beginText(W / 2 - lw / 2, 48)
    t.setFont("Atk", size)
    t.setCharSpace(track)
    t.textOut(line)
    t.setCharSpace(0)
    c.drawText(t)
    c.showPage()


# ------------------------------------------------------- the pages of words

def _wrap(text, font, size, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if stringWidth(trial, font, size) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    # no last line of a single word: bring one down to keep it company
    if len(lines) > 1 and " " not in lines[-1] and lines[-2].count(" ") >= 3:
        head, _, tail = lines[-2].rpartition(" ")
        if stringWidth(tail + " " + lines[-1], font, size) <= width:
            lines[-2], lines[-1] = head, tail + " " + lines[-1]
    return lines


def _flow(c, items, x, y, width, size, draw=True):
    """Lay out headings and paragraphs downwards from y. Returns the y below the last line.

    Kinds: "h" a heading; "p" a paragraph of reading text; "table" pairs of
    (name, figures) two to a row; "fine" a paragraph set in the figure face,
    for a line that has to carry a year or a count.
    """
    lead = size * 1.36
    for kind, text in items:
        if kind == "h":
            y -= size * 0.95
            if draw:
                c.setFillGray(0.0)
                c.setFont("FrS", size * 1.34)
                c.drawString(x, y, text)
            y -= lead * 1.12
        elif kind in ("p", "fine"):
            face = "Atk" if kind == "p" else "SpM"
            if kind == "p" and "0" in text:
                raise AssertionError("reading text may not hold a zero (it would be slashed): %r" % text)
            for line in _wrap(text, face, size, width):
                if draw:
                    c.setFillGray(0.0)
                    c.setFont(face, size)
                    c.drawString(x, y, line)
                y -= lead
            y -= size * 0.52
        elif kind == "table":
            colw = width / 2.0
            for i, (name, value) in enumerate(text):
                cx = x + (i % 2) * colw
                if draw:
                    c.setFillGray(0.0)
                    c.setFont("AtkB", size)
                    c.drawString(cx + 14, y, name)
                    c.setFont(NUM, size * 1.06)
                    c.drawString(cx + 14 + size * 5.0, y, value)
                if i % 2 == 1 or i == len(text) - 1:
                    y -= lead
            y -= size * 0.52
    return y


def _span(a, b):
    return "%d%s%d" % (a, DASH, b) if a != b else "%d" % a


def welcome(c, page, book, P):
    """Page 2: how the book works, how to print it, who may copy it."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    cw = W - 2 * M_SIDE
    by = {g["level"]: g for g in P["groups"]}
    if sorted(by) != ["easy", "hard", "medium"] or len(P["groups"]) != 3:
        raise AssertionError("the how-to page is written for one easy, one medium and one hard run of puzzles")
    e, m, h = by["easy"], by["medium"], by["hard"]
    answers = (P["first_answer"], P["first_answer"] + P["sheets"] - 1)
    other = PAPER["a4" if page == "letter" else "letter"]
    items = [
        ("p", "Here are %s %s in real large print, one to a page. They come in three levels: easy puzzles "
              "have the biggest letters and words that run across and down only, medium puzzles add diagonals, "
              "and hard puzzles run every way, backwards too." % (book["count_words"], book["kind"])),
        ("p", "Beside every word is a box to tick when you find it. Every answer is at the back, and the foot "
              "of each puzzle tells you which page."),
        ("h", "Printing"),
        ("p", "Print the whole book, or just the pages you want. The page numbers at the foot of the pages are "
              "the ones your print window uses. These are the pages for each part:"),
        ("table", [("Easy", _span(*e["pages"])), ("Medium", _span(*m["pages"])),
                   ("Hard", _span(*h["pages"])), ("Answers", _span(*answers))]),
        ("p", "Plain paper and black ink are all you need. Only the cover, page 1, is in color, so leave it "
              "out to save ink."),
        ("p", "This file is sized for %s paper. For %s paper, use the %s file that came with it. If the edges "
              "are cut off when you print, choose Fit in your print window." % (PAPER[page], other, other)),
        ("h", "Sharing"),
        ("p", "Print as many copies as you like for yourself, your family, your class, your library group or "
              "the people you care for. Please do not sell the puzzles or pass the file on."),
    ]
    y_title = H - M_TOP - 32
    _centre(c, W / 2, y_title, "Before you begin", "Fr", 32)
    _rule(c, W / 2, y_title - 13)
    start, floor = y_title - 13 - 34, M_BOT + 22
    for size in (18.0, 17.5, 17.0, 16.5, 16.0):
        if _flow(c, items, M_SIDE + 6, start, cw - 12, size, draw=False) >= floor:
            break
    else:
        raise AssertionError("the how-to page does not fit on %s" % page)
    _flow(c, items, M_SIDE + 6, start, cw - 12, size)
    footer(c, W, book["site"], "", "Page 2")
    c.showPage()
    return size


CONTENTS_PT = 16.0


def _group_head(c, W, yb, name, left, right):
    """A level's heading: its name, what its words do, and a note at the right."""
    c.setFillGray(0.0)
    c.setFont("Fr", 22)
    c.drawString(M_SIDE, yb, name)
    x = M_SIDE + stringWidth(name, "Fr", 22) + 12
    c.setFillGray(SOFT)
    c.setFont("Atk", CONTENTS_PT)
    c.drawString(x, yb, left)
    c.setFont("SpM", CONTENTS_PT + 1)
    c.drawRightString(W - M_SIDE, yb, right)
    if "0" in left or x + stringWidth(left, "Atk", CONTENTS_PT) + 16 > W - M_SIDE - stringWidth(right, "SpM", CONTENTS_PT + 1):
        raise AssertionError("the heading for %s does not fit: %r | %r" % (name, left, right))


def contents_page(c, page, book, P, chunks, page_no, k):
    """One page of the contents list: number, puzzle, page, in two columns."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    cw = W - 2 * M_SIDE
    y_title = H - M_TOP - 32
    _centre(c, W / 2, y_title, "Contents" if k == 0 else "Contents, continued", "Fr", 32)
    _rule(c, W / 2, y_title - 13)
    top, bottom = y_title - 13 - 12, M_BOT + 16
    HEAD, GAP = 58.0, 12.0
    rows = sum(-(-(ch["last"] - ch["first"] + 1) // 2) for ch in chunks)
    pitch = min(24.0, (top - bottom - HEAD * len(chunks) - GAP * (len(chunks) - 1)) / rows)
    if pitch < 20.5:
        raise AssertionError("contents rows would be only %.1f pt apart on %s" % (pitch, page))
    gut = 20.0
    col_w = (cw - gut) / 2.0
    num_w, page_w = 28.0, stringWidth(str(P["pages"]), NUM, CONTENTS_PT)
    y = top
    for ch in chunks:
        spec = ws.LEVELS[ch["level"]]
        yb = y - 27
        _group_head(c, W, yb, spec["label"] + (", continued" if ch["continued"] else ""), spec["short"],
                    "%d pt letters" % PROMISED[ch["level"]])
        yh = yb - 21
        count = ch["last"] - ch["first"] + 1
        n_rows = -(-count // 2)
        for col in range(2 if count > 1 else 1):
            x = M_SIDE + col * (col_w + gut)
            c.setFillGray(pdfs.GREY)
            c.setFont("AtkB", 11)
            c.drawRightString(x + num_w, yh, "NO.")
            c.drawString(x + num_w + 8, yh, "PUZZLE")
            c.drawRightString(x + col_w, yh, "PAGE")
            c.setStrokeGray(0.0)
            c.setLineWidth(1.0)
            c.line(x, yh - 6, x + col_w, yh - 6)
        y_rows = yh - 6
        for i in range(count):
            n = ch["first"] + i
            col, row = divmod(i, n_rows)
            x = M_SIDE + col * (col_w + gut)
            yr = y_rows - (row + 1) * pitch + 7.0
            title = book["puzzles"][n - 1]["title"]
            if "0" in title or stringWidth(title, "Atk", CONTENTS_PT) > col_w - num_w - 8 - page_w - 10:
                raise AssertionError("contents: %r does not suit its column on %s" % (title, page))
            c.setFillGray(0.0)
            c.setFont(NUM, CONTENTS_PT)
            c.drawRightString(x + num_w, yr, str(n))
            c.drawRightString(x + col_w, yr, str(puzzle_page_no(P, n)))
            c.setFont("Atk", CONTENTS_PT)
            c.drawString(x + num_w + 8, yr, title)
            c.setStrokeGray(0.82)
            c.setLineWidth(0.6)
            c.line(x, yr - 7.0, x + col_w, yr - 7.0)
            c.linkAbsolute("", "p%d" % n, Rect=(x, yr - 7.0, x + col_w, yr - 7.0 + pitch), thickness=0)
        y = y_rows - n_rows * pitch - GAP
    footer(c, W, book["site"], "", "Page %d" % page_no)
    c.showPage()
    return pitch


TRACK_PER_ROW = 10


def tracker_page(c, page, book, P):
    """A box for every puzzle, to tick as each is done. Each number leads to its puzzle."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    cw = W - 2 * M_SIDE
    y_title = H - M_TOP - 32
    _centre(c, W / 2, y_title, "Puzzle tracker", "Fr", 32)
    _rule(c, W / 2, y_title - 13)
    y = y_title - 13 - 36
    _centre(c, W / 2, y, "Tick each puzzle off when you have done it.", "Atk", 17)
    top, bottom = y - 16, M_BOT + 24
    HEAD, GAP = 46.0, 14.0
    groups = P["groups"]
    rows = sum(-(-(g["last"] - g["first"] + 1) // TRACK_PER_ROW) for g in groups)
    pitch = min(38.0, (top - bottom - HEAD * len(groups) - GAP * (len(groups) - 1)) / rows)
    if pitch < 26.0:
        raise AssertionError("the tracker does not fit on %s" % page)
    cell_w = cw / TRACK_PER_ROW
    size, box = 15.0, 15.0
    if stringWidth(str(P["total"]), NUM, size) + 5 + box > cell_w - 6:
        raise AssertionError("tracker cells are too narrow on %s" % page)
    y = top
    for g in groups:
        spec = ws.LEVELS[g["level"]]
        yb = y - 28
        _group_head(c, W, yb, spec["label"], spec["short"], "pages " + _span(*g["pages"]))
        y_rows = yb - (HEAD - 28) + 4
        count = g["last"] - g["first"] + 1
        for i in range(count):
            n = g["first"] + i
            row, col = divmod(i, TRACK_PER_ROW)
            x = M_SIDE + col * cell_w
            yr = y_rows - (row + 1) * pitch + (pitch - box) / 2.0 + 2.5
            c.setFillGray(0.0)
            c.setFont(NUM, size)
            c.drawRightString(x + cell_w - box - 11, yr, str(n))
            c.setStrokeGray(0.0)
            c.setLineWidth(1.0)
            c.rect(x + cell_w - box - 6, yr - 2.5, box, box, stroke=1, fill=0)
            c.linkAbsolute("", "p%d" % n, Rect=(x + 1, y_rows - (row + 1) * pitch, x + cell_w - 1, y_rows - row * pitch),
                           thickness=0)
        y = y_rows - (-(-count // TRACK_PER_ROW)) * pitch - GAP
    footer(c, W, book["site"], "", "Page %d" % P["tracker"])
    c.showPage()
    return pitch


def puzzle_page(c, page, book, P, n, puz, built):
    L = pdfs.layout(page, puz["level"], puz["words"])
    c.setPageSize((L["W"], L["H"]))
    pdfs._header(c, L, puz["title"], puz["note"], puz["level"], False)
    pdfs._grid(c, L, built["grid"], None)
    pdfs._wordlist(c, L, puz["words"])
    footer(c, L["W"], book["site"], "Puzzle %d of %d" % (n, P["total"]),
           "Page %d  %s  Answer on page %d" % (puzzle_page_no(P, n), DOT, answer_page_no(P, n)), dest="a%d" % n)
    c.showPage()
    return L


def answers_page(c, page, book, P, items, page_no):
    """Two answers to a page, still comfortably large. Each heading leads back to its puzzle."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    top, bottom = H - M_TOP, M_BOT + 18
    slot = (top - bottom) / 2.0
    smallest = None
    for k, (n, puz, built) in enumerate(items):
        size = ws.LEVELS[puz["level"]]["size"]
        y0 = top - k * slot
        head = "Answer %d: %s" % (n, puz["title"])
        fs = _fit(head, "Fr", 21, W - 2 * M_SIDE)
        _centre(c, W / 2, y0 - 20, head, "Fr", fs)
        hw = stringWidth(head, "Fr", fs)
        c.linkAbsolute("", "p%d" % n, Rect=(W / 2 - hw / 2, y0 - 26, W / 2 + hw / 2, y0 - 3), thickness=0)
        room = slot - 20 - 16 - 22
        cell = int(min(room, W - 2 * M_SIDE) / size * 2) / 2.0
        cell = min(cell, 27.0)
        letter = int(cell * 0.70)
        smallest = letter if smallest is None else min(smallest, letter)
        side = cell * size
        pdfs._grid(c, pdfs.mini((W - side) / 2.0, y0 - 36, size, cell, letter), built["grid"], built["placed"])
    footer(c, W, book["site"], "Answers", "Page %d" % page_no)
    c.showPage()
    return smallest


def closing(c, page, book, P):
    """The last page: where to find more, and what the book is made of."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    cw = W - 2 * M_SIDE
    y = H - M_TOP - 32
    _centre(c, W / 2, y, "More from Hearth & Clue", "Fr", 32)
    _rule(c, W / 2, y - 13)
    y -= 13 + 44
    size, lead = 17.0, 23.5
    x = M_SIDE + 6
    for text, link in (("A new word search every morning, free to play:", book["site"]),
                       ("Ten more large print %s, free to print:" % book["kind"], book["free"]),
                       ("More printable puzzle books:", book["shop"])):
        c.setFillGray(0.0)
        c.setFont("Atk", size)
        c.drawString(x, y, text)
        y -= lead + 2
        c.setFont("AtkB", size + 1)
        c.drawString(x, y, link)
        c.linkURL("https://" + link, (x, y - 5, x + stringWidth(link, "AtkB", size + 1), y + size), relative=0)
        y -= lead * 1.75
    y = _flow(c, [("p", "If you enjoyed this book, a short review on Etsy helps other puzzlers find it. Thank you.")],
              x, y, cw - 12, size)
    y -= 6
    grades = sorted({PROMISED[p["level"]] for p in book["puzzles"]}, reverse=True)
    sizes = ", ".join(str(g) for g in grades[:-1]) + " and %d" % grades[-1] if len(grades) > 1 else str(grades[0])
    y = _flow(c, [("h", "About this book"),
                  ("p", "Every grid was checked by computer after the pages were made: each listed word is in "
                        "its grid exactly once."),
                  ("p", "The puzzles are set in Atkinson Hyperlegible, a typeface designed for readers with low "
                        "vision. Grid letters are %s point. Word lists are %d point." % (sizes, WORD_PT)),
                  ("fine", "%s %d Hearth & Clue. %s, %s." % (COPY, book["year"], book["name"], book["edition"]))],
              x, y, cw - 12, size)
    if y < M_BOT + 22:
        raise AssertionError("the closing page does not fit on %s" % page)
    footer(c, W, book["site"], "", "Page %d" % P["closing"])
    c.showPage()


def write_pdf(path, page, book, P, built_all):
    fonts.register_book()
    cv = book["cover"]
    c = pdfs.new_canvas(path, "%s: %s" % (book["name"], cv["subtitle"]),
                        "%d large print %s with answers, %s." % (P["total"], book["kind"], PAPER[page]), book)
    c.setKeywords("large print, word search, printable, %s" % book["name"])
    c.setViewerPreference("DisplayDocTitle", "true")
    facts = {"paper": page}

    c.bookmarkPage("cover")
    c.addOutlineEntry("Cover", "cover", 0)
    cover(c, page, book)

    c.bookmarkPage("howto")
    c.addOutlineEntry("Before you begin", "howto", 0)
    facts["howto_pt"] = welcome(c, page, book, P)

    for k, chunks in enumerate(P["chunks"]):
        if k == 0:
            c.bookmarkPage("contents")
            c.addOutlineEntry("Contents", "contents", 0)
        facts["contents_pitch"] = contents_page(c, page, book, P, chunks, P["contents_first"] + k, k)

    c.bookmarkPage("tracker")
    c.addOutlineEntry("Puzzle tracker", "tracker", 0)
    facts["tracker_pitch"] = tracker_page(c, page, book, P)

    cells = {}
    for g in P["groups"]:
        spec = ws.LEVELS[g["level"]]
        for n in range(g["first"], g["last"] + 1):
            puz, built = book["puzzles"][n - 1], built_all[n - 1]
            c.bookmarkPage("p%d" % n)
            if n == g["first"]:
                # a bookmark's name is tied to one title, so the level's
                # entry needs a name of its own on the same page
                c.bookmarkPage("level%d" % n)
                c.addOutlineEntry("%s puzzles, %s" % (spec["label"], _span(g["first"], g["last"])), "level%d" % n, 0, closed=1)
            c.addOutlineEntry("%d. %s" % (n, puz["title"]), "p%d" % n, 1)
            L = puzzle_page(c, page, book, P, n, puz, built)
            cells.setdefault(g["level"], set()).add(L["cell"])
    facts["cells"] = {lev: sorted(v) for lev, v in cells.items()}

    items = [(n, p, b) for n, (p, b) in enumerate(zip(book["puzzles"], built_all, strict=True), 1)]
    smallest = None
    for k in range(P["sheets"]):
        sheet = items[k * 2:k * 2 + 2]
        for n, _, _ in sheet:
            c.bookmarkPage("a%d" % n)
        if k == 0:
            c.bookmarkPage("answers")
            c.addOutlineEntry("Answers", "answers", 0, closed=1)
        c.addOutlineEntry("Answers %s" % _span(sheet[0][0], sheet[-1][0]), "a%d" % sheet[0][0], 1)
        got = answers_page(c, page, book, P, sheet, P["first_answer"] + k)
        smallest = got if smallest is None else min(smallest, got)
    facts["smallest_answer_letter_pt"] = smallest

    c.bookmarkPage("more")
    c.addOutlineEntry("More from Hearth & Clue", "more", 0)
    closing(c, page, book, P)
    c.save()
    return facts


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(book_path, out_dir):
    book = load(book_path)
    P = plan(book)
    os.makedirs(out_dir, exist_ok=True)
    report = {"book": book["id"], "puzzles": P["total"], "pages": P["pages"], "checks": {}, "files": {},
              "plan": {"first_puzzle_page": P["first"], "first_answer_page": P["first_answer"],
                       "levels": [{"level": g["level"], "puzzles": [g["first"], g["last"]], "pages": list(g["pages"])}
                                  for g in P["groups"]]}}

    # 1. grids, each verified from scratch
    built, words = [], 0
    for puz in book["puzzles"]:
        b = ws.generate(puz["words"], puz["level"], "%s/%s" % (book["seed"], puz["slug"]))
        words += ws.verify(b["grid"], puz["words"], puz["level"], b["placed"])
        built.append(b)
    if words != sum(len(p["words"]) for p in book["puzzles"]) or words == 0:
        raise AssertionError("verified %d words" % words)
    report["checks"]["grid_words_verified"] = words

    # 2. one PDF for each paper size, read back and re-solved
    for page in ("letter", "a4"):
        name = "%s-%s.pdf" % (book["file"], FILE_TAG[page])
        path = os.path.join(out_dir, name)
        facts = write_pdf(path, page, book, P, built)
        r = qc_pdf.check_book(path, book, built, P, PROMISED, WORD_PT)
        if r["puzzles"] != P["total"] or r["answers"] != P["total"] or r["words_checked"] != words:
            raise AssertionError("book check incomplete for %s: %s" % (path, r))
        report["checks"][page] = dict(r, **facts)
        report["files"][name] = {"sha256": sha(path), "bytes": os.path.getsize(path)}
    json.dump(report, open(os.path.join(out_dir, "build.json"), "w"), indent=1)
    open(os.path.join(out_dir, "build.json"), "a").write("\n")
    print("built %s: %d puzzles, %d pages, %d words checked in each of %d files"
          % (book["id"], P["total"], P["pages"], words, len(report["files"])))
    return report


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
