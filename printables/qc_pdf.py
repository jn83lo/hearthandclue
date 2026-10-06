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


# ------------------------------------------------------------------ books

def _fraunces(obj):
    return "".join(ch["text"] for ch in sorted(
        [ch for ch in obj.chars if "Fraunces" in ch["fontname"]], key=lambda ch: (round(ch["top"]), ch["x0"])))


def _flat(text):
    return " ".join((text or "").split())


def page_links(pdf):
    """Every link in the file, as {page number: [(box, kind, target)]}.

    kind is "web" (target is the address) or "page" (target is the number of
    the page the link jumps to). A link that leads nowhere is an error.
    """
    from pdfminer.pdftypes import PDFObjRef, resolve1
    ids = {p.page_obj.pageid: p.page_number for p in pdf.pages}
    out = {}
    for p in pdf.pages:
        found = []
        for a in p.annots:
            box = (a["x0"], a["top"], a["x1"], a["bottom"])
            if a.get("uri"):
                found.append((box, "web", a["uri"]))
                continue
            dest = resolve1((a.get("data") or {}).get("Dest"))
            if isinstance(dest, (list, tuple)) and dest and isinstance(dest[0], PDFObjRef) and dest[0].objid in ids:
                found.append((box, "page", ids[dest[0].objid]))
            else:
                raise AssertionError("page %d has a link that leads nowhere" % p.page_number)
        out[p.page_number] = found
    return out


def _link_at(links, x, y):
    """The page links whose box covers the point (x from the left, y from the top)."""
    return [t for (x0, top, x1, bottom), kind, t in links if kind == "page" and x0 <= x <= x1 and top <= y <= bottom]


def fonts_embedded(pdf):
    """Names of the fonts in the file; raises if any of them is not carried inside it."""
    from pdfminer.pdftypes import resolve1
    names = set()
    for p in pdf.pages:
        res = resolve1(p.page_obj.attrs.get("Resources")) or {}
        for ref in (resolve1(res.get("Font")) or {}).values():
            font = resolve1(ref)
            desc = resolve1(font.get("FontDescriptor"))
            if desc is None and font.get("DescendantFonts"):
                desc = resolve1(resolve1(resolve1(font["DescendantFonts"])[0]).get("FontDescriptor"))
            name = str(font.get("BaseFont"))
            if desc is None or not any(k in desc for k in ("FontFile", "FontFile2", "FontFile3")):
                raise AssertionError("font %s is named but not embedded (page %d)" % (name, p.page_number))
            names.add(name.strip("/'").split("+")[-1])
    return sorted(names)


def check_book(path, book, built_all, plan, promised, list_pt):
    """A whole book, read back from the file.

    For every puzzle: the printed grid is the built grid and is solved again
    from the page; letter and word-list sizes are measured; the title, note,
    level and word list are the puzzle's own; the footer gives the puzzle's
    number, the page's real number, and an answer page that really holds that
    puzzle's answer. Every answer is found, with its bands spelling the words.
    The contents list gives every puzzle once, with the page it is really on.
    The tracker has one box for every puzzle. Every link is followed. Every
    font is embedded. Nothing is printed in the margins, and no figure is set
    with a slashed zero.
    """
    import re
    total = plan["total"]
    out = {"pages": 0, "puzzles": 0, "words_checked": 0, "answers": 0, "bands": 0,
           "contents_entries": 0, "links_followed": 0, "web_links": 0}
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != plan["pages"]:
            raise AssertionError("%s: expected %d pages, found %d" % (path, plan["pages"], len(pdf.pages)))
        out["pages"] = len(pdf.pages)
        links = page_links(pdf)
        out["fonts"] = fonts_embedded(pdf)

        # 1. the answers: find out from the pages themselves where each one is
        where = {}
        for pno in range(plan["first_answer"], plan["first_answer"] + plan["sheets"]):
            page = pdf.pages[pno - 1]
            tops = sorted({round(ch["top"]) for ch in page.chars if "Fraunces" in ch["fontname"]})
            cut = (tops[-1] - 4) if len(tops) > 1 and tops[-1] - tops[0] > 50 else page.height
            halves = [page.crop((0, 0, page.width, cut))]
            if cut < page.height:
                halves.append(page.crop((0, cut, page.width, page.height)))
            for half in halves:
                head = _fraunces(half)
                m = re.fullmatch(r"Answer (\d+): (.+)", head)
                if not m or not 1 <= int(m.group(1)) <= total:
                    raise AssertionError("page %d: answer heading reads %r" % (pno, head))
                n = int(m.group(1))
                puz, built = book["puzzles"][n - 1], built_all[n - 1]
                if m.group(2) != puz["title"]:
                    raise AssertionError("page %d: answer %d is headed %r" % (pno, n, m.group(2)))
                if n in where:
                    raise AssertionError("answer %d is printed twice" % n)
                size = ws.LEVELS[puz["level"]]["size"]
                bold = [ch for ch in half.chars if "Atkinson" in ch["fontname"] and "Bold" in ch["fontname"]]
                rows = _rows(bold, size)
                grid = ["".join(ch["text"] for ch in row) for row in rows]
                if grid != built["grid"]:
                    raise AssertionError("page %d: the grid of answer %d is not the puzzle's grid" % (pno, n))
                info = {"grid": grid, "centres": [[((ch["x0"] + ch["x1"]) / 2.0, (ch["top"] + ch["bottom"]) / 2.0)
                                                   for ch in row] for row in rows]}
                bands = read_bands(half, info)
                if sorted(bands) != sorted(puz["words"]):
                    raise AssertionError("page %d: answer %d bands spell %s" % (pno, n, sorted(bands)))
                out["bands"] += len(bands)
                # the heading leads back to the puzzle
                hc = [ch for ch in half.chars if "Fraunces" in ch["fontname"]]
                hx = (min(ch["x0"] for ch in hc) + max(ch["x1"] for ch in hc)) / 2.0
                hy = (min(ch["top"] for ch in hc) + max(ch["bottom"] for ch in hc)) / 2.0
                if _link_at(links[pno], hx, hy) != [plan["first"] + n - 1]:
                    raise AssertionError("page %d: the heading of answer %d does not lead to its puzzle" % (pno, n))
                out["links_followed"] += 1
                where[n] = pno
                out["answers"] += 1
            m = re.search(r"Answers Page (\d+)$", _flat(page.extract_text()))
            if not m or int(m.group(1)) != pno:
                raise AssertionError("page %d: the footer does not give its page number" % pno)
        if sorted(where) != list(range(1, total + 1)):
            raise AssertionError("answers found for %d of %d puzzles" % (len(where), total))

        # 2. every puzzle page
        for n in range(1, total + 1):
            pno = plan["first"] + n - 1
            page = pdf.pages[pno - 1]
            puz, built = book["puzzles"][n - 1], built_all[n - 1]
            label = "%s page %d" % (path, pno)
            res = check_pages(page, None, puz, built, promised[puz["level"]], list_pt, label)
            if res["words_checked"] != len(puz["words"]):
                raise AssertionError("%s: checked %d words" % (label, res["words_checked"]))
            text = _flat(page.extract_text())
            spec = ws.LEVELS[puz["level"]]
            if _flat(puz["note"]) not in text:
                raise AssertionError("%s: the note is not the puzzle's" % label)
            if spec["label"].upper() not in text or spec["rule"] not in text:
                raise AssertionError("%s: the level line is missing or wrong" % label)
            m = re.search(r"Puzzle (\d+) of (\d+) Page (\d+) \S Answer on page (\d+)$", text)
            if not m:
                raise AssertionError("%s: footer not found" % label)
            got = tuple(int(v) for v in m.groups())
            if got != (n, total, pno, where[n]):
                raise AssertionError("%s: footer says puzzle %d of %d, page %d, answer on page %d; the answer is on page %d"
                                     % ((label,) + got + (where[n],)))
            inner = [t for _, kind, t in links[pno] if kind == "page"]
            if inner != [where[n]]:
                raise AssertionError("%s: its answer link leads to %s" % (label, inner))
            out["links_followed"] += 1
            out["puzzles"] += 1
            out["words_checked"] += res["words_checked"]

        # 3. the contents list
        seen = {}
        for k in range(len(plan["chunks"])):
            pno = plan["contents_first"] + k
            page = pdf.pages[pno - 1]
            mid = page.width / 2.0
            for x0, x1 in ((0, mid), (mid, page.width)):
                col = page.crop((x0, 0, x1, page.height))
                for line in col.extract_text_lines():
                    m = re.fullmatch(r"(\d+) (.+) (\d+)", _flat(line["text"]))
                    if not m:
                        continue
                    n, title, target = int(m.group(1)), m.group(2), int(m.group(3))
                    if n in seen or not 1 <= n <= total:
                        raise AssertionError("contents: puzzle %d is listed twice or does not exist" % n)
                    if title != book["puzzles"][n - 1]["title"]:
                        raise AssertionError("contents: puzzle %d is listed as %r" % (n, title))
                    if target != plan["first"] + n - 1:
                        raise AssertionError("contents: puzzle %d is said to be on page %d" % (n, target))
                    lx, ly = (line["x0"] + line["x1"]) / 2.0, (line["top"] + line["bottom"]) / 2.0
                    if _link_at(links[pno], lx, ly) != [target]:
                        raise AssertionError("contents: the line for puzzle %d does not lead to page %d" % (n, target))
                    out["links_followed"] += 1
                    seen[n] = target
            if not re.search(r"Page %d$" % pno, _flat(page.extract_text())):
                raise AssertionError("page %d: the footer does not give its page number" % pno)
        if sorted(seen) != list(range(1, total + 1)):
            raise AssertionError("contents lists %d of %d puzzles" % (len(seen), total))
        out["contents_entries"] = len(seen)

        # 3b. the tracker: one box for every puzzle, its number leading to that puzzle
        tno = plan["tracker"]
        tpage = pdf.pages[tno - 1]
        ticked = {}
        for (x0, top, x1, bottom), kind, target in links[tno]:
            if kind != "page":
                continue
            inside = _flat(tpage.crop((x0, top, x1, bottom)).extract_text())
            if not inside.isdigit() or target != plan["first"] + int(inside) - 1 or int(inside) in ticked:
                raise AssertionError("tracker: the box marked %r leads to page %d" % (inside, target))
            boxes = [r for r in tpage.rects if x0 <= (r["x0"] + r["x1"]) / 2.0 <= x1 and top <= (r["top"] + r["bottom"]) / 2.0 <= bottom]
            if len(boxes) != 1:
                raise AssertionError("tracker: puzzle %s has %d boxes to tick" % (inside, len(boxes)))
            ticked[int(inside)] = target
            out["links_followed"] += 1
        if sorted(ticked) != list(range(1, total + 1)):
            raise AssertionError("the tracker has %d of %d puzzles" % (len(ticked), total))
        out["tracker_boxes"] = len(ticked)

        # 4. every link is one of the above, or goes to one of the book's own addresses
        inner = sum(1 for found in links.values() for _, kind, _ in found if kind == "page")
        if inner != out["links_followed"]:
            raise AssertionError("%d links inside the book, %d of them checked" % (inner, out["links_followed"]))
        allowed = {"https://" + book[k] for k in ("site", "free", "shop")}
        for pno, found in links.items():
            for _, kind, target in found:
                if kind == "web":
                    if target not in allowed:
                        raise AssertionError("page %d links to %s" % (pno, target))
                    out["web_links"] += 1

        # 4b. the bookmarks a PDF reader lists down its side
        from pdfminer.pdftypes import PDFObjRef, resolve1
        ids = {p.page_obj.pageid: p.page_number for p in pdf.pages}
        got = []
        for level, title, dest, _action, _ in pdf.doc.get_outlines():
            dest = resolve1(dest)
            if not (isinstance(dest, (list, tuple)) and dest and isinstance(dest[0], PDFObjRef) and dest[0].objid in ids):
                raise AssertionError("the bookmark %r leads nowhere" % title)
            got.append((level, title, ids[dest[0].objid]))
        want = [(1, "Cover", 1), (1, "Before you begin", 2), (1, "Contents", plan["contents_first"]),
                (1, "Puzzle tracker", plan["tracker"])]
        dash = chr(8211)
        for g in plan["groups"]:
            span = "%d%s%d" % (g["first"], dash, g["last"]) if g["first"] != g["last"] else "%d" % g["first"]
            want.append((1, "%s puzzles, %s" % (ws.LEVELS[g["level"]]["label"], span), plan["first"] + g["first"] - 1))
            for n in range(g["first"], g["last"] + 1):
                want.append((2, "%d. %s" % (n, book["puzzles"][n - 1]["title"]), plan["first"] + n - 1))
        want.append((1, "Answers", plan["first_answer"]))
        for k in range(plan["sheets"]):
            a, b = 2 * k + 1, min(total, 2 * k + 2)
            want.append((2, "Answers %s" % ("%d%s%d" % (a, dash, b) if a != b else "%d" % a), plan["first_answer"] + k))
        want.append((1, "More from Hearth & Clue", plan["closing"]))
        if got != want:
            diff = [(g, w) for g, w in zip(got, want) if g != w][:3]
            raise AssertionError("bookmarks differ (%d found, %d wanted); first differences: %s" % (len(got), len(want), diff))
        out["bookmarks"] = len(got)

        # 5. nothing in the margins (the cover is the one page that runs to the edge)
        for page in pdf.pages[1:]:
            W, H = float(page.width), float(page.height)
            for ch in page.chars:
                if ch["x0"] < 34 or ch["x1"] > W - 34 or ch["top"] < 24 or ch["bottom"] > H - 14:
                    raise AssertionError("page %d: %r is printed in the margin" % (page.page_number, ch["text"]))
            for other in (plan["closing"], plan["tracker"], 2):
                if page.page_number == other and not re.search(r"Page %d$" % other, _flat(page.extract_text())):
                    raise AssertionError("page %d: the footer does not give its page number" % other)
            # Atkinson's zero has a slash through it; figures belong in the other face
            if any(ch["text"] == "0" and "Atkinson" in ch["fontname"] for ch in page.chars):
                raise AssertionError("page %d prints a slashed zero" % page.page_number)
    if out["puzzles"] != total or out["answers"] != total or out["words_checked"] == 0:
        raise AssertionError("book check incomplete: %s" % out)
    return out
