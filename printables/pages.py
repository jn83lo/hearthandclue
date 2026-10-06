"""HTML for a printable pack: one hub page and one page per puzzle.

Plain static pages. Everything a visitor came for (the print buttons) is at
the top; there is no sign-up and nothing to scroll past.
"""
import html
import json
from urllib.parse import quote

import ws
from pdfs import PROMISED, WORD_PT

ORIGIN = "https://hearthandclue.com"
V = "1"   # bump to refresh cached css/js
FONTS = ("https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700"
         "&family=Fraunces:opsz,wght@72,600;72,700&family=Spectral:ital,wght@0,400;0,600;1,400&display=swap")


def esc(s):
    return html.escape(str(s), quote=True)


def pdf_name(pack, puz, paper):
    return "%s-word-search-large-print-%s.pdf" % (puz["slug"], paper)


def pack_pdf_name(pack, paper):
    return "%d-%s-word-searches-large-print-%s.pdf" % (len(pack["puzzles"]), pack["season"].lower(), paper)


def urls(pack, puz=None):
    base = "/%s/" % pack["slug"]
    if puz is None:
        return {"page": base, "letter": base + "pdf/" + pack_pdf_name(pack, "letter"),
                "a4": base + "pdf/" + pack_pdf_name(pack, "a4"), "og": base + "img/og.png",
                "pin": base + "pins/hub-1.png"}
    return {"page": base + puz["slug"] + "/", "letter": base + "pdf/" + pdf_name(pack, puz, "letter"),
            "a4": base + "pdf/" + pdf_name(pack, puz, "a4"), "img": base + "img/%s.png" % puz["slug"],
            "thumb": base + "img/%s-s.png" % puz["slug"], "pin": base + "pins/%s.png" % puz["slug"]}


def meta_line(puz):
    spec = ws.LEVELS[puz["level"]]
    n = spec["size"]
    return "%d by %d grid, %d words, %d pt letters" % (n, n, len(puz["words"]), PROMISED[puz["level"]])


def _head(title, desc, canonical, image, ld):
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>%(t)s</title>
<meta name="description" content="%(d)s">
<meta name="theme-color" content="#F8F3ED">
<link rel="canonical" href="%(c)s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Hearth &amp; Clue">
<meta property="og:title" content="%(t)s">
<meta property="og:description" content="%(d)s">
<meta property="og:url" content="%(c)s">
<meta property="og:image" content="%(i)s">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="%(f)s" rel="stylesheet">
<link rel="stylesheet" href="/assets/printables.css?v=%(v)s">
<script type="application/ld+json">%(ld)s</script>
</head>
<body>
<a class="skip-link" href="#main">Skip to the puzzles</a>
<div class="wrap">
<p class="brand"><a href="/">Hearth &amp; Clue</a></p>
""" % {"t": esc(title), "d": esc(desc), "c": esc(canonical), "i": esc(image), "f": esc(FONTS), "v": V,
       "ld": json.dumps(ld, ensure_ascii=True).replace("</", "<\\/")}


def _book(pack):
    b = pack["book"]
    return """<section class="book" aria-labelledby="book-h">
<h2 id="book-h">Want more than ten?</h2>
<p>%(blurb)s</p>
<div class="btn-row"><a class="btn btn-primary" href="%(u)s" target="_blank" rel="noopener" data-ev="print_book">See %(label)s on Etsy</a></div>
</section>
""" % {"blurb": esc(b["blurb"]), "u": esc(b["url"]), "label": esc(b["label"])}


def _foot(pack):
    return """<footer class="foot">
<p>Made by <a href="/">Hearth &amp; Clue</a>. Every puzzle tells a story.</p>
<p><a href="/">The Daily Clue: a free word search online, new every day</a> &middot; <a href="/privacy">Privacy</a></p>
<p>&copy; %d Hearth &amp; Clue. Free to print for home, classroom, library and care-home use. Not for resale.</p>
</footer>
</div>
<div aria-live="polite" class="sr-only" id="live"></div>
<script src="/assets/printables.js?v=%s" defer></script>
</body>
</html>
""" % (pack["year"], V)


def _card(pack, puz):
    u = urls(pack, puz)
    spec = ws.LEVELS[puz["level"]]
    return """<article class="card">
<a href="%(page)s"><img class="thumb" src="%(thumb)s" width="360" height="466" loading="lazy" alt="%(alt)s"></a>
<h3><a href="%(page)s">%(title)s</a></h3>
<p class="meta">%(meta)s</p>
<div class="links">
<a href="%(letter)s" data-ev="print_pdf">US Letter</a>
<a href="%(a4)s" data-ev="print_pdf">A4</a>
<a class="go" href="%(page)s#play">Play online</a>
</div>
</article>
""" % {"page": esc(u["page"]), "thumb": esc(u["thumb"]), "letter": esc(u["letter"]), "a4": esc(u["a4"]),
       "title": esc(puz["title"]), "meta": esc("%d words, %d pt letters" % (len(puz["words"]), PROMISED[puz["level"]])),
       "alt": esc("%s word search: a %d by %d grid of large letters with %d words to find"
                  % (puz["title"], spec["size"], spec["size"], len(puz["words"])))}


def hub(pack):
    total = len(pack["puzzles"])
    u = urls(pack)
    season = pack["season"]
    title = "Free Printable %s Word Searches - Large Print, %d Puzzles | Hearth & Clue" % (season, total)
    sizes = sorted({PROMISED[p["level"]] for p in pack["puzzles"]})
    desc = ("%d free printable %s word searches in large print: %d to %d point letters, three levels, "
            "answer keys, US Letter and A4. No sign-up, no ads." % (total, season, sizes[0], sizes[-1]))
    ld = {"@context": "https://schema.org", "@type": "CollectionPage",
          "name": "Free Printable %s Word Searches (Large Print)" % season, "description": desc,
          "url": ORIGIN + u["page"], "isAccessibleForFree": True,
          "publisher": {"@type": "Organization", "name": "Hearth & Clue", "url": ORIGIN + "/"},
          "hasPart": [{"@type": "CreativeWork", "name": p["search"], "url": ORIGIN + urls(pack, p)["page"]}
                      for p in pack["puzzles"]]}
    save = ("https://www.pinterest.com/pin/create/button/?url=%s&media=%s&description=%s"
            % (quote(ORIGIN + u["page"], safe=""), quote(ORIGIN + u["pin"], safe=""),
               quote("Free printable %s word searches - large print, %d puzzles with answer keys" % (season, total), safe="")))
    out = [_head(title, desc, ORIGIN + u["page"], ORIGIN + u["og"], ld)]
    out.append("""<main id="main">
<header class="top">
<p class="kicker">Free &middot; Large print &middot; Answer keys</p>
<h1>Free Printable %(season)s Word Searches</h1>
<div class="rule"></div>
<p class="lede">%(total)d %(season)s word searches you can print right now. No sign-up, no ads, and no clip art eating your ink.</p>
<div class="btn-row">
<a class="btn btn-primary" href="%(letter)s" data-ev="print_pdf">All %(total)d puzzles: US Letter<small>PDF, %(pages)d pages with answers</small></a>
<a class="btn btn-primary" href="%(a4)s" data-ev="print_pdf">All %(total)d puzzles: A4<small>PDF, %(pages)d pages with answers</small></a>
</div>
<p class="fine">US Letter for the United States and Canada. A4 for almost everywhere else.</p>
<p class="fine" style="margin-top:8px"><a href="%(save)s" target="_blank" rel="noopener" data-ev="print_save">Save these to Pinterest for later</a></p>
</header>

<ul class="facts">
<li><strong>Large print you can measure.</strong> Grid letters are %(sz)s point. Word lists are %(wl)d point.</li>
<li><strong>Three levels.</strong> Easy runs across and down only. Hard uses every direction.</li>
<li><strong>An answer key for every puzzle.</strong></li>
<li><strong>Black and white.</strong> One clean page per puzzle, in US Letter and A4.</li>
<li><strong>Checked by computer.</strong> Every word is in its grid exactly once.</li>
<li><strong>Made to be read.</strong> Set in Atkinson Hyperlegible, a typeface designed for readers with low vision.</li>
</ul>
""" % {"season": esc(season), "total": total, "letter": esc(u["letter"]), "a4": esc(u["a4"]),
       "pages": 1 + total + -(-total // 2), "wl": int(WORD_PT), "save": esc(save),
       "sz": esc(", ".join(str(s) for s in sorted(sizes, reverse=True)[:-1]) + " or " + str(sizes[0]))})
    for level in ("easy", "medium", "hard"):
        group = [p for p in pack["puzzles"] if p["level"] == level]
        if not group:
            continue
        spec = ws.LEVELS[level]
        out.append("""<div class="level-head"><h2>%s</h2><span>%d pt letters, %d by %d grid. %s</span></div>
<div class="cards">
""" % (esc(spec["label"]), PROMISED[level], spec["size"], spec["size"], esc(spec["rule"])))
        out.extend(_card(pack, p) for p in group)
        out.append("</div>\n")
    out.append(_book(pack))
    out.append("""<section class="plain">
<h2>Using them with a group</h2>
<p>You are welcome to print and photocopy these pages for a classroom, a library, a club or a care home. Please do not sell them or post the files somewhere else; link to this page instead.</p>
<h2>Questions</h2>
<dl class="faq">
<dt>How do I print one?</dt>
<dd>Choose a paper size and the PDF opens. Print it at 100%% (sometimes called &ldquo;actual size&rdquo;) so the letters stay the size we promise.</dd>
<dt>Is it really free?</dt>
<dd>Yes. There is no email address to give and no account to make.</dd>
<dt>Where are the answers?</dt>
<dd>Each single puzzle has its answer on page 2. In the full pack the answers are at the back.</dd>
<dt>Can I play on a phone or tablet instead?</dt>
<dd>Yes. Every puzzle has a <em>Play online</em> button, and there is a new word search every day at <a href="/">The Daily Clue</a>.</dd>
</dl>
</section>
</main>
""")
    out.append(_foot(pack))
    return "".join(out)


def puzzle(pack, puz, built, index):
    total = len(pack["puzzles"])
    u, hubu = urls(pack, puz), urls(pack)
    spec = ws.LEVELS[puz["level"]]
    n = spec["size"]
    title = "%s - Free Printable, Large Print | Hearth & Clue" % puz["search"]
    desc = ("Free printable %s in large print: %d words in a %d by %d grid, %d point letters, answer key included. "
            "%s US Letter and A4, or play it online." % (puz["search"].lower(), len(puz["words"]), n, n,
                                                          PROMISED[puz["level"]], spec["rule"]))
    ld = {"@context": "https://schema.org", "@type": "CreativeWork", "name": puz["search"],
          "alternateName": puz["title"], "description": desc, "url": ORIGIN + u["page"],
          "image": ORIGIN + u["img"], "isAccessibleForFree": True, "genre": "Word search puzzle",
          "isPartOf": {"@type": "CollectionPage", "url": ORIGIN + hubu["page"]},
          "publisher": {"@type": "Organization", "name": "Hearth & Clue", "url": ORIGIN + "/"}}
    prev_p = pack["puzzles"][index - 2] if index > 1 else None
    next_p = pack["puzzles"][index] if index < total else None
    save = ("https://www.pinterest.com/pin/create/button/?url=%s&media=%s&description=%s"
            % (quote(ORIGIN + u["page"], safe=""), quote(ORIGIN + u["pin"], safe=""),
               quote("%s - free printable, large print, answer key included" % puz["search"], safe="")))
    words = sorted(puz["words"])
    data = json.dumps({"grid": built["grid"], "words": words}, ensure_ascii=True, separators=(",", ":"))
    out = [_head(title, desc, ORIGIN + u["page"], ORIGIN + u["img"], ld)]
    out.append("""<p class="crumb"><a href="%(hub)s">&larr; All %(total)d %(season)s word searches</a></p>
<main id="main">
<header class="top">
<p class="kicker">Free printable &middot; Large print &middot; %(level)s</p>
<h1>%(search)s</h1>
<div class="rule"></div>
<p class="note">%(note)s</p>
<div class="btn-row">
<a class="btn btn-primary" href="%(letter)s" data-ev="print_pdf">Print: US Letter<small>PDF with answer key</small></a>
<a class="btn btn-primary" href="%(a4)s" data-ev="print_pdf">Print: A4<small>PDF with answer key</small></a>
</div>
<p class="fine">%(meta)s. %(rule)s</p>
</header>
<a href="%(letter)s" data-ev="print_pdf"><img class="preview" src="%(img)s" width="935" height="1210" alt="%(alt)s"></a>
<p class="fine" style="margin-top:14px"><a href="%(save)s" target="_blank" rel="noopener" data-ev="print_save">Save this puzzle to Pinterest</a></p>

<section class="play" id="play" aria-labelledby="play-h">
<h2 id="play-h">Or play it here</h2>
<p>Drag across a word, or tap its first letter and then its last.</p>
<p class="status">Found 0 of %(nwords)d</p>
<div class="won" hidden><h3>All %(nwords)d found.</h3><p>Nicely done. There are <a href="%(hub)s">%(others)d more here</a>, and a new puzzle every day at <a href="/">The Daily Clue</a>.</p></div>
<div class="board"><div class="grid"></div></div>
<ul class="wordlist"></ul>
<div class="btn-row"><button class="btn btn-ghost" type="button" data-reset disabled>Start over</button></div>
<noscript><p class="fine">The online version needs JavaScript. The printable PDF works without it.</p></noscript>
</section>

<h2>The words</h2>
<p class="words-text">%(words)s</p>
<nav class="pager" aria-label="More puzzles">
%(prev)s
%(next)s
</nav>
""" % {"hub": esc(hubu["page"]), "total": total, "season": esc(pack["season"]), "level": esc(spec["label"]),
       "search": esc(puz["search"]), "note": esc(puz["note"]), "letter": esc(u["letter"]), "a4": esc(u["a4"]),
       "meta": esc(meta_line(puz)[0].upper() + meta_line(puz)[1:]), "rule": esc(spec["rule"]), "img": esc(u["img"]),
       "alt": esc("The %s puzzle page: a %d by %d grid of large letters with %d words listed underneath"
                  % (puz["search"], n, n, len(puz["words"]))),
       "save": esc(save), "nwords": len(words), "others": total - 1, "words": esc(", ".join(words)),
       "prev": ('<a href="%s">&larr; %s</a>' % (esc(urls(pack, prev_p)["page"]), esc(prev_p["title"]))) if prev_p else "<span></span>",
       "next": ('<a href="%s">%s &rarr;</a>' % (esc(urls(pack, next_p)["page"]), esc(next_p["title"]))) if next_p else "<span></span>"})
    out.append(_book(pack))
    out.append("</main>\n")
    out.append('<script type="application/json" id="puzzle-data">%s</script>\n' % data.replace("</", "<\\/"))
    out.append(_foot(pack))
    return "".join(out)
