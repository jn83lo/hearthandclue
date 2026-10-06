#!/usr/bin/env python3
"""Build a printable pack into the site.

    python printables/build.py halloween [site_root]

Writes, under <site_root>/<pack slug>/ :
    index.html, <puzzle>/index.html     the pages
    pdf/*.pdf                           every puzzle in US Letter and A4, plus the full pack
    img/*.png                           page previews, thumbnails, link-preview image
    pins/*.png                          Pinterest images (1000x1500)
    build.json                          what was built and what was checked
and merges this pack's pins into <site_root>/assets/pin-schedule.json, which
the site's scheduled poster reads.

The build stops with an error if any puzzle fails ws.verify(), or if any
finished PDF, read back and re-solved by qc_pdf, does not match. A build that
checked zero words also fails. Publish only the output of a build that ended
with its "built ..." line.
"""
import hashlib
import json
import os
import sys
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import art      # noqa: E402
import pages    # noqa: E402
import pdfs     # noqa: E402
import qc_pdf   # noqa: E402
import ws       # noqa: E402

BULLET = "  " + chr(8226) + "  "


def _ascii(text):
    if any(ord(ch) > 126 or ord(ch) < 32 for ch in text):
        raise AssertionError("pin text must be plain ASCII: %r" % text)
    return text


def pin_copy(pack, pin):
    """Title, description and alt text for one pin, written the way people search."""
    total = len(pack["puzzles"])
    season = pack["season"]
    kind = pin.get("kind", "puzzle")
    colour = {"night": "dark purple", "pumpkin": "orange", "cream": "cream"}[pin["scheme"]]
    if kind == "hub":
        title = "Free Printable %s Word Searches - Large Print, %d Puzzles with Answers" % (season, total)
        desc = ("%d free printable %s word searches in large print (22 to 28 pt letters). Three levels from easy to hard, "
                "an answer key for every puzzle, US Letter and A4, black and white. No sign-up and no ads. "
                "Good for adults, seniors, classrooms and care homes." % (total, season))
        alt = ("Three printed %s word search pages with large letters, fanned out on a %s background, under the words "
               "%d Free Printables, %s Word Searches, Large Print, 3 Levels, Answer Keys." % (season, colour, total, season))
    elif kind == "hub2":
        title = "%s Word Search Printables for Adults - Free, Large Print, 3 Levels" % season
        desc = ("%s word search printables for adults, free: %d large print puzzles (22 to 28 pt letters) in three levels, "
                "from easy grids that only run across and down to hard ones that run in every direction. "
                "Answer keys, US Letter and A4, black and white, no sign-up." % (season, total))
        alt = ("Three printed %s word search pages with large letters, fanned out on a %s background, under the words "
               "%d Free Printables, %s Word Searches, Large Print, 3 Levels, Answer Keys." % (season, colour, total, season))
    elif kind == "seniors":
        title = "Large Print %s Word Search for Seniors - Free Printable PDF" % season
        desc = ("Free large print %s word search for seniors: 28 pt letters, words that run across and down only, "
                "nothing backwards or diagonal, and an answer key. Print on US Letter or A4, black and white, no sign-up. "
                "%d free puzzles in three levels for care homes and activity groups." % (season, total))
        alt = ("A printed %s word search page with very large letters on a %s background, under the words Free Printable, "
               "Large Print %s Word Search, 28 pt Letters, Easy, Answer Key." % (season, colour, season))
    elif kind == "easy":
        title = "Easy %s Word Search Printable - Free, Large Print, Across and Down Only" % season
        desc = ("Easy %s word search printable, free: large 28 pt letters and words that only run across and down. "
                "Answer key included, US Letter and A4, black and white, no sign-up. "
                "Part of %d free %s word searches in three levels." % (season, total, season))
        alt = ("Two printed easy %s word search pages with large letters on a %s background, under the words Free Printable, "
               "Easy %s Word Search, Across and Down Only, 28 pt." % (season, colour, season))
    else:
        puz = next(p for p in pack["puzzles"] if p["slug"] == pin["target"])
        spec = ws.LEVELS[puz["level"]]
        pt = pdfs.PROMISED[puz["level"]]
        title = "%s - Free Printable, Large Print with Answer Key" % puz["search"]
        desc = ("Free printable %s in large print: %d words in a %d by %d grid with %d pt letters. %s "
                "Answer key included, US Letter and A4, black and white, no sign-up. One of %d free %s word searches "
                "from Hearth & Clue." % (puz["search"].lower(), len(puz["words"]), spec["size"], spec["size"], pt,
                                          spec["rule"], total, season))
        alt = ("A printed word search page titled %s with a %d by %d grid of large letters and a word list, on a %s "
               "background, under the words Free %s Printable, %s, Large Print, %d pt, Answer Key."
               % (puz["title"], spec["size"], spec["size"], colour, season, puz["search"], pt))
    for text, limit in ((title, 100), (desc, 500), (alt, 500)):
        _ascii(text)
        if len(text) > limit:
            raise AssertionError("pin text over %d characters: %r" % (limit, text))
    return title, desc, alt


def make_pin(pack, pin, page_img, out_path):
    season = pack["season"]
    total = len(pack["puzzles"])
    kind = pin.get("kind", "puzzle")
    foot = "No sign-up" + BULLET + "US Letter and A4"
    by_level = {lv: [p for p in pack["puzzles"] if p["level"] == lv] for lv in ("easy", "medium", "hard")}
    if kind in ("hub", "hub2"):
        picks = [by_level["easy"][0], by_level["medium"][0], by_level["hard"][0]]
        if kind == "hub2":
            picks = [by_level["medium"][-1], by_level["easy"][1], by_level["hard"][-1]]
        art.pin(out_path, pin["scheme"], "%d FREE PRINTABLES" % total, "%s Word Searches" % season,
                "LARGE PRINT" + BULLET + "3 LEVELS" + BULLET + "ANSWER KEYS",
                [page_img(p, 1) for p in picks], foot)
    elif kind == "seniors":
        puz = by_level["easy"][2]
        art.pin(out_path, pin["scheme"], "FREE PRINTABLE", "Large Print %s Word Search" % season,
                "28 PT LETTERS" + BULLET + "EASY" + BULLET + "ANSWER KEY",
                [page_img(puz, 1), page_img(puz, 2)], "For seniors, care homes and activity groups", pumpkin=False)
    elif kind == "easy":
        art.pin(out_path, pin["scheme"], "FREE PRINTABLE", "Easy %s Word Search" % season,
                "ACROSS AND DOWN ONLY" + BULLET + "28 PT",
                [page_img(by_level["easy"][3], 1), page_img(by_level["easy"][1], 1)], foot)
    else:
        puz = next(p for p in pack["puzzles"] if p["slug"] == pin["target"])
        art.pin(out_path, pin["scheme"], "FREE %s PRINTABLE" % season.upper(), puz["search"],
                "LARGE PRINT" + BULLET + "%d PT" % pdfs.PROMISED[puz["level"]] + BULLET + "ANSWER KEY",
                [page_img(puz, 1), page_img(puz, 2)], foot, pumpkin=(pin["scheme"] != "pumpkin"))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(name, root):
    pack = json.load(open(os.path.join(HERE, "packs", name + ".json")))
    slug, total = pack["slug"], len(pack["puzzles"])
    out = os.path.join(root, slug)
    for sub in ("pdf", "img", "pins"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    report = {"pack": slug, "puzzles": total, "checks": {}, "files": {}}

    # 1. grids, each verified from scratch
    built, words_verified = [], 0
    for puz in pack["puzzles"]:
        b = ws.generate(puz["words"], puz["level"], "%s/%s" % (pack["seed"], puz["slug"]))
        words_verified += ws.verify(b["grid"], puz["words"], puz["level"], b["placed"])
        built.append(b)
    themes = [p["title"] for p in pack["puzzles"]]
    if len(set(themes)) != total or len({p["slug"] for p in pack["puzzles"]}) != total:
        raise AssertionError("two puzzles share a title or slug")
    report["checks"]["grid_words_verified"] = words_verified

    # 2. PDFs, each read back and re-solved
    pdf_words = 0
    for paper in ("letter", "a4"):
        for i, (puz, b) in enumerate(zip(pack["puzzles"], built), 1):
            path = os.path.join(out, "pdf", pages.pdf_name(pack, puz, paper))
            pdfs.single(path, paper, pack, puz, b, i, total)
            r = qc_pdf.check_single(path, puz, b, pdfs.PROMISED[puz["level"]], pdfs.WORD_PT)
            if r["words_checked"] != len(puz["words"]) or r["bands"] != len(puz["words"]):
                raise AssertionError("PDF check incomplete for %s" % path)
            pdf_words += r["words_checked"]
        path = os.path.join(out, "pdf", pages.pack_pdf_name(pack, paper))
        n_pages = pdfs.pack_pdf(path, paper, pack, built)
        r = qc_pdf.check_pack(path, pack, built, pdfs.PROMISED, pdfs.WORD_PT)
        pdf_words += r["words_checked"]
        report["checks"]["pack_%s" % paper] = dict(r, pages=n_pages)
    if pdf_words == 0:
        raise AssertionError("the PDF check looked at zero words")
    report["checks"]["pdf_words_resolved"] = pdf_words
    report["checks"]["letter_sizes_pt"] = {"grid": pdfs.PROMISED, "word_list": pdfs.WORD_PT}

    # 3. previews
    cache = {}

    def page_img(puz, page_no):
        key = (puz["slug"], page_no)
        if key not in cache:
            cache[key] = art.render_page(os.path.join(out, "pdf", pages.pdf_name(pack, puz, "letter")), page_no, 200)
        return cache[key]

    for puz in pack["puzzles"]:
        art.save_preview(os.path.join(out, "pdf", pages.pdf_name(pack, puz, "letter")),
                         os.path.join(out, "img", puz["slug"] + ".png"),
                         os.path.join(out, "img", puz["slug"] + "-s.png"))
    art.og(os.path.join(out, "img", "og.png"), "%d FREE PRINTABLES" % total, "%s Word Searches" % pack["season"],
           "Large print. Three levels. Answer keys. No sign-up.",
           [page_img(pack["puzzles"][0], 1), page_img(pack["puzzles"][4], 1)])

    # 4. pins and their schedule
    pt = pack["pinterest"]
    entries = []
    for pin in pt["pins"]:
        make_pin(pack, pin, page_img, os.path.join(out, "pins", pin["id"] + ".png"))
        title, desc, alt = pin_copy(pack, pin)
        target = pages.urls(pack) if pin["target"] == "hub" else pages.urls(pack, next(p for p in pack["puzzles"] if p["slug"] == pin["target"]))
        entries.append({"id": "%s/%s" % (slug, pin["id"]), "date": pin["date"], "board_id": pt["board_id"],
                        "title": title, "description": desc, "alt_text": alt,
                        "link": pages.ORIGIN + target["page"] + "?src=pin",
                        "image": "%s/%s/pins/%s.png" % (pages.ORIGIN, slug, pin["id"])})
    # the pin each page offers through its own "Save to Pinterest" link
    for puz in pack["puzzles"]:
        own = [p for p in pt["pins"] if p["target"] == puz["slug"]]
        if not own:
            raise AssertionError("no pin image for %s" % puz["slug"])
        if own[0]["id"] != puz["slug"]:
            raise AssertionError("the pin for %s must be named after it" % puz["slug"])
    sched_path = os.path.join(root, "assets", "pin-schedule.json")
    os.makedirs(os.path.dirname(sched_path), exist_ok=True)
    try:
        sched = json.load(open(sched_path))
    except Exception:
        sched = {"pins": []}
    sched["pins"] = [p for p in sched["pins"] if not p["id"].startswith(slug + "/")] + entries
    sched["pins"].sort(key=lambda p: (p["date"], p["id"]))
    if len({p["id"] for p in sched["pins"]}) != len(sched["pins"]):
        raise AssertionError("duplicate pin ids in the schedule")
    # The poster recognises a pin already on the board by its title and link,
    # so no two scheduled pins may share both.
    keys = [(p["title"], p["link"].split("?")[0].rstrip("/").lower(), p["board_id"]) for p in sched["pins"]]
    if len(set(keys)) != len(keys):
        raise AssertionError("two scheduled pins share a title and link: %s" % sorted(k for k in keys if keys.count(k) > 1)[:2])
    if len({p["image"] for p in sched["pins"]}) != len(sched["pins"]):
        raise AssertionError("two scheduled pins share an image")
    if pt["board_id"].isdigit():
        json.dump(sched, open(sched_path, "w"), indent=1)
        open(sched_path, "a").write("\n")
    else:
        print("NOTE: no Pinterest board id yet - schedule not written")

    # 5. pages
    html = {os.path.join(out, "index.html"): pages.hub(pack)}
    for i, (puz, b) in enumerate(zip(pack["puzzles"], built), 1):
        d = os.path.join(out, puz["slug"])
        os.makedirs(d, exist_ok=True)
        html[os.path.join(d, "index.html")] = pages.puzzle(pack, puz, b, i)
    for path, text in html.items():
        if any(ord(ch) > 126 for ch in text):
            raise AssertionError("non-ASCII character in %s" % path)
        open(path, "w", newline="\n").write(text)

    # 6. every link and image the pages mention must exist in the build
    import re
    missing = set()
    for path, text in html.items():
        for ref in re.findall(r'(?:href|src)="(/[^"#?]*)', text):
            if ref.startswith("/.netlify") or ref in ("/", "/privacy", "/favicon.png"):
                continue
            local = os.path.join(root, ref.lstrip("/"))
            if ref.endswith("/"):
                local = os.path.join(local, "index.html")
            if not os.path.exists(local):
                missing.add(ref)
        # the image each "Save to Pinterest" link hands to Pinterest
        for media in re.findall(r'media=([^&"]+)', text):
            ref = unquote(media).replace(pages.ORIGIN, "")
            if not os.path.exists(os.path.join(root, ref.lstrip("/"))):
                missing.add(ref)
    if missing:
        raise AssertionError("pages link to files that were not built: %s" % sorted(missing))

    for base, _, files in sorted(os.walk(out)):
        for f in sorted(files):
            if f == "build.json":
                continue
            full = os.path.join(base, f)
            report["files"][os.path.relpath(full, root)] = {"bytes": os.path.getsize(full), "sha256": sha(full)}
    report["checks"]["pins"] = len(entries)
    report["checks"]["pages"] = len(html)
    json.dump(report, open(os.path.join(out, "build.json"), "w"), indent=1, sort_keys=True)
    return report


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "halloween"
    root = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(HERE)
    rep = build(name, root)
    kinds = {}
    for f, meta in rep["files"].items():
        ext = f.rsplit(".", 1)[-1]
        kinds.setdefault(ext, [0, 0])
        kinds[ext][0] += 1
        kinds[ext][1] += meta["bytes"]
    print("built %s: %s" % (rep["pack"], ", ".join("%d %s (%d KB)" % (n, e, b // 1024) for e, (n, b) in sorted(kinds.items()))))
    print("checks:", json.dumps(rep["checks"], sort_keys=True))
