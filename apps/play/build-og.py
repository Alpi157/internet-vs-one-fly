"""Build a static social card from declared runtime metadata, no invented spikes."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[2]
runtime=json.loads((root/'apps/play/public/data/runtime.json').read_text())
image=Image.new('RGB',(1200,630),'#f6edd9');draw=ImageDraw.Draw(image)
draw.rounded_rectangle((30,30,1170,600),radius=22,fill='#183c31')
font=lambda size: ImageFont.load_default(size=size)
draw.text((75,75),'FLYBENCH / CATCH THE FLY',font=font(23),fill='#e0c18d')
draw.text((75,170),'Six strikes.',font=font(80),fill='#fff7e4')
draw.text((75,270),'One simulated fly.',font=font(70),fill='#fff7e4')
draw.text((78,395),f"{runtime['counts']['N']:,} neurons from measured MaleCNS wiring",font=font(29),fill='#b9dec5')
draw.text((78,450),runtime['status'],font=font(23),fill='#e0c18d')
draw.text((78,535),'alpi157.github.io/internet-vs-one-fly/',font=font(25),fill='#fff7e4')
image.save(root/'apps/play/public/og-image.png',optimize=True)
