"""Preview images and Pinterest pins for a printable pack (Pillow).

Everything is drawn at twice the final size and scaled down, so shapes and
type have smooth edges. Pins are 1000x1500 (Pinterest's 2:3). There are two
kinds: pin() draws everything itself on a flat colour; photo_pin() lays the
real pages on one of the table photographs in printables/photos/.
"""
import math
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import fonts

SS = 2  # supersampling factor

SCHEMES = {
    "night":   {"bg": (36, 27, 47),    "title": (248, 243, 237), "accent": (240, 138, 36),
                "chip": (240, 138, 36),  "chip_text": (36, 27, 47),    "foot": (248, 243, 237),
                "sub": (214, 200, 222),  "ink": (20, 14, 28),          "moon": (247, 226, 170)},
    "pumpkin": {"bg": (212, 94, 26),   "title": (255, 250, 242), "accent": (43, 28, 18),
                "chip": (255, 250, 242), "chip_text": (43, 28, 18),    "foot": (255, 250, 242),
                "sub": (255, 226, 200),  "ink": (43, 28, 18),          "moon": (255, 214, 150)},
    "cream":   {"bg": (248, 243, 237), "title": (51, 48, 44),    "accent": (196, 86, 26),
                "chip": (51, 48, 44),    "chip_text": (248, 243, 237), "foot": (142, 42, 42),
                "sub": (95, 90, 82),     "ink": (51, 48, 44),          "moon": (232, 217, 195)},
}

# A bat, as points on a unit square: wing tip, wing peak, ears, and a
# scalloped lower edge. Left to right along the top, then back along the bottom.
_BAT = [(0.00, 0.26), (0.17, 0.04), (0.33, 0.22), (0.42, 0.20), (0.44, 0.02), (0.48, 0.15),
        (0.52, 0.15), (0.56, 0.02), (0.58, 0.20), (0.67, 0.22), (0.83, 0.04), (1.00, 0.26),
        (0.91, 0.40), (0.83, 0.64), (0.73, 0.44), (0.64, 0.68), (0.56, 0.50), (0.50, 0.80),
        (0.44, 0.50), (0.36, 0.68), (0.27, 0.44), (0.17, 0.64), (0.09, 0.40)]


def font(name, size):
    fonts.ensure()
    return ImageFont.truetype(fonts.path(name), int(round(size * SS)))


def render_page(pdf_path, page_no, dpi):
    """Rasterise one PDF page (1-based). Poppler if installed, else PyMuPDF."""
    import shutil
    if shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "p")
            subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page_no), "-l", str(page_no), "-gray", "-png", pdf_path, base], check=True)
            name = [f for f in os.listdir(tmp) if f.endswith(".png")][0]
            return Image.open(os.path.join(tmp, name)).convert("L").copy()
    import fitz
    doc = fitz.open(pdf_path)
    pix = doc[page_no - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def save_preview(pdf_path, out_big, out_small):
    """The page-1 preview used on the site: 935 wide, plus a 360-wide thumbnail."""
    page = render_page(pdf_path, 1, 220)
    big = page.resize((935, 1210), Image.LANCZOS)
    big.save(out_big, optimize=True)
    page.resize((360, 466), Image.LANCZOS).save(out_small, optimize=True)


def _text_w(d, text, f, tracking=0):
    return d.textlength(text, font=f) + tracking * SS * max(0, len(text) - 1)


def _draw_text(d, x, y, text, f, fill, tracking=0, anchor="l"):
    w = _text_w(d, text, f, tracking)
    if anchor == "m":
        x -= w / 2.0
    if not tracking:
        d.text((x, y), text, font=f, fill=fill)
        return w
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + tracking * SS
    return w


def _balanced(d, text, f, width):
    """Wrap to at most two lines of similar length (no lonely last word)."""
    words = text.split()
    if d.textlength(text, font=f) <= width or len(words) < 2:
        return [text]
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        wa, wb = d.textlength(a, font=f), d.textlength(b, font=f)
        if max(wa, wb) <= width and (best is None or abs(wa - wb) < best[0]):
            best = (abs(wa - wb), [a, b])
    return best[1] if best else _wrap(d, text, f, width)


def _wrap(d, text, f, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if d.textlength(trial, font=f) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def _bat(d, cx, cy, w, fill, tilt=0.0):
    h = w * 0.62
    pts = []
    for (u, v) in _BAT:
        x, y = (u - 0.5) * w, (v - 0.4) * h
        a = math.radians(tilt)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    d.polygon(pts, fill=fill)


def _moon(img, cx, cy, r, fill, bg):
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    o = r * 0.42
    d.ellipse((cx - r + o, cy - r - o * 0.55, cx + r + o, cy + r - o * 0.55), fill=bg)


def _pumpkin(d, cx, cy, w, body=(226, 113, 29), rib=(184, 82, 15), stem=(86, 98, 52)):
    h = w * 0.78
    d.rounded_rectangle((cx - w * 0.07, cy - h * 0.72, cx + w * 0.07, cy - h * 0.38), radius=w * 0.03, fill=stem)
    for dx, ww in ((-0.30, 0.44), (0.30, 0.44), (-0.14, 0.46), (0.14, 0.46), (0.0, 0.42)):
        x0, x1 = cx + (dx - ww / 2) * w, cx + (dx + ww / 2) * w
        d.ellipse((x0, cy - h / 2, x1, cy + h / 2), fill=body, outline=rib, width=max(2, int(w * 0.018)))


def _page_card(page_img, width, angle, shadow=(0, 0, 0, 110)):
    """A white page with a soft shadow, rotated a little. Returns an RGBA image."""
    w = int(width)
    h = int(page_img.height * w / page_img.width)
    page = page_img.convert("RGB").resize((w, h), Image.LANCZOS)
    pad = int(w * 0.09)
    card = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((pad + w * 0.012, pad + w * 0.02, pad + w + w * 0.012, pad + h + w * 0.02), fill=shadow)
    card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(w * 0.022)))
    card.paste(page, (pad, pad))
    return card.rotate(angle, resample=Image.BICUBIC, expand=True)


def pin(out_path, scheme, eyebrow, title, chip, pages, footer_small, pumpkin=True):
    """One 1000x1500 pin. `pages` is a list of 1 to 3 PIL page images, front first."""
    c = SCHEMES[scheme]
    W, H = 1000 * SS, 1500 * SS
    img = Image.new("RGB", (W, H), c["bg"])
    d = ImageDraw.Draw(img)

    # sky: moon and bats, kept clear of the words
    _moon(img, W - 96 * SS, 92 * SS, 58 * SS, c["moon"], c["bg"])
    d = ImageDraw.Draw(img)
    bat = c["ink"] if scheme != "night" else (12, 8, 18)
    _bat(d, 104 * SS, 96 * SS, 132 * SS, bat, tilt=-10)
    _bat(d, 232 * SS, 56 * SS, 74 * SS, bat, tilt=12)

    # words, stacked at the top
    y = 166 * SS
    ef, et = font("Atkinson-Bold.ttf", 36), 6
    if _text_w(d, eyebrow, ef, et) > 700 * SS:
        ef, et = font("Atkinson-Bold.ttf", 33), 5
    _draw_text(d, W / 2, y, eyebrow, ef, c["accent"], tracking=et, anchor="m")
    y += 58 * SS
    size = 96
    while True:
        f = font("Fraunces-Bold.ttf", size)
        lines = _balanced(d, title, f, 900 * SS)
        if len(lines) <= 2 or size <= 60:
            break
        size -= 4
    lh = size * 1.06 * SS
    for line in lines:
        _draw_text(d, W / 2, y, line, f, c["title"], anchor="m")
        y += lh
    y += 22 * SS
    cf = font("Atkinson-Bold.ttf", 31)
    cw = _text_w(d, chip, cf, 1.5)
    ch = 62 * SS
    d.rounded_rectangle((W / 2 - cw / 2 - 30 * SS, y, W / 2 + cw / 2 + 30 * SS, y + ch), radius=ch / 2, fill=c["chip"])
    _draw_text(d, W / 2, y + 12 * SS, chip, cf, c["chip_text"], tracking=1.5, anchor="m")
    y += ch + 26 * SS

    # the pages
    foot_top = H - 150 * SS
    room = foot_top - y
    width = min(640 * SS, (room - 20 * SS) / 1.294 / 1.04)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if len(pages) >= 3:
        back2 = _page_card(pages[2], width * 0.92, -8)
        layer.alpha_composite(back2, (int(W / 2 - back2.width / 2 - width * 0.26), int(y + room / 2 - back2.height / 2 + 10 * SS)))
    if len(pages) >= 2:
        back = _page_card(pages[1], width * 0.94, 7)
        layer.alpha_composite(back, (int(W / 2 - back.width / 2 + width * 0.24), int(y + room / 2 - back.height / 2 + 6 * SS)))
    front = _page_card(pages[0], width, -2.2)
    layer.alpha_composite(front, (int(W / 2 - front.width / 2), int(y + room / 2 - front.height / 2)))
    img.paste(layer, (0, 0), layer)
    d = ImageDraw.Draw(img)
    if pumpkin:
        _pumpkin(d, 128 * SS, foot_top - 84 * SS, 168 * SS)
        _pumpkin(d, 232 * SS, foot_top - 58 * SS, 104 * SS, body=(236, 140, 52))

    # where to get it
    _draw_text(d, W / 2, H - 132 * SS, "hearthandclue.com", font("Fraunces-SemiBold.ttf", 46), c["foot"], anchor="m")
    _draw_text(d, W / 2, H - 70 * SS, footer_small, font("Atkinson-Regular.ttf", 27), c["sub"], anchor="m")
    img.resize((1000, 1500), Image.LANCZOS).save(out_path, optimize=True)


def _paper(page_img, width, angle, tint=(252, 249, 243)):
    """A printed page lying on a table: faintly warm paper and a soft, wide
    shadow. Returns an RGBA image."""
    w = int(width)
    h = int(page_img.height * w / page_img.width)
    grey = page_img.convert("L").resize((w, h), Image.LANCZOS)
    page = Image.merge("RGB", [grey.point(lambda v, t=t: int(v * t / 255)) for t in tint])
    pad = int(w * 0.14)
    card = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    for blur, off, alpha in ((w * 0.045, w * 0.030, 70), (w * 0.012, w * 0.008, 90)):
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle((pad + off * 0.5, pad + off, pad + w + off * 0.5, pad + h + off), fill=(20, 12, 4, alpha))
        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    card.paste(page, (pad, pad))
    return card.rotate(angle, resample=Image.BICUBIC, expand=True)


def _plate(img, box, fill, radius):
    """A solid rounded panel with a soft shadow, for words on top of a photograph."""
    x0, y0, x1, y1 = [int(v) for v in box]
    m = 40 * SS     # room around the panel for its shadow to fade out
    w, h = x1 - x0, y1 - y0
    layer = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((m, m + 6 * SS, m + w, m + h + 10 * SS), radius=radius, fill=(10, 6, 2, 80))
    layer = layer.filter(ImageFilter.GaussianBlur(12 * SS))
    ImageDraw.Draw(layer).rounded_rectangle((m, m, m + w, m + h), radius=radius, fill=tuple(fill) + (255,))
    # keep to the part that lies on the picture
    left, top = max(0, m - x0), max(0, m - y0)
    right, bottom = min(layer.width, img.width - (x0 - m)), min(layer.height, img.height - (y0 - m))
    layer = layer.crop((left, top, right, bottom))
    img.paste(layer, (x0 - m + left, y0 - m + top), layer)


def photo_pin(out_path, photo_path, scheme, eyebrow, title, chip, pages, footer_small, stack=None, foot="centre"):
    """One 1000x1500 pin on a photograph of a table: the real puzzle pages are
    laid on it, with the words on a panel at the top. `pages` is 1 or 2 PIL
    page images, front first. `stack` may move or shrink the pages so that
    something worth seeing in the photograph stays in view."""
    c = SCHEMES[scheme]
    stack = stack or {}
    W, H = 1000 * SS, 1500 * SS
    photo = Image.open(photo_path).convert("RGB")
    k = max(W / photo.width, H / photo.height)
    photo = photo.resize((int(round(photo.width * k)), int(round(photo.height * k))), Image.LANCZOS)
    left, top = (photo.width - W) // 2, (photo.height - H) // 2
    img = photo.crop((left, top, left + W, top + H))
    d = ImageDraw.Draw(img)

    # the words, on a panel across the top
    M = 40 * SS
    ef, et = font("Atkinson-Bold.ttf", 33), 5.5
    if _text_w(d, eyebrow, ef, et) > 760 * SS:
        ef, et = font("Atkinson-Bold.ttf", 30), 4.5
    size = 88
    while True:
        f = font("Fraunces-Bold.ttf", size)
        lines = _balanced(d, title, f, 840 * SS)
        if len(lines) <= 2 or size <= 56:
            break
        size -= 4
    lh = size * 1.06 * SS
    cf = font("Atkinson-Bold.ttf", 29)
    ch = 58 * SS
    panel_h = 84 * SS + len(lines) * lh + 20 * SS + ch + 34 * SS
    _plate(img, (M, M, W - M, M + panel_h), c["bg"], 30 * SS)
    d = ImageDraw.Draw(img)
    y = M + 36 * SS
    _draw_text(d, W / 2, y, eyebrow, ef, c["accent"], tracking=et, anchor="m")
    y += 50 * SS
    for line in lines:
        _draw_text(d, W / 2, y, line, f, c["title"], anchor="m")
        y += lh
    y += 18 * SS
    cw = _text_w(d, chip, cf, 1.5)
    d.rounded_rectangle((W / 2 - cw / 2 - 28 * SS, y, W / 2 + cw / 2 + 28 * SS, y + ch), radius=ch / 2, fill=c["chip"])
    _draw_text(d, W / 2, y + 11 * SS, chip, cf, c["chip_text"], tracking=1.5, anchor="m")

    # the pages, between the two panels
    fh = 112 * SS
    foot_top = H - M - fh
    y0 = M + panel_h + 14 * SS
    room = foot_top - 14 * SS - y0
    width = min(590 * SS, room / 1.294 / 1.07) * stack.get("scale", 1.0)
    pages = pages[:stack.get("pages", 2)]
    cx = W / 2 + stack.get("dx", 0) * SS
    cy = y0 + room / 2 + stack.get("dy", 0) * SS
    if len(pages) >= 2:
        back = _paper(pages[1], width * 0.97, 5.0)
        img.paste(back, (int(cx - back.width / 2 + width * 0.115), int(cy - back.height / 2 + 4 * SS)), back)
        del back
    front = _paper(pages[0], width, stack.get("angle", -2.5))
    img.paste(front, (int(cx - front.width / 2 - (width * 0.045 if len(pages) >= 2 else 0)), int(cy - front.height / 2)), front)
    del front

    # where to get it
    fx = W / 2 if foot == "centre" else M + 290 * SS
    _plate(img, (fx - 290 * SS, foot_top, fx + 290 * SS, foot_top + fh), c["bg"], 26 * SS)
    d = ImageDraw.Draw(img)
    _draw_text(d, fx, foot_top + 12 * SS, "hearthandclue.com", font("Fraunces-SemiBold.ttf", 42), c["foot"], anchor="m")
    _draw_text(d, fx, foot_top + 68 * SS, footer_small, font("Atkinson-Regular.ttf", 25), c["sub"], anchor="m")
    img.resize((1000, 1500), Image.LANCZOS).save(out_path, quality=90, optimize=True)


def og(out_path, eyebrow, title, sub, pages):
    """1200x630 link-preview image."""
    c = SCHEMES["cream"]
    W, H = 1200 * SS, 630 * SS
    img = Image.new("RGB", (W, H), c["bg"])
    d = ImageDraw.Draw(img)
    f = font("Fraunces-Bold.ttf", 66)
    y = 120 * SS
    _draw_text(d, 70 * SS, y - 60 * SS, eyebrow, font("Atkinson-Bold.ttf", 26), c["accent"], tracking=5)
    for line in _wrap(d, title, f, 520 * SS):
        d.text((70 * SS, y), line, font=f, fill=c["title"])
        y += 74 * SS
    y += 18 * SS
    for line in _wrap(d, sub, font("Atkinson-Regular.ttf", 30), 470 * SS):
        d.text((70 * SS, y), line, font=font("Atkinson-Regular.ttf", 30), fill=c["sub"])
        y += 42 * SS
    _draw_text(d, 70 * SS, H - 90 * SS, "hearthandclue.com", font("Fraunces-SemiBold.ttf", 34), c["foot"])
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    back = _page_card(pages[1], 330 * SS, 6)
    layer.alpha_composite(back, (int(W - 440 * SS), int(H / 2 - back.height / 2 + 14 * SS)))
    front = _page_card(pages[0], 350 * SS, -3)
    layer.alpha_composite(front, (int(W - 610 * SS), int(H / 2 - front.height / 2)))
    img.paste(layer, (0, 0), layer)
    img.resize((1200, 630), Image.LANCZOS).save(out_path, optimize=True)
