"""Check a finished PDF against the puzzle it is meant to show.

Reads the PDF back with pdfplumber and trusts nothing the builder said:

  * the grid is rebuilt from the position of every letter on the page (never
    from extracted text lines - long grid rows get wrapped and a text-based
    check once reported books clean while checking zero words);
  * the letter and word-list sizes are measured from the file;
  * on an answer page every grey band is followed from end to end and must
    spell a listed word, and every listed word must have a band.

Each function returns counts so the caller can refuse a check that checked nothing.
"""
import pdfplumber

import ws


def _rows(chars, n):
    """Group grid letters into n rows of n by where they sit on the page."""
    chars = sorted(chars, key=lambda ch: ((ch["top"] + ch["bottom"]) / 2.0, ch["x0"]))
    if len(chars) != n * n:
        raise AssertionError("expected %d grid letters, found %d" % (n * n, len(chars)))
    rows = [chars[i * n:(i + 1) * n] for i in range(n)]
    for row in rows:
        ys = [(ch["top"] + ch["bottom"]) / 2.0 for ch in row]
        if max(ys) - min(ys) > 2.0:
            raise AssertionError("grid letters are not on straight rows")
        row.sort(key=lambda ch: (ch["x0"] + ch["x1"]) / 2.0)
    return rows


def read_page(page, level):
    """Return what is really on a puzzle or answer page."""
    n = ws.LEVELS[level]["size"]
    chars = page.chars
    bold = [ch for ch in chars if "Atkinson" in ch["fontname"] and "Bold" in ch["fontname"]]
    sizes = sorted({round(ch["size"], 1) for ch in bold})
    grid_size = max(sizes)
    grid_chars = [ch for ch in bold if round(ch["size"], 1) == grid_size]
    rows = _rows(grid_chars, n)
    grid = ["".join(ch["text"] for ch in row) for row in rows]
    centres = [[((ch["x0"] + ch["x1"]) / 2.0, (ch["top"] + ch["bottom"]) / 2.0) for ch in row] for row in rows]

    # word list: regular-weight letters at the list size, split on gaps
    reg = [ch for ch in chars if "Atkinson" in ch["fontname"] and "Regular" in ch["fontname"]]
    list_size = max(round(ch["size"], 1) for ch in reg)
    lst = sorted([ch for ch in reg if round(ch["size"], 1) == list_size and ch["text"].strip()],
                 key=lambda ch: (round(ch["top"]), ch["x0"]))
    words, cur, last = [], "", None
    for ch in lst:
        if last is not None and (round(ch["top"]) != round(last["top"]) or ch["x0"] - last["x1"] > list_size * 0.5):
            words.append(cur)
            cur = ""
        cur += ch["text"]
        last = ch
    if cur:
        words.append(cur)
    title = "".join(ch["text"] for ch in sorted(
        [ch for ch in chars if "Fraunces" in ch["fontname"]], key=lambda ch: (round(ch["top"]), ch["x0"])))
    return {"grid": grid, "centres": centres, "grid_pt": grid_size, "list_pt": list_size,
            "words": words, "title": title, "n": n}


def _nearest(centres, x, y):
    best = None
    for r, row in enumerate(centres):
        for c, (cx, cy) in enumerate(row):
            d = (cx - x) ** 2 + (cy - y) ** 2
            if best is None or d < best[0]:
                best = (d, r, c)
    return best


def read_bands(page, info):
    """Follow each light grey band on an answer page and spell what it covers."""
    H = float(page.height)
    cell = info["centres"][0][1][0] - info["centres"][0][0][0]
    spelled = []
    for ln in page.lines:
        colour = ln.get("stroking_color")
        grey = colour[0] if isinstance(colour, (tuple, list)) else colour
        if ln.get("linewidth", 0) < cell * 0.5 or grey is None or grey < 0.8:
            continue    # the darker outline pass, borders and rules are not bands
        (x0, y0), (x1, y1) = ln["pts"][0], ln["pts"][-1]
        d0, r0, c0 = _nearest(info["centres"], x0, y0)
        d1, r1, c1 = _nearest(info["centres"], x1, y1)
        # A letter's reported box sits a few points off its drawn centre, so
        # allow a third of a cell: still far too little to reach a neighbour.
        if max(d0, d1) > (cell * 0.3) ** 2:
            raise AssertionError("an answer band does not start or end on a letter")
        steps = max(abs(r1 - r0), abs(c1 - c0))
        dr = (r1 > r0) - (r1 < r0)
        dc = (c1 > c0) - (c1 < c0)
        if (abs(r1 - r0) not in (0, steps)) or (abs(c1 - c0) not in (0, steps)):
            raise AssertionError("an answer band is not straight")
        spelled.append("".join(info["grid"][r0 + dr * i][c0 + dc * i] for i in range(steps + 1)))
    return spelled


def check_single(path, puz, built, promised_pt, list_pt):
    """A two-page puzzle PDF: page 1 the puzzle, page 2 its answer."""
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 2:
            raise AssertionError("%s: expected 2 pages, found %d" % (path, len(pdf.pages)))
        out = check_pages(pdf.pages[0], pdf.pages[1], puz, built, promised_pt, list_pt, path)
    return out


def check_pages(ppage, apage, puz, built, promised_pt, list_pt, label=""):
    words = sorted(puz["words"])
    p = read_page(ppage, puz["level"])
    if p["grid"] != built["grid"]:
        raise AssertionError("%s: the printed grid is not the built grid" % label)
    if p["grid_pt"] != promised_pt:
        raise AssertionError("%s: grid letters are %s pt, promised %s" % (label, p["grid_pt"], promised_pt))
    if p["list_pt"] != list_pt:
        raise AssertionError("%s: word list is %s pt, promised %s" % (label, p["list_pt"], list_pt))
    if sorted(p["words"]) != words:
        raise AssertionError("%s: printed word list differs: %s" % (label, sorted(set(p["words"]) ^ set(words))))
    if p["title"] != puz["title"]:
        raise AssertionError("%s: title reads %r" % (label, p["title"]))
    checked = ws.verify(p["grid"], puz["words"], puz["level"])   # the PRINTED grid, re-solved
    if ppage.lines and any((ln.get("linewidth", 0) > 10) for ln in ppage.lines):
        raise AssertionError("%s: the puzzle page shows answer bands" % label)
    bands = None
    if apage is not None:
        a = read_page(apage, puz["level"])
        if a["grid"] != built["grid"]:
            raise AssertionError("%s: the answer page grid differs from the puzzle" % label)
        bands = read_bands(apage, a)
        if sorted(bands) != words:
            raise AssertionError("%s: answer bands spell %s" % (label, sorted(bands)))
    return {"words_checked": checked, "bands": len(bands) if bands is not None else None,
            "grid_pt": p["grid_pt"], "list_pt": p["list_pt"]}


def check_pack(path, pack, built_all, promised, list_pt):
    """The full pack: cover, one page per puzzle, then answers two to a page."""
    total = len(pack["puzzles"])
    out = {"puzzles": 0, "words_checked": 0, "answers": 0}
    with pdfplumber.open(path) as pdf:
        expect = 1 + total + -(-total // 2)
        if len(pdf.pages) != expect:
            raise AssertionError("%s: expected %d pages, found %d" % (path, expect, len(pdf.pages)))
        cover = pdf.pages[0].extract_text() or ""
        for puz in pack["puzzles"]:
            if puz["title"] not in cover:
                raise AssertionError("cover does not list %s" % puz["title"])
        for i, (puz, built) in enumerate(zip(pack["puzzles"], built_all), 1):
            res = check_pages(pdf.pages[i], None, puz, built, promised[puz["level"]], list_pt, "%s p%d" % (path, i + 1))
            out["puzzles"] += 1
            out["words_checked"] += res["words_checked"]
        # answer sheets: two small grids per page, top one first
        for k in range(0, total, 2):
            page = pdf.pages[1 + total + k // 2]
            # split where the second heading starts, found from the page itself
            tops = sorted({round(ch["top"]) for ch in page.chars if "Fraunces" in ch["fontname"]})
            cut = (tops[-1] - 4) if len(tops) > 1 and tops[-1] - tops[0] > 50 else page.height
            halves = [page.crop((0, 0, page.width, cut))]
            if cut < page.height:
                halves.append(page.crop((0, cut, page.width, page.height)))
            for j, half in enumerate(halves):
                if k + j >= total:
                    break
                puz, built = pack["puzzles"][k + j], built_all[k + j]
                n = ws.LEVELS[puz["level"]]["size"]
                bold = [ch for ch in half.chars if "Atkinson" in ch["fontname"] and "Bold" in ch["fontname"]]
                rows = _rows(bold, n)
                grid = ["".join(ch["text"] for ch in row) for row in rows]
                if grid != built["grid"]:
                    raise AssertionError("answer sheet grid %d differs" % (k + j + 1))
                info = {"grid": grid, "centres": [[((ch["x0"] + ch["x1"]) / 2.0, (ch["top"] + ch["bottom"]) / 2.0)
                                                   for ch in row] for row in rows]}
                bands = read_bands(half, info)
                if sorted(bands) != sorted(puz["words"]):
                    raise AssertionError("answer sheet %d bands spell %s" % (k + j + 1, sorted(bands)))
                head = "".join(ch["text"] for ch in sorted(
                    [ch for ch in half.chars if "Fraunces" in ch["fontname"]], key=lambda ch: (round(ch["top"]), ch["x0"])))
                if head != "Answer %d: %s" % (k + j + 1, puz["title"]):
                    raise AssertionError("answer sheet heading reads %r" % head)
                out["answers"] += 1
    if out["puzzles"] != total or out["answers"] != total or out["words_checked"] == 0:
        raise AssertionError("pack check incomplete: %s" % out)
    return out
