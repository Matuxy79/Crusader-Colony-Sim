"""Build the Windows sprite-engine executable and launcher icon."""
from __future__ import annotations

import subprocess
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ICON_SOURCE = ROOT / "assets" / "sprite_engine_icon.png"
ICON_FILE = ROOT / "build" / "sprite_engine_icon.ico"


def make_fallback_icon() -> Image.Image:
    image = Image.new("RGBA", (256, 256), (238, 240, 242, 255))
    draw = ImageDraw.Draw(image)
    dark = (31, 35, 38, 255)
    cyan = (15, 207, 211, 255)
    orange = (255, 145, 8, 255)
    draw.rounded_rectangle((12, 12, 244, 244), radius=48, fill=(238, 240, 242), outline=(180, 184, 188), width=8)
    draw.ellipse((47, 63, 209, 218), fill=dark)
    draw.rectangle((75, 80, 181, 183), fill=cyan)
    draw.rectangle((89, 40, 167, 84), fill=dark)
    draw.rectangle((101, 51, 155, 61), fill=cyan)
    draw.rectangle((91, 100, 120, 133), fill="white")
    draw.rectangle((136, 100, 165, 133), fill="white")
    draw.rectangle((101, 109, 111, 120), fill=dark)
    draw.rectangle((145, 109, 155, 120), fill=dark)
    draw.rectangle((122, 136, 136, 147), fill=dark)
    draw.line((168, 194, 219, 143), fill=orange, width=20)
    draw.polygon(((207, 130), (232, 155), (215, 172), (190, 145)), fill=orange)
    return image


def build_icon() -> None:
    ICON_FILE.parent.mkdir(parents=True, exist_ok=True)
    if ICON_SOURCE.exists():
        image = Image.open(ICON_SOURCE).convert("RGBA")
        print(f"Using launcher artwork: {ICON_SOURCE.relative_to(ROOT)}")
    else:
        image = make_fallback_icon()
        print(f"No {ICON_SOURCE.relative_to(ROOT)} found; using generated fallback icon")
    image.thumbnail((256, 256), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    canvas.save(ICON_FILE, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> None:
    build_icon()
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "CrusaderSpriteEngine",
        "--icon", str(ICON_FILE), str(ROOT / "sprite_engine_v2.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    source_assets = ROOT / "assets"
    distribution_assets = ROOT / "dist" / "assets"
    if source_assets.exists():
        shutil.copytree(source_assets, distribution_assets, dirs_exist_ok=True)
        print(f"Copied external assets to {distribution_assets.relative_to(ROOT)}")


if __name__ == "__main__":
    main()