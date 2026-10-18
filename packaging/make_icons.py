"""Draw the app icon (gradient rounded square with a white pointing hand) and write every size
the exe and the Microsoft Store package need:

  packaging/icon.ico                         the exe icon
  packaging/msix/Assets/*.png                Store tiles and logos

Run:  .venv\\Scripts\\python.exe packaging\\make_icons.py
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gesture_control.icon import glyph, tile  # noqa: E402

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "msix" / "Assets"
def wide(w, h):
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    t = tile(int(h * 0.7))
    out.paste(t, ((w - t.width) // 2, (h - t.height) // 2), t)
    return out


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    tile(256).save(HERE / "icon.ico", sizes=[(s, s) for s in sizes])
    # Store / Start menu assets (scale-100 plus the larger scales Windows picks on high-DPI screens)
    for scale in (100, 125, 150, 200, 400):
        k = scale / 100
        tile(round(150 * k), pad=0.12).save(ASSETS / f"Square150x150Logo.scale-{scale}.png")
        tile(round(44 * k), pad=0.04).save(ASSETS / f"Square44x44Logo.scale-{scale}.png")
        wide(round(310 * k), round(150 * k)).save(ASSETS / f"Wide310x150Logo.scale-{scale}.png")
        tile(round(50 * k)).save(ASSETS / f"StoreLogo.scale-{scale}.png")
    # taskbar / title bar sizes without the tile plate
    for s in (16, 24, 32, 48, 256):
        tile(s).save(ASSETS / f"Square44x44Logo.targetsize-{s}.png")
        glyph(s).save(ASSETS / f"Square44x44Logo.targetsize-{s}_altform-unplated.png")
    print("icons written to", HERE)


if __name__ == "__main__":
    main()
