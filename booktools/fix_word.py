#!/usr/bin/env python3
"""Replace a word that was placed into a grid with digits in it.

Usage: python booktools/fix_word.py <in.pdf> <out.pdf> <OLD> <NEW>
Example: fix_word.py book.pdf fixed/book.pdf SINCE1987 PAPERWORK
Needs: pip install pypdf pdfplumber reportlab

THE BUG: the generator placed strings like SINCE1987 / SINCE1994 straight into
the grid, digits and all. House rule is A-Z only. Because digits are not alpha,
these pages fail the QC grid detection, which shows up as "54 puzzle pages but
footers say 55".

The replacement MUST be the same length as the original. This rewrites the
cells on both the puzzle page and its solution page, updates the printed clue,
and re-sorts the clue list alphabetically.

SAFETY: it aborts unless the word has exactly one placement on each page. It
does NOT check whether the cells are shared with a crossing word — check that
first (see the crossing check below) or you will silently break another word.

GOTCHAS learned the hard way:
  - grid font size differs per book (17pt word search, 16pt mystery), so detect
    it rather than hardcoding
  - a draw op must be matched on BOTH x and y: a column shares x, a row shares y
  - the Tm y sits about 3.5pt above pdfplumber's y0 (descender), so allow ~8pt
  - pypdf get_contents() returns a detached copy; use page.replace_contents()

AFTER RUNNING: re-run qc_book.py and render both changed pages and LOOK.
"""
import collections, os, re, sys
import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject
from reportlab.pdfbase import pdfmetrics

DIRS = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1)]
FONT = "Helvetica-Bold"


def read_table(page):
    """Return the grid as rows of pdfplumber char dicts, plus the font size."""
    sizes = collections.Counter(round(c["size"],1) for c in page.chars
                                if len(c["text"].strip())==1 and c["text"].strip().isalpha())
    if not sizes:
        return None, None
    gsize = max(sizes, key=lambda s: (sizes[s], s))
    rows = collections.defaultdict(list)
    for c in page.chars:
        if round(c["size"],1)==gsize and c["text"].strip():
            rows[round(c["top"],0)].append(c)
    table = [sorted(rows[y], key=lambda c: c["x0"]) for y in sorted(rows)]
    table = [r for r in table if len(r) >= 10]
    return table, gsize


def locate(grid, word):
    N = len(grid)
    hits = []
    for y in range(N):
        for x in range(len(grid[y])):
            for dx, dy in DIRS:
                if all(0 <= y+dy*i < N and 0 <= x+dx*i < len(grid[y+dy*i])
                       and grid[y+dy*i][x+dx*i] == word[i] for i in range(len(word))):
                    hits.append([(y+dy*i, x+dx*i) for i in range(len(word))])
    return hits


def clue_words(page):
    text = page.extract_text() or ""
    for header in ("FIND THESE WORDS:", "CLUES TO FIND:"):
        if header in text:
            tail = re.split(r"(Puzzle|Solution|Chapter)\s+\d+\s+of\s+\d+",
                            text.split(header,1)[1])[0]
            return re.findall(r"[A-Z0-9]{2,}", tail)
    return []


def crossing_check(table, coords, all_words):
    """Warn if any target cell also belongs to another word."""
    grid = [[c["text"].upper() for c in r] for r in table]
    used = collections.Counter()
    for w in all_words:
        hits = locate(grid, w)
        if hits:
            for cell in hits[0]:
                used[cell] += 1
    shared = [c for c in coords if used[c] > 1]
    return shared


def main():
    src, dest, old, new = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    if len(old) != len(new):
        sys.exit(f"replacement must be the same length: {old} is {len(old)}, {new} is {len(new)}")
    if not re.fullmatch(r"[A-Z]+", new):
        sys.exit("replacement must be A-Z only")

    num = None
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            if old in clue_words(page):
                m = re.search(r"(Puzzle|Solution)\s+(\d+)\s+of", page.extract_text() or "")
                if m:
                    num = m.group(2)
                    break
    if num is None:
        sys.exit(f"{old} not found in any clue list")
    print(f"{os.path.basename(src)}: {old} -> {new} on puzzle {num}")

    pages = {}
    with pdfplumber.open(src) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            m = re.search(r"(Puzzle|Solution)\s+(\d+)\s+of", text)
            if not m or m.group(2) != num:
                continue
            table, gsize = read_table(page)
            grid = [[c["text"].upper() for c in r] for r in table]
            hits = locate(grid, old)
            if len(hits) != 1:
                sys.exit(f"p{i+1}: expected one placement of {old}, found {len(hits)}")
            words = [w for w in clue_words(page) if w != old]
            shared = crossing_check(table, hits[0], words)
            if shared:
                sys.exit(f"p{i+1}: ABORT — cells {shared} are shared with another word")
            pages[i] = (table, hits[0], gsize)
            print(f"  p{i+1} ({m.group(1)}): cells {hits[0][0]}..{hits[0][-1]}, no crossings")

    if len(pages) != 2:
        sys.exit(f"expected a puzzle page and a solution page, found {len(pages)}")

    reader = PdfReader(src)
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in pages:
            table, coords, gsize = pages[i]
            data = page.get_contents().get_data().decode("latin-1")
            for (ry, rx), ch in zip(coords, new):
                cell = table[ry][rx]
                old_ch = cell["text"]
                if old_ch == ch:
                    continue
                centre = (cell["x0"] + cell["x1"]) / 2.0
                x_new = centre - pdfmetrics.stringWidth(ch, FONT, gsize)/2.0
                # match on BOTH coordinates — a column shares x, a row shares y
                cand = []
                for m2 in re.finditer(r"BT 1 0 0 1 ([\d.]+) ([\d.]+) Tm \(" +
                                      re.escape(old_ch) + r"\) Tj T\* ET", data):
                    if (abs(float(m2.group(1)) - cell["x0"]) < 0.06
                            and abs(float(m2.group(2)) - cell["y0"]) < 8.0):
                        cand.append(m2)
                if len(cand) != 1:
                    sys.exit(f"p{i+1}: cell ({ry},{rx}) '{old_ch}' matched {len(cand)} draw ops")
                mm = cand[0]
                new_op = f"BT 1 0 0 1 {x_new:.3f} {mm.group(2)} Tm ({ch}) Tj T* ET"
                data = data[:mm.start()] + new_op + data[mm.end():]

            if f"( {old})" in data:
                data = data.replace(f"( {old})", f"( {new})")
                pat = re.compile(r"(BT 1 0 0 1 [\d.]+ [\d.]+ Tm /F4 [\d.]+ Tf [\d.]+ TL \(n\) Tj "
                                 r"/F1 [\d.]+ Tf [\d.]+ TL \( )([A-Z]+)(\) Tj T\* ET)")
                ms = list(pat.finditer(data))
                words = [m.group(2) for m in ms]
                ordered = sorted(words)
                if words != ordered:
                    for m, w in reversed(list(zip(ms, ordered))):
                        data = data[:m.start()] + m.group(1) + w + m.group(3) + data[m.end():]
                    print(f"  p{i+1}: clue list resorted")
            s = DecodedStreamObject()
            s.set_data(data.encode("latin-1"))
            page.replace_contents(s)
        writer.add_page(page)

    if os.path.dirname(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        writer.write(f)
    print("written:", dest)


if __name__ == "__main__":
    main()
