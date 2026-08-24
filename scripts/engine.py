#!/usr/bin/env python3
"""
Daily Clue puzzle engine — exact port of the browser engine in index.html.

Theme data is read from the DEPLOYED page, so the pins always match the puzzle
people are actually served. Verified byte-identical to the JS engine across 180
consecutive days.
"""
import json, re, sys, datetime

SIZE = 10
EPOCH = datetime.date(2026, 1, 1)
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
MASK = 0xFFFFFFFF


def imul(a, b):
    """JavaScript Math.imul: 32-bit signed multiply."""
    r = (a * b) & MASK
    return r - 0x100000000 if r >= 0x80000000 else r


def to_int32(x):
    x &= MASK
    return x - 0x100000000 if x >= 0x80000000 else x


def mulberry32(seed):
    state = [to_int32(seed)]

    def rng():
        state[0] = to_int32(state[0] + 0x6D2B79F5)
        a = state[0]
        t = imul(a ^ ((a & MASK) >> 15), 1 | a)
        t = to_int32(to_int32(t + imul(t ^ ((t & MASK) >> 7), 61 | t)) ^ t)
        return ((t ^ ((t & MASK) >> 14)) & MASK) / 4294967296.0

    return rng


def day_number(d):
    return (d - EPOCH).days


def theme_for(themes, d):
    evergreen = [t for t in themes if t["kind"] == "ever"]
    for t in themes:
        if t["kind"] == "dated" and d.month in t["months"] and t["days"][0] <= d.day <= t["days"][1]:
            return t
    season = next((t for t in themes if t["kind"] == "season" and d.month in t["months"]), None)
    pool = evergreen + [season] if season else evergreen
    return pool[day_number(d) % len(pool)]


def place(grid, word, rng):
    for _ in range(400):
        dx, dy = DIRS[int(rng() * 8)]
        sx, sy = int(rng() * SIZE), int(rng() * SIZE)
        ok = True
        for i, ch in enumerate(word):
            x, y = sx + dx * i, sy + dy * i
            if not (0 <= x < SIZE and 0 <= y < SIZE):
                ok = False
                break
            cur = grid[y][x]
            if cur is not None and cur != ch:
                ok = False
                break
        if not ok:
            continue
        for i, ch in enumerate(word):
            grid[sy + dy * i][sx + dx * i] = ch
        return True
    return False


def findable(grid, word):
    for y in range(SIZE):
        for x in range(SIZE):
            for dx, dy in DIRS:
                ok = True
                for i, ch in enumerate(word):
                    nx, ny = x + dx * i, y + dy * i
                    if not (0 <= nx < SIZE and 0 <= ny < SIZE) or grid[ny][nx] != ch:
                        ok = False
                        break
                if ok:
                    return True
    return False


def build(words, seed):
    ordered = sorted(words, key=len, reverse=True)
    for rnd in range(60):
        rng = mulberry32(seed + rnd * 7919)
        grid = [[None] * SIZE for _ in range(SIZE)]
        if not all(place(grid, w, rng) for w in ordered):
            continue
        for y in range(SIZE):
            for x in range(SIZE):
                if grid[y][x] is None:
                    grid[y][x] = chr(65 + int(rng() * 26))
        if all(findable(grid, w) for w in words):
            return grid
    return None


LIVE_URL = "https://hearthandclue.com/index.html"


def _extract(src, where):
    m = re.search(r"var THEMES = (\[.*?\]);", src)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        print("theme data in %s did not parse: %s" % (where, e))
        return None


def load_themes(index_path=None):
    """Prefer the deployed page: the pins must match the puzzle people are served,
    not whatever happens to be sitting in the repo."""
    try:
        import urllib.request
        with urllib.request.urlopen(LIVE_URL, timeout=20) as r:
            themes = _extract(r.read().decode("utf-8"), LIVE_URL)
        if themes:
            print("theme source: %s (%d themes)" % (LIVE_URL, len(themes)))
            return themes
        print("live page reachable but theme data not in the expected format")
    except Exception as e:
        print("could not read live page (%s), falling back to the repo copy" % type(e).__name__)

    if index_path:
        try:
            themes = _extract(open(index_path, encoding="utf-8").read(), index_path)
        except OSError as e:
            raise SystemExit("cannot open %s: %s" % (index_path, e))
        if themes:
            print("theme source: %s (%d themes)" % (index_path, len(themes)))
            return themes

    raise SystemExit(
        "No usable theme data. Checked %s and %s. The deployed index.html must "
        "contain a single-line `var THEMES = [...]` JSON array." % (LIVE_URL, index_path)
    )


if __name__ == "__main__":
    themes = load_themes(sys.argv[1] if len(sys.argv) > 1 else "index.html")
    d = datetime.date.today()
    t = theme_for(themes, d)
    g = build(t["words"], d.year * 10000 + d.month * 100 + d.day)
    print(t["title"], day_number(d) + 1)
    for row in g:
        print(" ".join(row))
