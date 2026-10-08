"""Small helpers for the words used on pages, on pins and in PDF properties."""

PROPER = ("halloween", "thanksgiving", "christmas", "easter", "valentine")


def mid_sentence(phrase):
    """A title-case phrase made ready for the middle of a sentence: lower case,
    except for names that keep their capital. "Halloween Party Word Search"
    becomes "Halloween party word search", not "halloween party word search"."""
    out = phrase.lower()
    for name in PROPER:
        out = out.replace(name, name.capitalize())
    return out


NUMBERS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
           10: "ten", 11: "eleven", 12: "twelve", 15: "fifteen", 20: "twenty"}


def number_word(n):
    """A small count in words, for a heading such as "Want more than six?"."""
    if n not in NUMBERS:
        raise AssertionError("no word for %d: add it to wording.NUMBERS" % n)
    return NUMBERS[n]
