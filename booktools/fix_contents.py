#!/usr/bin/env python3
"""Repair the Contents page of a Hearth & Clue book.

Usage: python booktools/fix_contents.py <outdir> book1.pdf book2.pdf ...
Needs: pip install pypdf reportlab pdfplumber

THE BUG: the builder started column 2 without resetting y, so 55-puzzle books
split 10/45 and ran entries down to y=-344, far off the page. Affects every
long book. 12-chapter mystery books fit and are untouched.

This reads the page's OWN colours, fonts and entry text out of the content
stream, re-lays them into two balanced columns inside the margins, and splices
only that page back. Page count never changes.

GOTCHA: column 2 is narrower than column 1, so the font-fit test must use the
NARROWER column or long titles overflow the right edge. Also pypdf's
get_contents() returns a detached copy — you must use page.replace_contents()
or the edit silently does nothing.

AFTER RUNNING: render page 3 and LOOK at it. The numeric checks passed a
book whose clue list had fallen out of alphabetical order.
"""
import os, re, sys
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject
from reportlab.pdfbase import pdfmetrics

PAGE_W, PAGE_H = 612, 792
LEFT, TOP_TITLE, TOP_FIRST = 72, 705.6, 669.6
BOTTOM_LIMIT = 54          # nothing may sit below this
COL_X = [72, 306]
COL_RIGHT = [296, 540]     # usable right edge per column


def find_contents(reader):
    for i, page in enumerate(reader.pages):
        data = page.get_contents().get_data().decode("latin-1")
        if "(Contents)" in data:
            return i, data
    return None, None


def parse(data):
    """Pull the palette, fonts and numbered entries out of the page."""
    colours = re.findall(r"([\d.]+ [\d.]+ [\d.]+) rg", data)
    bg = colours[0] if colours else ".984314 .960784 .917647"
    title_col = colours[1] if len(colours) > 1 else ".756863 .439216 .227451"
    entry_col = colours[2] if len(colours) > 2 else ".360784 .25098 .2"

    tf = re.findall(r"/(F\d+) ([\d.]+) Tf", data)
    title_size = float(tf[1][1]) if len(tf) > 1 else 20.0
    entry_size = float(tf[0][1]) if tf else 12.0

    entries = []
    for m in re.finditer(r"Tm \((\d+\.\s+[^)]*)\) Tj", data):
        entries.append(m.group(1))
    return bg, title_col, entry_col, title_size, entry_size, entries


def layout(entries, entry_size):
    """Two balanced columns; shrink the step, then the font, until everything fits."""
    n = len(entries)
    per_col = (n + 1) // 2
    size = entry_size
    while True:
        available = TOP_FIRST - BOTTOM_LIMIT
        step = available / max(per_col - 1, 1)
        step = min(step, 23.04)                      # never looser than the original
        if step >= size * 1.25:                      # readable leading
            widest = max(pdfmetrics.stringWidth(e, "Helvetica", size) for e in entries)
            # both columns must hold the longest entry, so test the narrower one
            usable = min(COL_RIGHT[0] - COL_X[0], COL_RIGHT[1] - COL_X[1]) - 4
            if widest <= usable:
                return per_col, step, size
        size -= 0.5
        if size < 8:
            return per_col, step, size


def build(bg, title_col, entry_col, title_size, entry_size, entries):
    per_col, step, size = layout(entries, entry_size)
    out = ["1 0 0 1 0 0 cm  BT /F1 12 Tf 14.4 TL ET"]
    out.append(f"{bg} rg")
    out.append(f"n 0 0 {PAGE_W} {PAGE_H} re f*")
    out.append(f"{title_col} rg")
    out.append(f"BT /F2 {title_size:g} Tf {title_size*1.2:g} TL ET")
    out.append(f"BT 1 0 0 1 {LEFT} {TOP_TITLE} Tm (Contents) Tj T* ET")
    out.append(f"BT /F1 {size:g} Tf {size*1.2:g} TL ET")
    out.append(f"{entry_col} rg")
    for i, e in enumerate(entries):
        col = 0 if i < per_col else 1
        row = i if col == 0 else i - per_col
        x = COL_X[col]
        y = TOP_FIRST - row * step
        out.append(f"BT 1 0 0 1 {x} {y:.2f} Tm ({e}) Tj T* ET")
    lowest = TOP_FIRST - (per_col - 1) * step
    return "\n".join(out) + "\n", per_col, step, size, lowest


def repair(src, outdir):
    name = os.path.basename(src)
    reader = PdfReader(src)
    idx, data = find_contents(reader)
    if idx is None:
        print(f"{name}: no Contents page — skipped")
        return None

    bg, tc, ec, ts, es, entries = parse(data)
    if not entries:
        print(f"{name}: Contents page has no numbered entries — skipped")
        return None

    ys = [float(m.group(1)) for m in re.finditer(r"1 0 0 1 [\d.]+ ([-\d.]+) Tm \(\d+\.", data)]
    broken = bool(ys) and min(ys) < BOTTOM_LIMIT

    stream, per_col, step, size, lowest = build(bg, tc, ec, ts, es, entries)
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i == idx:
            s = DecodedStreamObject()
            s.set_data(stream.encode("latin-1"))
            page.replace_contents(s)
        writer.add_page(page)

    os.makedirs(outdir, exist_ok=True)
    dest = os.path.join(outdir, name)
    with open(dest, "wb") as f:
        writer.write(f)

    status = "BROKEN" if broken else "already ok"
    print(f"{name}: {status} — {len(entries)} entries, was reaching y={min(ys):.0f}; "
          f"now {per_col}/column, step {step:.2f}, font {size:g}, lowest y={lowest:.1f}")
    return dest


def verify(orig, fixed, expected_entries):
    """Confirm the repair: all entries present, inside the margins, page count same."""
    import pdfplumber
    with pdfplumber.open(fixed) as pdf:
        pg = pdf.pages[2]
        words = pg.extract_words()
        nums = sorted(int(m.group(1)) for w in words
                      if (m := re.match(r"^(\d+)\.$", w["text"])))
        lines = {}
        for w in words:
            lines.setdefault((round(w["top"]), w["x0"] < 300), []).append(w)
        over = [k for k, ws in lines.items() if max(x["x1"] for x in ws) > 540]
        below = [w for w in words if w["bottom"] > pg.height - 36]
    same = len(PdfReader(orig).pages) == len(PdfReader(fixed).pages)
    ok = (nums == list(range(1, expected_entries + 1))
          and not over and not below and same)
    print(f"  verify: entries {'OK' if nums == list(range(1, expected_entries+1)) else 'BAD'}"
          f" | overflow {len(over)} | below margin {len(below)}"
          f" | pages {'same' if same else 'CHANGED'} | {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    outdir = sys.argv[1]
    for src in sys.argv[2:]:
        dest = repair(src, outdir)
        if dest:
            n = len(parse(find_contents(PdfReader(src))[1])[5])
            verify(src, dest, n)
