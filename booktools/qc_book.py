#!/usr/bin/env python3
"""QC a Hearth & Clue word search book.

Usage: python booktools/qc_book.py book1.pdf book2.pdf ...
Needs: pip install pdfplumber

Checks: every clue word is actually present in its grid, grids are square,
every solution grid matches its puzzle grid, footers are consistent, words are
A-Z only and under 16 characters, no duplicates within a puzzle.

Parses by CHARACTER GEOMETRY, not extracted text lines. pdfplumber wraps long
grid rows, which on the first attempt silently produced ragged-grid false
positives and empty word lists — it reported books CLEAN while checking zero
words. If this script ever prints "0 words checked", the parser is broken, not
the book.

A grid containing DIGITS also fails the square test (digits are not alpha), so
a book reporting "N puzzle pages but footers say N+1" usually means a word with
digits was placed in a grid. Find it with the digit scan at the bottom.
"""
import re, sys, collections
import pdfplumber

DIRS = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1)]


def page_data(page):
    """Find the grid by geometry: the character size that yields a square block."""
    chars = [c for c in page.chars
             if len(c["text"].strip()) == 1 and c["text"].strip().isalpha()]
    if not chars:
        return None

    by_size = collections.defaultdict(list)
    for c in chars:
        by_size[round(c["size"], 1)].append(c)

    grid = []
    for size in sorted(by_size, reverse=True):
        rows = collections.defaultdict(list)
        for c in by_size[size]:
            rows[round(c["top"], 0)].append(c)
        candidate = []
        for y in sorted(rows):
            line = sorted(rows[y], key=lambda c: c["x0"])
            if len(line) >= 10:
                candidate.append([c["text"].upper() for c in line])
        widths = {len(r) for r in candidate}
        if candidate and len(widths) == 1 and len(candidate) == list(widths)[0] >= 10:
            grid = candidate
            break

    text = page.extract_text() or ""

    words = []
    for header in ("FIND THESE WORDS:", "CLUES TO FIND:"):
        if header in text:
            tail = text.split(header, 1)[1]
            # strip the footer line so the book title cannot leak in as a word
            tail = re.split(r"(Puzzle|Solution|Chapter)\s+\d+\s+of\s+\d+", tail)[0]
            words = re.findall(r"[A-Z]{2,}", tail)
            break

    m = re.search(r"(Puzzle|Solution|Chapter)\s+(\d+)\s+of\s+(\d+)", text)
    footer = (m.group(1), int(m.group(2)), int(m.group(3))) if m else None
    return {"grid": grid, "words": words, "footer": footer, "raw": text}


def findable(grid, word):
    h = len(grid)
    if not h:
        return False
    for y in range(h):
        for x in range(len(grid[y])):
            for dx, dy in DIRS:
                ok = True
                for i, ch in enumerate(word):
                    nx, ny = x + dx*i, y + dy*i
                    if not (0 <= ny < h) or not (0 <= nx < len(grid[ny])) or grid[ny][nx] != ch:
                        ok = False
                        break
                if ok:
                    return True
    return False


def digit_scan(path):
    """Report any grid holding digits. Page 3 always hits — that is the Contents."""
    out = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            sizes = collections.Counter(round(c["size"],1) for c in page.chars
                                        if len(c["text"].strip())==1 and c["text"].strip().isalpha())
            if not sizes:
                continue
            gsize = max(sizes, key=lambda s: (sizes[s], s))
            d = [c["text"] for c in page.chars
                 if round(c["size"],1)==gsize and c["text"].strip().isdigit()]
            if d and i != 2:
                out.append((i+1, "".join(d)))
    return out


def qc(path):
    problems = []
    puzzles, solutions = {}, {}
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            d = page_data(page)
            if not d or not d["grid"] or not d["footer"]:
                continue
            kind, n, total = d["footer"]
            d["page"] = i + 1
            d["total"] = total
            (solutions if kind == "Solution" else puzzles)[n] = d

    totals = {d["total"] for d in list(puzzles.values()) + list(solutions.values())}
    expected = max(totals) if totals else 0
    if len(totals) > 1:
        problems.append(f"inconsistent 'of N' footers across pages: {sorted(totals)}")
    if len(puzzles) != expected:
        problems.append(f"{len(puzzles)} puzzle pages but footers say {expected}")
    if len(solutions) != expected:
        problems.append(f"{len(solutions)} solution pages but expected {expected}")

    for n in sorted(puzzles):
        p = puzzles[n]
        widths = {len(r) for r in p["grid"]}
        if len(widths) != 1:
            problems.append(f"puzzle {n} (p{p['page']}): ragged grid {sorted(widths)}")
        elif len(p["grid"]) != list(widths)[0]:
            problems.append(f"puzzle {n} (p{p['page']}): {len(p['grid'])}x{list(widths)[0]} not square")
        if not p["words"]:
            problems.append(f"puzzle {n} (p{p['page']}): NO WORD LIST PARSED")

    checked = 0
    for n in sorted(puzzles):
        p = puzzles[n]
        seen = set()
        for w in p["words"]:
            checked += 1
            if not re.fullmatch(r"[A-Z]+", w):
                problems.append(f"puzzle {n} (p{p['page']}): non A-Z word {w!r}")
                continue
            if len(w) > 15:
                problems.append(f"puzzle {n} (p{p['page']}): {w} is {len(w)} chars (max 15)")
            if w in seen:
                problems.append(f"puzzle {n} (p{p['page']}): duplicate word {w}")
            seen.add(w)
            if not findable(p["grid"], w):
                problems.append(f"puzzle {n} (p{p['page']}): WORD NOT IN GRID: {w}")

    for n in sorted(solutions):
        s = solutions[n]
        p = puzzles.get(n)
        if not p:
            problems.append(f"solution {n} (p{s['page']}) has no matching puzzle")
        elif s["grid"] != p["grid"]:
            problems.append(f"solution {n} (p{s['page']}) grid differs from puzzle {n} (p{p['page']})")

    return expected, len(puzzles), checked, problems


if __name__ == "__main__":
    for path in sys.argv[1:]:
        name = path.split("/")[-1]
        expected, found, checked, problems = qc(path)
        print("=" * 72)
        print(f"{name}  —  {found} puzzles, {checked} words checked")
        if checked == 0:
            print("  WARNING: zero words checked — the parser failed, do NOT trust this result")
        digits = digit_scan(path)
        if digits:
            print(f"  DIGITS IN GRID on pages: {digits}")
        if problems:
            print(f"  {len(problems)} PROBLEM(S):")
            for p in problems[:50]:
                print("   -", p)
            if len(problems) > 50:
                print(f"   ... and {len(problems)-50} more")
        elif not digits:
            print("  CLEAN")
