#!/usr/bin/env python3
"""
A page for every day's puzzle: daily/<issue>/index.html, plus the list of all
of them (daily/index.html) and their sitemap (daily/sitemap.xml).

Each day is recorded once, when its date arrives, in daily/issues.json: the
title, note, words and the 10x10 grid exactly as played that day. A recorded
day is never rewritten, so its page keeps showing the puzzle in that day's
pin even if THEMES changes later. The pages themselves are rebuilt on every
run from Index.html's styles, so they keep the home page's look.

Usage: python scripts/daily_pages.py [Index.html] [site_root]
"""
import datetime
import html
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import build, day_number, load_themes, theme_for  # noqa: E402

ORIGIN = "https://hearthandclue.com"
FIRST = 236            # the first day with a page (24 August 2026)
LEAD_HOURS = 14        # a day is added once its date has begun anywhere (UTC+14)
SIZE = 10


def esc(s):
    return html.escape(str(s), quote=True)


def long_date(d):
    return "%s, %s %d, %d" % (d.strftime("%A"), d.strftime("%B"), d.day, d.year)


def short_date(d):
    return "%s, %s %d" % (d.strftime("%a"), d.strftime("%b"), d.day)


def word_list(words):
    w = [x.title() for x in words]
    return ", ".join(w[:-1]) + " and " + w[-1]


def write_if_changed(path, data):
    data = data.encode("utf-8") if isinstance(data, str) else data
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return True


# ---- the record --------------------------------------------------------------

def record_new_days(record, themes, now_utc):
    """Add every day from the last recorded one up to the latest date on Earth.
    Returns the issue numbers added."""
    latest = (now_utc + datetime.timedelta(hours=LEAD_HOURS)).date()
    have = [int(k) for k in record]
    d = datetime.date(2026, 1, 1) + datetime.timedelta(days=(max(have) if have else FIRST - 1))
    added = []
    while d <= latest:
        n = day_number(d) + 1
        if n >= FIRST and str(n) not in record:
            t = theme_for(themes, d)
            grid = build(t["words"], d.year * 10000 + d.month * 100 + d.day)
            if grid is None:
                raise SystemExit("could not build the puzzle for %s" % d)
            record[str(n)] = {
                "date": d.isoformat(), "title": t["title"], "note": t["note"], "subject": t["subject"],
                "url": t["url"], "words": list(t["words"]), "grid": ["".join(r) for r in grid],
            }
            added.append(n)
        d += datetime.timedelta(days=1)
    return added


def check(record):
    """Every recorded grid must hold every word, and dates must match numbers."""
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
    for k, e in record.items():
        d = datetime.date.fromisoformat(e["date"])
        if day_number(d) + 1 != int(k):
            raise SystemExit("issue %s is dated %s" % (k, e["date"]))
        g = e["grid"]
        if len(g) != SIZE or any(len(r) != SIZE or not r.isalpha() or not r.isupper() for r in g):
            raise SystemExit("issue %s has a malformed grid" % k)
        for w in e["words"]:
            if not any(all(0 <= x + dx * i < SIZE and 0 <= y + dy * i < SIZE and g[y + dy * i][x + dx * i] == w[i]
                           for i in range(len(w)))
                       for y in range(SIZE) for x in range(SIZE) for dx, dy in dirs):
                raise SystemExit("issue %s: %s is not in its grid" % (k, w))


# ---- page parts taken from the home page -------------------------------------

def parts_from_home(index_html):
    src = open(index_html, encoding="utf-8").read()
    css = re.search(r"<style>\n(.*?)</style>", src, re.S).group(1)
    about = re.search(r'(<section class="about".*?</section>)', src, re.S).group(1)
    fonts = re.findall(r'<link rel="preconnect"[^>]*>|<link href="https://fonts.googleapis.com[^"]*" rel="stylesheet">', src)
    if len(fonts) != 3:
        raise SystemExit("Index.html: expected the three Google Fonts links")
    return css, about, "\n".join(fonts)


EXTRA_CSS = """
  .home-link { color:inherit; text-decoration:none; }
  .past { text-align:center; font-size:14px; color:var(--green); margin:-8px 0 18px; }
  .past a { color:var(--oxblood); }
  .pager { margin-top:4px; font-size:13px; }
  .nojs { text-align:center; font-size:13px; font-style:italic; color:var(--green); margin-top:4px; }
  .archive h2 { font-family:"Fraunces",Georgia,serif; font-size:19px; font-weight:600; color:var(--oxblood); margin:24px 0 6px; }
  .archive ul { list-style:none; }
  .archive li a { display:flex; align-items:baseline; gap:10px; padding:10px 4px; border-bottom:1px solid var(--rule); color:var(--ink); text-decoration:none; }
  .archive li a:hover { background:rgba(198,162,102,.10); }
  .archive .no { flex:0 0 auto; min-width:58px; font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--brass); }
  .archive .t { flex:1 1 auto; font-family:"Fraunces",Georgia,serif; font-weight:600; color:var(--oxblood); }
  .archive .d { flex:0 0 auto; font-size:13px; font-style:italic; color:var(--green); }
  .intro { text-align:center; font-size:15px; margin:-6px 0 8px; }
  .intro a { color:var(--oxblood); }
"""

# Hides links to a day that has not started yet where the visitor is.
HIDE_FUTURE = """<script>
(function () {
  var n = new Date(), t = n.getFullYear() + "-" + ("0" + (n.getMonth() + 1)).slice(-2) + "-" + ("0" + n.getDate()).slice(-2);
  var els = document.querySelectorAll("[data-date]");
  for (var i = 0; i < els.length; i++) if (els[i].getAttribute("data-date") > t) els[i].hidden = true;
})();
</script>"""


def head(title, desc, url, image, css, fonts):
    img = ('<meta property="og:image" content="%s">\n<meta name="twitter:image" content="%s">\n' % (esc(image), esc(image))) if image else ""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="description" content="%(desc)s">
<meta name="theme-color" content="#F8F3ED">

<meta property="og:type" content="article">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
%(img)s<meta property="og:url" content="%(url)s">
<meta name="twitter:card" content="summary_large_image">

<link rel="canonical" href="%(url)s">
<link rel="icon" type="image/png" href="/favicon.png">

%(fonts)s

<title>%(title)s</title>
<style>
%(css)s%(extra)s</style>
</head>
""" % {"title": esc(title), "desc": esc(desc), "url": esc(url), "img": img, "fonts": fonts,
       "css": css, "extra": EXTRA_CSS}


def masthead(issue_line, skip="Skip to the puzzle"):
    return """<a class="skip-link" href="#board">%s</a>
<div class="wrap">
  <header>
    <h1><a class="home-link" href="/">The Daily Clue</a></h1>
    <div class="rule"></div>
    <p class="tagline">A free word search, every day</p>
    <p class="issue" id="issue">%s</p>
  </header>
""" % (esc(skip), esc(issue_line))


def day_page(n, e, prev_e, next_e, extra, css, about, fonts, has_pin):
    d = datetime.date.fromisoformat(e["date"])
    title = "%s Word Search: %s | The Daily Clue No. %d" % (e["subject"], e["title"], n)
    desc = ("The Daily Clue No. %d, %s: %s. Find %s in a 10x10 word search grid. "
            "Free to play in your browser, no app, no sign-up." % (n, long_date(d), e["title"], word_list(e["words"])))
    url = "%s/daily/%d/" % (ORIGIN, n)
    image = "%s/daily/%d/pin.png" % (ORIGIN, n) if has_pin else None
    cells = "".join('<span class="cell">%s</span>' % ch for row in e["grid"] for ch in row)
    words = "".join('<div class="word">%s</div>' % esc(w) for w in e["words"])
    pager = []
    if prev_e:
        pager.append('<a href="/daily/%d/" rel="prev">&larr; No. %d</a>' % (n - 1, n - 1))
    pager.append('<a href="/daily/">All past puzzles</a>')
    later = ""
    if next_e:
        later = '<span data-date="%s"> &middot; <a href="/daily/%d/" rel="next">No. %d &rarr;</a></span>' % (next_e["date"], n + 1, n + 1)
    day = {"n": n, "date": e["date"], "title": e["title"], "note": e["note"], "subject": e["subject"],
           "url": extra.get("url"), "cta": extra.get("cta"), "words": e["words"], "grid": e["grid"]}
    data = json.dumps(day, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    issue_line = "No. %d · %s" % (n, d.strftime("%a %b %d %Y"))
    return (head(title, desc, url, image, css, fonts) + "<body>\n" + masthead(issue_line) +
            """  <nav class="past" aria-label="Past puzzles">
    <p>The puzzle from %(long)s. <a href="/">Play today's puzzle</a></p>
    <p class="pager">%(pager)s</p>
  </nav>
  <main id="app">
    <section class="card"><h2>%(title)s</h2><p>%(note)s</p></section>
    <div class="board" id="board"><div class="grid">%(cells)s</div></div>
    <div class="words">%(words)s</div>
    <noscript><p class="nojs">Turn on JavaScript to play here, or print this page and play with a pencil.</p></noscript>
  </main>
  %(about)s
</div>
<div aria-live="polite" class="sr-only" id="live"></div>

<script>window.DC_DAY = %(data)s;</script>
<script src="/assets/clue.js"></script>
%(hide)s
</body>
</html>
""" % {"long": esc(long_date(d)), "pager": " &middot; ".join(pager) + later, "title": esc(e["title"]), "note": esc(e["note"]),
       "cells": cells, "words": words, "about": about, "data": data, "hide": HIDE_FUTURE})


def archive_page(record, css, about, fonts):
    items = sorted(record.items(), key=lambda kv: -int(kv[0]))
    groups, current = [], None
    for k, e in items:
        d = datetime.date.fromisoformat(e["date"])
        label = d.strftime("%B %Y")
        if label != current:
            groups.append((label, []))
            current = label
        groups[-1][1].append(
            '<li data-date="%s"><a href="/daily/%s/"><span class="no">No. %s</span><span class="t">%s</span>'
            '<span class="d">%s</span></a></li>' % (e["date"], k, k, esc(e["title"]), esc(short_date(d))))
    body = "".join('<h2>%s</h2>\n<ul>\n%s\n</ul>\n' % (esc(label), "\n".join(lis)) for label, lis in groups)
    title = "Past Daily Clue Puzzles: Free Word Search Archive | Hearth & Clue"
    desc = ("Every past puzzle from The Daily Clue, a free daily word search: %d puzzles so far, each a 10x10 grid "
            "with eight words on one theme. Play any of them in your browser, free." % len(record))
    return (head(title, desc, ORIGIN + "/daily/", ORIGIN + "/og-image.png", css, fonts) + "<body>\n" +
            masthead("Past puzzles", "Skip to the list") +
            """  <p class="intro">Missed a day? Every past puzzle is here, newest first. <a href="/">Play today's puzzle</a></p>
  <main class="archive" id="board">
%s  </main>
  %s
</div>
%s
</body>
</html>
""" % (body, about, HIDE_FUTURE))


def sitemap(record):
    urls = ['  <url><loc>%s/daily/</loc><changefreq>daily</changefreq></url>' % ORIGIN]
    for k, e in sorted(record.items(), key=lambda kv: int(kv[0])):
        urls.append("  <url><loc>%s/daily/%s/</loc><lastmod>%s</lastmod></url>" % (ORIGIN, k, e["date"]))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
            "\n".join(urls) + "\n</urlset>\n")


def pin_copy(src_png):
    """The day's pin image, shrunk to 32 colours (looks the same, a third of the size)."""
    from PIL import Image
    im = Image.open(src_png).convert("RGB")
    q = im.quantize(colors=32, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    b = io.BytesIO()
    q.save(b, "PNG", optimize=True)
    return b.getvalue()


def main(index_html="Index.html", root=".", now_utc=None):
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    rec_path = os.path.join(root, "daily", "issues.json")
    try:
        record = json.load(open(rec_path, encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    themes = load_themes(index_html)
    added = record_new_days(record, themes, now_utc)
    check(record)
    write_if_changed(rec_path, json.dumps(dict(sorted(record.items(), key=lambda kv: int(kv[0]))), indent=1) + "\n")

    css, about, fonts = parts_from_home(index_html)
    by_title = {t["title"]: t for t in themes}
    changed = 0
    for k, e in record.items():
        n = int(k)
        pin = os.path.join(root, "daily", k, "pin.png")
        if not os.path.exists(pin):
            src = os.path.join(root, "pins", "%s.png" % k)
            if os.path.exists(src):
                write_if_changed(pin, pin_copy(src))
        t = by_title.get(e["title"], {})
        extra = {"url": t.get("url", e.get("url")), "cta": t.get("cta")}
        page = day_page(n, e, record.get(str(n - 1)), record.get(str(n + 1)), extra, css, about, fonts, os.path.exists(pin))
        changed += write_if_changed(os.path.join(root, "daily", k, "index.html"), page)
    changed += write_if_changed(os.path.join(root, "daily", "index.html"), archive_page(record, css, about, fonts))
    changed += write_if_changed(os.path.join(root, "daily", "sitemap.xml"), sitemap(record))
    print("daily pages: %d days recorded (No. %s to %s), %d new: %s; %d files changed" % (
        len(record), min(record, key=int), max(record, key=int), len(added), added, changed))
    return record, added


if __name__ == "__main__":
    main(*(sys.argv[1:3]))
