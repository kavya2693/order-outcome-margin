"""Turn the repo's light matplotlib figures into the dark panels used in the video.

Inverts each image, rotates hue by 180 degrees (so colours keep their hue), blends it onto the
video background (#0b1722), crops the axes area with its tick labels, paints over the
matplotlib legend (the video draws its own) and upscales 2x. No data is redrawn.

Usage: python3 darkmap.py <repo>/outputs <demo>/assets
Needs: numpy, Pillow, matplotlib.
"""

import sys

import numpy as np
from matplotlib.colors import hsv_to_rgb, rgb_to_hsv
from PIL import Image, ImageDraw

src, out = sys.argv[1].rstrip("/") + "/", sys.argv[2].rstrip("/") + "/"
BG = (0x0B, 0x17, 0x22)

# figure -> (output name, crop box incl. tick labels, legend box to paint over, in source pixels)
# Axes spines found at x 122..1415, y 44..434 (daily_margin.png, 1440x480) and
# x 133..826, y 44..527 (policy_frontier.png, 960x600), both written by order_margin/plots.py.
JOBS = {
    "daily_margin.png": ("plot-daily.png", (38, 38, 1422, 462), (1124, 48, 1412, 138)),
    "policy_frontier.png": ("plot-frontier.png", (38, 38, 960, 560), (136, 446, 446, 524)),
}


def dark(path: str) -> Image.Image:
    im = np.asarray(Image.open(path).convert("RGB")).astype(float) / 255
    hsv = rgb_to_hsv(1 - im)
    hsv[..., 0] = (hsv[..., 0] + 0.5) % 1.0
    bg = np.array(BG) / 255
    d = bg + hsv_to_rgb(hsv) * (1 - bg)
    return Image.fromarray((d * 255).clip(0, 255).astype(np.uint8))


for name, (dst, box, legend) in JOBS.items():
    img = dark(src + name)
    ImageDraw.Draw(img).rectangle(legend, fill=BG)
    c = img.crop(box)
    c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS)
    c.save(out + dst)
    print(out + dst, c.size)
