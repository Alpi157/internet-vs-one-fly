from pathlib import Path
from PIL import Image
import hashlib,json,sys
root=Path(__file__).resolve().parents[3];frames=Path('/tmp/flybench-v2k-media-frames' if '--v2k' in sys.argv else '/tmp/flybench-v2j-a03-media-frames' if '--a03' in sys.argv else '/tmp/flybench-v2i-a02-media-frames')
p=root/'docs/media/media-provenance.json';provenance=json.loads(p.read_text())
for prefix,name in ([('game','game-hero.gif')] if '--a03' in sys.argv or '--v2k' in sys.argv else [('game','game-hero.gif'),('lab','coupling-hero.gif')]):
 sequence=[]
 # One palette keeps unchanged UI pixels stable, allowing lossless GIF delta rectangles.
 samples=sorted(frames.glob(prefix+'-*.png'))[::10]
 sheet=Image.new('RGB',(320,200*len(samples)))
 for i,frame in enumerate(samples):
  sample=Image.open(frame).convert('RGB');sample.thumbnail((320,200),Image.Resampling.LANCZOS);sheet.paste(sample,(0,i*200))
 palette=sheet.quantize(colors=96,method=Image.Quantize.MEDIANCUT)
 for frame in sorted(frames.glob(prefix+'-*.png')):
  im=Image.open(frame).convert('RGB');im.thumbnail((960,600) if prefix=='game' else (960,600),Image.Resampling.LANCZOS);sequence.append(im.quantize(palette=palette,dither=Image.Dither.NONE))
 duration=provenance['game' if prefix=='game' else 'lab']['frame_duration_ms']
 out=root/'docs/media'/name;sequence[0].save(out,save_all=True,append_images=sequence[1:],duration=duration,loop=0,optimize=False,disposal=1)
 data=out.read_bytes();assert len(data)<8_000_000;provenance['assets'][str(out.relative_to(root))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'frames':Image.open(out).n_frames,'source_frames':len(sequence),'size':sequence[0].size,'frame_duration_ms':duration,'palette_colors':96};print(name,len(data))
for size in [180,192,512]:
 out=root/f'apps/play/public/icon-{size}.png';data=out.read_bytes();provenance['assets'][str(out.relative_to(root))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
provenance['conversion_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
p.write_text(json.dumps(provenance,indent=2)+'\n')
