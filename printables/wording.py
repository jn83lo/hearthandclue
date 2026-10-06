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
