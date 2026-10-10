"""Draw the Krypton crystal icon at every size Chrome needs."""
from PIL import Image, ImageDraw, ImageFilter

from config import EXTENSION_DIR


def crystal(size: int) -> Image.Image:
    s = size * 4  # supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 5, fill=(8, 16, 12, 255))
    cx, cy = s / 2, s / 2
    top, mid, bot, w = s * .12, s * .40, s * .90, s * .34
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon([(cx, top), (cx + w, mid), (cx, bot), (cx - w, mid)], fill=(92, 255, 106, 150))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s * .06)))
    d.polygon([(cx, top), (cx + w, mid), (cx, mid)], fill=(182, 255, 59, 255))
    d.polygon([(cx, top), (cx, mid), (cx - w, mid)], fill=(120, 255, 90, 255))
    d.polygon([(cx - w, mid), (cx, mid), (cx, bot)], fill=(47, 245, 138, 255))
    d.polygon([(cx, mid), (cx + w, mid), (cx, bot)], fill=(24, 201, 194, 255))
    d.line([(cx - w, mid), (cx + w, mid)], fill=(230, 255, 240, 200), width=max(1, s // 64))
    return img.resize((size, size), Image.LANCZOS)


def run():
    out = EXTENSION_DIR / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 48, 128):
        crystal(size).save(out / f"icon{size}.png")


if __name__ == "__main__":
    run()
