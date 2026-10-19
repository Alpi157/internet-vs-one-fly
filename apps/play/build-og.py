"""Check the committed social frame; capture is performed by the media harness."""
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[2]
image=Image.open(root/'apps/play/public/og-image.png')
assert image.size == (1200,630)
