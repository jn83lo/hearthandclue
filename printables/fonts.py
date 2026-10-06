"""Fonts for the printable packs. Fetched once from google/fonts at a pinned
commit (all three families are SIL Open Font License, which allows embedding
in PDFs and images), then cached in printables/fonts/.

  Atkinson Hyperlegible - grid letters, word lists, all reading text. Designed
                          by the Braille Institute for low-vision readers.
  Fraunces              - titles (the site's display face). Variable font, so a
                          static Bold is cut from it with fontTools.
  Spectral              - small italic accents only.
"""
import os
import urllib.request

PIN = "7085eb89a950e85db5b166b7a58d414544b4140c"
BASE = "https://raw.githubusercontent.com/google/fonts/%s/ofl/" % PIN
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.environ.get("PRINTABLES_FONTS", os.path.join(HERE, "fonts"))

SOURCES = {
    "Atkinson-Regular.ttf": "atkinsonhyperlegible/AtkinsonHyperlegible-Regular.ttf",
    "Atkinson-Bold.ttf": "atkinsonhyperlegible/AtkinsonHyperlegible-Bold.ttf",
    "Fraunces-VF.ttf": "fraunces/Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf",
    "Spectral-Italic.ttf": "spectral/Spectral-Italic.ttf",
    "Spectral-SemiBold.ttf": "spectral/Spectral-SemiBold.ttf",
}


def path(name):
    return os.path.join(FONT_DIR, name)


_ready = False


def _ps_name(file_path):
    from fontTools.ttLib import TTFont
    return TTFont(file_path, lazy=True)["name"].getDebugName(6)


def ensure():
    """Download anything missing and cut the static Fraunces weights."""
    global _ready
    if _ready:
        return FONT_DIR
    os.makedirs(FONT_DIR, exist_ok=True)
    for name, rel in SOURCES.items():
        if not (os.path.exists(path(name)) and os.path.getsize(path(name)) > 10000):
            urllib.request.urlretrieve(BASE + rel, path(name))
    for name, wght, style in (("Fraunces-Bold.ttf", 700, "Bold"), ("Fraunces-SemiBold.ttf", 600, "SemiBold")):
        if not (os.path.exists(path(name)) and _ps_name(path(name)) == "Fraunces-" + style):
            from fontTools.ttLib import TTFont
            from fontTools.varLib.instancer import instantiateVariableFont
            # recalcTimestamp=False keeps the source font's own date in the cut,
            # so building again on another day does not change the PDFs.
            vf = TTFont(path("Fraunces-VF.ttf"), recalcTimestamp=False)
            inst = instantiateVariableFont(vf, {"wght": wght, "opsz": 72, "SOFT": 0, "WONK": 0})
            # The source file calls itself "Fraunces 9pt Black" and so would
            # every cut. Name each cut for what it is, so that two cuts used
            # in one PDF can never be taken for the same font.
            names = inst["name"]
            for rec in list(names.names):
                if rec.nameID in (3, 4, 6, 17):
                    text = rec.toUnicode().replace("9pt Black", style).replace("9ptBlack", style).replace("Black", style)
                    names.setName(text, rec.nameID, rec.platformID, rec.platEncID, rec.langID)
            inst.save(path(name))
    _ready = True
    return FONT_DIR


def register_pdf():
    """Register the faces with reportlab under short names."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    ensure()
    for short, name in (("Atk", "Atkinson-Regular.ttf"), ("AtkB", "Atkinson-Bold.ttf"),
                        ("Fr", "Fraunces-Bold.ttf"), ("FrS", "Fraunces-SemiBold.ttf"),
                        ("SpI", "Spectral-Italic.ttf"), ("SpS", "Spectral-SemiBold.ttf")):
        pdfmetrics.registerFont(TTFont(short, path(name)))
