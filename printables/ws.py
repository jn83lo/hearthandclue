"""Word-search engine for the printable packs.

Builds a grid from a word list, deterministically from a seed, and then
re-verifies the finished grid from scratch. A puzzle is only accepted when:

  * every listed word is in the grid EXACTLY once, counting all eight
    directions (so there is never a second, accidental copy to argue about);
  * every listed word runs in a direction its level allows;
  * no rude or upsetting word has formed by accident anywhere in the grid;
  * the grid is square and A-Z only.

Lessons carried over from the book toolkit (booktools/): word lists are A-Z
only (a book once shipped SINCE1987 with digits in the grid), no word may be
longer than the grid, and "checked" means words were really counted - verify()
returns how many it checked so a caller can refuse a silent zero.
"""
import random

E, S_, SE, NE = (0, 1), (1, 0), (1, 1), (-1, 1)
W, N, NW, SW = (0, -1), (-1, 0), (-1, -1), (1, -1)
ALL8 = [E, S_, SE, NE, W, N, NW, SW]

LEVELS = {
    "easy": {
        "label": "Easy", "size": 12, "dirs": [E, S_],
        "rule": "Words run across and down. Nothing is backwards or diagonal.",
        "short": "across and down only",
    },
    "medium": {
        "label": "Medium", "size": 14, "dirs": [E, S_, SE, NE],
        "rule": "Words run across, down and diagonally. Nothing is backwards.",
        "short": "across, down and diagonal",
    },
    "hard": {
        "label": "Hard", "size": 15, "dirs": ALL8,
        "rule": "Words run in every direction, including backwards.",
        "short": "every direction, including backwards",
    },
}

# Filler letters roughly follow English, so the filler does not stand out from
# the words and the grid is not littered with Q, X and Z.
_FREQ = {
    "E": 11, "A": 8, "R": 7, "I": 7, "O": 7, "T": 7, "N": 6, "S": 6, "L": 5,
    "C": 4, "U": 4, "D": 4, "P": 3, "M": 3, "H": 3, "G": 3, "B": 2, "F": 2,
    "Y": 2, "W": 2, "K": 2, "V": 1, "X": 1, "Z": 1, "J": 1, "Q": 1,
}
_FILL = "".join(ch * n for ch, n in sorted(_FREQ.items()))

# Words that must never appear by accident. Occurrences that sit wholly inside
# a listed word (the ASS in GLASS) are ignored; anything else is re-rolled.
BLOCKLIST = sorted(set("""
ANAL ANUS ARSE ASS BASTARD BITCH BOOB BOLLOCK BONER BUGGER BUM BUTT CLIT COCK
COON CRAP CUM CUNT DAMN DEAD DICK DIE DIED DIKE DILDO DYKE FAG FART FECK FUCK
FUK GAY GOOK HELL HOMO HORNY JERK JEW JIZZ KIKE KILL KKK KNOB LEZ MILF MUFF
NAZI NIG NIP NOB NUDE ORGY PAKI PEE PENIS PISS POO POOP PORN PRICK PUBE PUKE
PUSSY QUEER RAPE RETARD SCUM SEX SHAG SHIT SLAG SLUT SMUT SNOT SOD SPIC SUCK
SUICIDE TARD TIT TITS TURD TWAT VAG WANK WHORE WOG
""".split()))


def _line(r, c, dr, dc, length):
    return [(r + dr * i, c + dc * i) for i in range(length)]


def _axis(d):
    """Two opposite directions share an axis (E and W lie on the same line)."""
    dr, dc = d
    return (dr, dc) if (dr, dc) > (-dr, -dc) else (-dr, -dc)


def occurrences(grid, word):
    """Every place `word` reads in the grid, in any of the eight directions."""
    n, L, out = len(grid), len(word), []
    for dr, dc in ALL8:
        for r in range(n):
            er = r + dr * (L - 1)
            if not 0 <= er < n:
                continue
            for c in range(n):
                ec = c + dc * (L - 1)
                if not 0 <= ec < n:
                    continue
                if all(grid[r + dr * i][c + dc * i] == word[i] for i in range(L)):
                    out.append((r, c, dr, dc))
    return out


def check_words(words, size):
    """Content rules, checked before any grid is built. Returns a list of problems."""
    bad = []
    seen = set()
    for w in words:
        if not (w.isascii() and w.isalpha() and w.isupper()):
            bad.append("%s: letters A-Z only" % w)
        if len(w) < 4:
            bad.append("%s: shorter than 4 letters" % w)
        if len(w) > size:
            bad.append("%s: longer than the %d-letter grid" % (w, size))
        if w in seen:
            bad.append("%s: listed twice" % w)
        seen.add(w)
        if w == w[::-1]:
            bad.append("%s: reads the same backwards" % w)
        if w in BLOCKLIST:
            bad.append("%s: is on the blocklist" % w)
    for a in words:
        for b in words:
            if a != b and (a in b or a[::-1] in b):
                bad.append("%s hides inside %s" % (a, b))
    return bad


def _place(words, size, dirs, rng):
    grid = [[None] * size for _ in range(size)]
    axes = [[set() for _ in range(size)] for _ in range(size)]
    used = {d: 0 for d in dirs}
    placed = {}
    for w in sorted(words, key=lambda x: (-len(x), x)):
        options = {d: [] for d in dirs}
        for d in dirs:
            dr, dc = d
            ax = _axis(d)
            for r in range(size):
                for c in range(size):
                    er, ec = r + dr * (len(w) - 1), c + dc * (len(w) - 1)
                    if not (0 <= er < size and 0 <= ec < size):
                        continue
                    overlap, ok = 0, True
                    for i, (rr, cc) in enumerate(_line(r, c, dr, dc, len(w))):
                        g = grid[rr][cc]
                        if g is None:
                            continue
                        # crossings only: never run along a line another word is on
                        if g != w[i] or ax in axes[rr][cc]:
                            ok = False
                            break
                        overlap += 1
                    if ok:
                        options[d].append((overlap, r, c))
        live = [d for d in dirs if options[d]]
        if not live:
            return None
        # spread the words evenly over the allowed directions
        fewest = min(used[d] for d in live)
        d = rng.choice([x for x in live if used[x] == fewest])
        opts = options[d]
        crossing = [o for o in opts if o[0] > 0]
        pool = crossing if crossing and rng.random() < 0.45 else opts
        _, r, c = rng.choice(pool)
        dr, dc = d
        for i, (rr, cc) in enumerate(_line(r, c, dr, dc, len(w))):
            grid[rr][cc] = w[i]
            axes[rr][cc].add(_axis(d))
        used[d] += 1
        placed[w] = (r, c, dr, dc)
    return grid, placed


def _problems(grid, words, placed):
    """Cells that take part in an accidental extra word or a blocklisted word."""
    word_cells = {}
    for w, (r, c, dr, dc) in placed.items():
        word_cells[w] = (set(_line(r, c, dr, dc, len(w))), _axis((dr, dc)))
    out = []
    for w in words:
        for occ in occurrences(grid, w):
            if occ != placed[w]:
                out.append(_line(occ[0], occ[1], occ[2], occ[3], len(w)))
    for b in BLOCKLIST:
        for (r, c, dr, dc) in occurrences(grid, b):
            cells = set(_line(r, c, dr, dc, len(b)))
            inside = any(cells <= wc and _axis((dr, dc)) == ax for wc, ax in word_cells.values())
            if not inside:
                out.append(sorted(cells))
    return out


def generate(words, level, seed):
    """Return {"grid": [...rows...], "placed": {word: (r, c, dr, dc)}, "seed": n}."""
    spec = LEVELS[level]
    size, dirs = spec["size"], spec["dirs"]
    issues = check_words(words, size)
    if issues:
        raise ValueError("word list rejected: " + "; ".join(issues))
    for attempt in range(400):
        rng = random.Random("%s/%d" % (seed, attempt))
        res = _place(words, size, dirs, rng)
        if res is None:
            continue
        grid, placed = res
        fixed = set()
        for (r, c, dr, dc), w in ((v, k) for k, v in placed.items()):
            fixed.update(_line(r, c, dr, dc, len(w)))
        for r in range(size):
            for c in range(size):
                if grid[r][c] is None:
                    grid[r][c] = rng.choice(_FILL)
        ok = False
        for _ in range(600):
            probs = _problems(grid, words, placed)
            if not probs:
                ok = True
                break
            stuck = False
            for cells in probs:
                free = [rc for rc in cells if rc not in fixed]
                if not free:
                    stuck = True  # made only of real words crossing: start again
                    break
                r, c = rng.choice(free)
                grid[r][c] = rng.choice(_FILL)
            if stuck:
                break
        if ok:
            rows = ["".join(row) for row in grid]
            out = {"grid": rows, "placed": placed, "seed": "%s/%d" % (seed, attempt)}
            verify(rows, words, level, placed)
            return out
    raise RuntimeError("could not build a clean grid for seed %r" % (seed,))


def verify(rows, words, level, placed=None):
    """Independent re-check of a finished grid. Raises on any defect.

    Deliberately does not trust the generator: it searches the grid afresh.
    Returns the number of words it checked.
    """
    spec = LEVELS[level]
    size, allowed = spec["size"], set(spec["dirs"])
    if len(rows) != size or any(len(r) != size for r in rows):
        raise AssertionError("grid is not %dx%d" % (size, size))
    for r in rows:
        if not (r.isascii() and r.isalpha() and r.isupper()):
            raise AssertionError("grid has a non A-Z character: %r" % r)
    issues = check_words(words, size)
    if issues:
        raise AssertionError("; ".join(issues))
    grid = [list(r) for r in rows]
    checked = 0
    found = {}
    for w in words:
        occ = occurrences(grid, w)
        if len(occ) != 1:
            raise AssertionError("%s appears %d times (must be exactly once)" % (w, len(occ)))
        r, c, dr, dc = occ[0]
        if (dr, dc) not in allowed:
            raise AssertionError("%s runs in a direction the %s level does not allow" % (w, level))
        if placed is not None and tuple(placed[w]) != occ[0]:
            raise AssertionError("%s: answer key does not match the grid" % w)
        found[w] = occ[0]
        checked += 1
    word_cells = [(set(_line(r, c, dr, dc, len(w))), _axis((dr, dc))) for w, (r, c, dr, dc) in found.items()]
    for b in BLOCKLIST:
        for (r, c, dr, dc) in occurrences(grid, b):
            cells = set(_line(r, c, dr, dc, len(b)))
            if not any(cells <= wc and _axis((dr, dc)) == ax for wc, ax in word_cells):
                raise AssertionError("unwanted word %s at row %d, column %d" % (b, r + 1, c + 1))
    if checked != len(words) or checked == 0:
        raise AssertionError("checked %d of %d words" % (checked, len(words)))
    return checked
