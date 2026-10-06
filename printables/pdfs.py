"""PDF pages for the printable packs: one puzzle per page, real large print.

Sizes are not guesses. layout() works the grid out from the page and refuses
to build if the letters would fall below the size promised for the level, so
"28 pt" on the website is a measured fact about the file.
"""
import calendar
import os
import time

import reportlab.rl_config as rl_config
rl_config.invariant = 1  # same input, same bytes: nothing in the files depends on the build day
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

import fonts
import ws
from wording import mid_sentence

PAGES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
PAPER = {"letter": "US Letter", "a4": "A4"}
M_SIDE, M_TOP, M_BOT = 40.0, 34.0, 30.0
PROMISED = {"easy": 28, "medium": 24, "hard": 22}   # grid letters, in points
WORD_PT = 18.0                                      # word list, in points
GREY, BAND, EDGE = 0.36, 0.86, 0.45
SITE = "hearthandclue.com"
DOT = chr(8226)     # bullet. Never chr(127): reportlab draws that as a filled square
COPY = chr(169)     # copyright sign


def _centre(c, x, y, text, font, size, grey=0.0, tracking=0.0):
    c.setFillGray(grey)
    if tracking:
        w = stringWidth(text, font, size) + tracking * (len(text) - 1)
        t = c.beginText(x - w / 2.0, y)
        t.setFont(font, size)
        t.setCharSpace(tracking)
        t.textOut(text)
        t.setCharSpace(0)   # spacing is sticky in a PDF: put it back
        c.drawText(t)
    else:
        c.setFont(font, size)
        c.drawCentredString(x, y, text)


def _fit(text, font, size, width):
    while stringWidth(text, font, size) > width and size > 8:
        size -= 0.5
    return size


def layout(page, level, words):
    """All the measurements for one puzzle page, top to bottom."""
    W, H = PAGES[page]
    n = ws.LEVELS[level]["size"]
    cw = W - 2 * M_SIDE
    L = {"W": W, "H": H, "n": n, "cw": cw}
    y = H - M_TOP
    L["y_title"] = y - 24
    L["y_rule"] = L["y_title"] - 11
    L["y_note"] = L["y_rule"] - 22
    L["y_level"] = L["y_note"] - 21
    grid_top = L["y_level"] - 13

    # word list: as many columns as the longest word allows, fewest rows
    longest = max(stringWidth(w, "Atk", WORD_PT) for w in words)
    box = 12.0
    need = box + 8 + longest + 10
    cols = max(1, min(4, int(cw // need)))
    rows = -(-len(words) // cols)
    row_h = WORD_PT + 6.5
    L.update(cols=cols, rows=rows, row_h=row_h, box=box, col_w=cw / cols)
    L["y_foot"] = M_BOT - 6
    list_bottom = L["y_foot"] + 20
    L["y_words_top"] = list_bottom + rows * row_h
    L["y_find"] = L["y_words_top"] + 8
    grid_bottom_min = L["y_find"] + 12 + 14

    # The letter size is fixed by the level; the page decides how much air
    # each letter gets. Too little room for the promised size stops the build.
    letter = PROMISED[level]
    avail = min(cw, grid_top - grid_bottom_min)
    cell = int(avail / n * 2) / 2.0
    cell = min(cell, int(letter / 0.66 * 2) / 2.0)
    if cell < letter / 0.76:
        raise AssertionError("%s on %s: only %.1f pt per cell, too tight for %d pt letters"
                             % (level, page, cell, letter))
    side = cell * n
    # centre the grid in the space it has
    slack = (grid_top - grid_bottom_min) - side
    L.update(cell=cell, letter=float(letter), side=side,
             gx=(W - side) / 2.0, gy_top=grid_top - slack / 2.0)
    return L


def _cell_xy(L, r, c):
    return (L["gx"] + (c + 0.5) * L["cell"], L["gy_top"] - (r + 0.5) * L["cell"])


def mini(gx, gy_top, n, cell, letter):
    """A layout holding only what _grid needs, for grids drawn at any size."""
    return {"n": n, "cell": cell, "letter": float(letter), "side": cell * n, "gx": gx, "gy_top": gy_top}


def _header(c, L, title, note, level, solution):
    spec = ws.LEVELS[level]
    W = L["W"]
    head = ("Answer: " + title) if solution else title
    size = _fit(head, "Fr", 30, L["cw"])
    _centre(c, W / 2, L["y_title"], head, "Fr", size)
    c.setStrokeGray(EDGE)
    c.setLineWidth(0.8)
    for dy in (0, 3.2):
        c.line(W / 2 - 34, L["y_rule"] + dy, W / 2 + 34, L["y_rule"] + dy)
    line2 = "Every word is ringed below." if solution else note
    _centre(c, W / 2, L["y_note"], line2, "Atk", _fit(line2, "Atk", 17, L["cw"]))
    lev = "%s  %s  %s" % (spec["label"].upper(), DOT, spec["rule"])
    _centre(c, W / 2, L["y_level"], lev, "AtkB", _fit(lev, "AtkB", 13, L["cw"]), grey=0.2)


def _grid(c, L, rows, placed=None):
    n, cell = L["n"], L["cell"]
    x0, ytop, side = L["gx"], L["gy_top"], L["side"]
    if placed:
        c.setLineCap(1)
        half = cell * 0.36
        segs = []
        for w, (r, cc, dr, dc) in sorted(placed.items()):
            a = _cell_xy(L, r, cc)
            b = _cell_xy(L, r + dr * (len(w) - 1), cc + dc * (len(w) - 1))
            segs.append((a, b))
        c.setStrokeGray(EDGE)
        c.setLineWidth(2 * half + 1.8)
        for a, b in segs:
            c.line(a[0], a[1], b[0], b[1])
        c.setStrokeGray(BAND)
        c.setLineWidth(2 * half)
        for a, b in segs:
            c.line(a[0], a[1], b[0], b[1])
        c.setLineCap(0)
    c.setStrokeGray(0.0)
    c.setLineWidth(1.3 if cell > 24 else 1.0)
    pad = 5.0 if cell > 24 else 3.5
    c.roundRect(x0 - pad, ytop - side - pad, side + 2 * pad, side + 2 * pad, 9 if cell > 24 else 6, stroke=1, fill=0)
    c.setFillGray(0.0)
    c.setFont("AtkB", L["letter"])
    drop = L["letter"] * 0.668 / 2.0     # half the cap height: centres the capitals
    for r in range(n):
        for col in range(n):
            x, y = _cell_xy(L, r, col)
            c.drawCentredString(x, y - drop, rows[r][col])


def _wordlist(c, L, words, done=False):
    W = L["W"]
    _centre(c, W / 2, L["y_find"], "WORDS FOUND" if done else "FIND THESE WORDS", "AtkB", 12.5, grey=GREY, tracking=1.6)
    words = sorted(words)
    cols, rows, row_h, box = L["cols"], L["rows"], L["row_h"], L["box"]
    widest = max(stringWidth(w, "Atk", WORD_PT) for w in words)
    block = box + 8 + widest
    for i, w in enumerate(words):
        col, row = divmod(i, rows)
        x = M_SIDE + col * L["col_w"] + (L["col_w"] - block) / 2.0
        y = L["y_words_top"] - (row + 1) * row_h + 7
        c.setStrokeGray(0.0)
        c.setLineWidth(1.0)
        c.rect(x, y - 0.5, box, box, stroke=1, fill=0)
        if done:
            c.setLineWidth(1.6)
            c.line(x + 2.6, y + 5.6, x + 5.2, y + 2.6)
            c.line(x + 5.2, y + 2.6, x + 10.2, y + 9.8)
        c.setFillGray(0.0)
        c.setFont("Atk", WORD_PT)
        c.drawString(x + box + 8, y, w)


def _footer(c, W, y, left, mid, right):
    size = 9.5
    lw, mw, rw = (stringWidth(t, "Atk", size) for t in (left, mid, right))
    if M_SIDE + lw + 14 > W / 2 - mw / 2 or W / 2 + mw / 2 + 14 > W - M_SIDE - rw:
        raise AssertionError("footer text collides: %r | %r | %r" % (left, mid, right))
    c.setFillGray(GREY)
    c.setFont("Atk", size)
    c.drawString(M_SIDE, y, left)
    c.drawCentredString(W / 2, y, mid)
    c.drawRightString(W - M_SIDE, y, right)
    c.linkURL("https://" + left, (M_SIDE, y - 3, M_SIDE + lw, y + 9), relative=0)


def puzzle_page(c, page, puz, built, index, total, link, right, solution=False):
    L = layout(page, puz["level"], puz["words"])
    c.setPageSize((L["W"], L["H"]))
    _header(c, L, puz["title"], puz["note"], puz["level"], solution)
    _grid(c, L, built["grid"], built["placed"] if solution else None)
    _wordlist(c, L, puz["words"], done=solution)
    _footer(c, L["W"], L["y_foot"], link, "%s %d of %d" % ("Answer" if solution else "Puzzle", index, total), right)
    c.showPage()
    return L


def new_canvas(path, title, subject, pack):
    fonts.register_pdf()
    # Date the file with the day the pack was released (noon UTC, so it reads
    # as that day everywhere), not the day it happened to be built. reportlab
    # takes its clock from SOURCE_DATE_EPOCH when that is set.
    stamp = calendar.timegm(time.strptime(pack["released"], "%Y-%m-%d")) + 12 * 3600
    before = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(stamp)
    try:
        # Start in one of our own embedded fonts. Left to itself the library
        # starts every page in Helvetica, which it names but does not embed.
        c = canvas.Canvas(path, pageCompression=1, initialFontName="Atk", lang="en")
    finally:
        if before is None:
            del os.environ["SOURCE_DATE_EPOCH"]
        else:
            os.environ["SOURCE_DATE_EPOCH"] = before
    c.setTitle(title)
    c.setAuthor("Hearth & Clue")
    c.setSubject(subject)
    c.setCreator("hearthandclue.com")
    return c


def single(path, page, pack, puz, built, index, total):
    """Two pages: the puzzle, then its full-size answer."""
    link = "%s/%s" % (SITE, pack["slug"])
    c = new_canvas(path, "%s - free large print word search" % puz["title"],
                   "%s. %s level, %s." % (puz["search"], ws.LEVELS[puz["level"]]["label"], PAPER[page]), pack)
    L = puzzle_page(c, page, puz, built, index, total, link, "Answer on the next page")
    puzzle_page(c, page, puz, built, index, total, link, COPY + " %d Hearth & Clue" % pack["year"], solution=True)
    c.save()
    return L


def _para(c, x, y, text, font, size, width, leading=None, grey=0.0):
    """Left-aligned wrapped text. Returns the y of the line after the last one."""
    leading = leading or size * 1.32
    c.setFillGray(grey)
    c.setFont(font, size)
    line = ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if stringWidth(trial, font, size) > width and line:
            c.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


COVER_SIZES = [(30.5, 17.5, 24.5, 42), (29.0, 17.0, 23.5, 40), (27.5, 16.5, 22.5, 36),
               (26.5, 16.0, 21.5, 34), (25.5, 16.0, 21.0, 32), (24.5, 15.5, 20.5, 30)]
COVER_BOX_H = 56.0


def _cover(c, page, pack, first_answer_page):
    """Page 1 of the pack. Uses the largest text that fits the paper."""
    import io
    floor = M_BOT + 16 + COVER_BOX_H + 6
    for sizes in COVER_SIZES:
        scratch = canvas.Canvas(io.BytesIO())
        if _cover_body(scratch, page, pack, first_answer_page, sizes) >= floor:
            break
    else:
        raise AssertionError("cover does not fit on %s at any size" % page)
    y = _cover_body(c, page, pack, first_answer_page, sizes)
    W = PAGES[page][0]
    cw = W - 2 * M_SIDE
    # the plug: no puzzle count here, so the page never goes out of date
    link = "%s/%s" % (SITE, pack["slug"])
    box_y = M_BOT + 16
    # sit the box midway between the text and the footer when there is room
    box_y += max(0.0, (y - floor) / 2.0)
    # a pack may say something else here, and send people somewhere else
    plug = pack.get("plug") or {}
    plug_text = plug.get("text", "Liked these? There is a whole book of them.")
    plug_link = plug.get("link", link)
    c.setStrokeGray(0.0)
    c.setLineWidth(1.2)
    c.roundRect(M_SIDE, box_y, cw, COVER_BOX_H, 9, stroke=1, fill=0)
    _centre(c, W / 2, box_y + 34, plug_text, "Fr", _fit(plug_text, "Fr", 18, cw - 24))
    _centre(c, W / 2, box_y + 12, plug_link, "AtkB", 15)
    c.linkURL("https://" + plug_link, (M_SIDE, box_y, M_SIDE + cw, box_y + COVER_BOX_H), relative=0)
    _footer(c, W, M_BOT - 6, link, "Page 1", COPY + " %d Hearth & Clue" % pack["year"])
    c.showPage()


def _cover_body(c, page, pack, first_answer_page, sizes):
    """Draw the cover text; return the y just below the last line."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    cw = W - 2 * M_SIDE
    total = len(pack["puzzles"])
    row, body, lead, gap = sizes
    y = H - M_TOP - 6
    _centre(c, W / 2, y, "HEARTH & CLUE", "AtkB", 11, grey=GREY, tracking=3.0)
    y -= 46
    head = "%d %s" % (total, pack["name"])
    _centre(c, W / 2, y, head, "Fr", _fit(head, "Fr", 38, cw))
    c.setStrokeGray(EDGE)
    c.setLineWidth(0.8)
    for dy in (0, 3.2):
        c.line(W / 2 - 40, y - 14 + dy, W / 2 + 40, y - 14 + dy)
    y -= 42
    _centre(c, W / 2, y, "Large print. Three levels. Answers included.", "Atk", 18)

    # contents
    y -= gap
    c.setFillGray(GREY)
    c.setFont("AtkB", 11)
    cols = (M_SIDE + 4, M_SIDE + 44, M_SIDE + cw * 0.60, W - M_SIDE - 4)
    for x, text, right in ((cols[0], "NO.", 0), (cols[1], "PUZZLE", 0), (cols[2], "LEVEL", 0), (cols[3], "LETTERS", 1)):
        (c.drawRightString if right else c.drawString)(x, y, text)
    c.setStrokeGray(0.0)
    c.setLineWidth(1.0)
    c.line(M_SIDE, y - 7, W - M_SIDE, y - 7)
    y -= row + 1
    for i, p in enumerate(pack["puzzles"], 1):
        c.setFillGray(0.0)
        c.setFont("Fr", 17)             # Fraunces numerals: Atkinson's zero is slashed
        c.drawString(cols[0], y, str(i))
        c.setFont("Atk", 18)
        c.drawString(cols[1], y, p["title"])
        c.drawString(cols[2], y, ws.LEVELS[p["level"]]["label"])
        c.drawRightString(cols[3], y, "%d pt" % PROMISED[p["level"]])
        c.setStrokeGray(0.82)
        c.setLineWidth(0.6)
        c.line(M_SIDE, y - 9, W - M_SIDE, y - 9)
        y -= row

    # how the levels work
    y -= 8
    for level in ("easy", "medium", "hard"):
        spec = ws.LEVELS[level]
        c.setFillGray(0.0)
        c.setFont("AtkB", body)
        c.drawString(M_SIDE + 4, y, spec["label"])
        y = _para(c, M_SIDE + 92, y, spec["rule"], "Atk", body, cw - 96, leading=lead) - 2

    y -= 8
    y = _para(c, M_SIDE + 4, y,
              "Set in Atkinson Hyperlegible, a typeface made for readers with low vision. "
              "Word lists are %d point. Each grid was checked by computer: every word is "
              "there exactly once. Answers start on page %d." % (WORD_PT, first_answer_page),
              "Atk", body, cw - 8, leading=lead)
    y -= 6
    y = _para(c, M_SIDE + 4, y,
              "Free to print and copy for home, classroom, library and care-home use. "
              "Please do not sell them.", "AtkB", body, cw - 8, leading=lead)

    return y


def _answers_page(c, page, pack, items, link, page_no, pages):
    """Two answers to a page, still comfortably large."""
    W, H = PAGES[page]
    c.setPageSize((W, H))
    top, bottom = H - M_TOP, M_BOT + 16
    slot = (top - bottom) / 2.0
    for k, (index, puz, built) in enumerate(items):
        n = ws.LEVELS[puz["level"]]["size"]
        y0 = top - k * slot
        head = "Answer %d: %s" % (index, puz["title"])
        _centre(c, W / 2, y0 - 20, head, "Fr", _fit(head, "Fr", 21, W - 2 * M_SIDE))
        room = slot - 20 - 16 - 22
        cell = int(min(room, W - 2 * M_SIDE) / n * 2) / 2.0
        cell = min(cell, 27.0)
        letter = int(cell * 0.70)
        side = cell * n
        _grid(c, mini((W - side) / 2.0, y0 - 36, n, cell, letter), built["grid"], built["placed"])
    _footer(c, W, M_BOT - 6, link, "Answers, page %d of %d" % (page_no, pages), COPY + " %d Hearth & Clue" % pack["year"])
    c.showPage()


def pack_pdf(path, page, pack, built_all):
    """Cover, every puzzle, then the answers two to a page."""
    total = len(pack["puzzles"])
    link = "%s/%s" % (SITE, pack["slug"])
    c = new_canvas(path, "%d %s - free large print printable" % (total, pack["name"]),
                   "Free large print %s, %s, with answer keys." % (mid_sentence(pack["name"]), PAPER[page]), pack)
    first_answer = 1 + total + 1
    _cover(c, page, pack, first_answer)
    for i, (puz, built) in enumerate(zip(pack["puzzles"], built_all), 1):
        puzzle_page(c, page, puz, built, i, total, link, "Answers start on page %d" % first_answer)
    items = [(i, p, b) for i, (p, b) in enumerate(zip(pack["puzzles"], built_all), 1)]
    sheets = [items[k:k + 2] for k in range(0, total, 2)]
    for k, sheet in enumerate(sheets, 1):
        _answers_page(c, page, pack, sheet, link, k, len(sheets))
    c.save()
    return 1 + total + len(sheets)
