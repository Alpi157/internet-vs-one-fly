from pathlib import Path
from PIL import Image
import hashlib,json,sys
# V2M changes palette encoding only, using the exact retained V2L source frames.
if '--v2m' in sys.argv:
 from PIL import ImageDraw
 root=Path(__file__).resolve().parents[3];frames=root/'evidence/V2M/hero-source-frames'
 if not frames.is_dir():frames=Path('/tmp/flybench-v2l-media-frames')
 paths=sorted(frames.glob('game-*.png'));assert len(paths)==153
 provenance=json.loads((root/'docs/media/history/v2l-provenance.json').read_text())
 images=[]
 for path in paths:
  im=Image.open(path).convert('RGB');im.thumbnail((960,600),Image.Resampling.LANCZOS);images.append(im)
 sheet=Image.new('RGB',(960,10200))
 for i,im in enumerate(images[::10]):sheet.paste(im,(0,i*600))
 ink=ImageDraw.Draw(sheet);ink.rectangle((0,9600,479,10199),fill='#63f29a');
 for j,color in enumerate(['#503c28','#6e553c','#876e50','#a58c69','#bea682']):ink.rectangle((480,9600+j*120,959,9719+j*120),fill=color)
 palette=sheet.quantize(colors=112,method=Image.Quantize.MEDIANCUT)
 sequence=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in images]
 out=root/'docs/media/game-hero.gif';sequence[0].save(out,save_all=True,append_images=sequence[1:],duration=50,loop=0,optimize=False,disposal=1)
 data=out.read_bytes();assert len(data)<8_000_000
 provenance['schema']='flybench.media.v2m.a01';provenance['history']='docs/media/history/v2l-provenance.json'
 provenance['capture_source_commit']='2cb59c0d6dca6c341c03e83ee5352d8955223f29'
 provenance['assets']['docs/media/game-hero.gif']={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'frames':Image.open(out).n_frames,'source_frames':len(sequence),'size':sequence[0].size,'frame_duration_ms':50,'palette_colors':112}
 provenance['conversion_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 provenance['palette_revision']={'same_source_frames':True,'rule':'112-color global median-cut palette from every tenth full-size frame; reserve sample area for semantic green #63F29A and five sampled tan body shades; no dithering; unchanged frame order, size and 50 ms timing.','source_frames_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
 (root/'docs/media/media-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
 print('V2M hero: same 153 frames,',len(data),'bytes');raise SystemExit
root=Path(__file__).resolve().parents[3];frames=Path('/tmp/flybench-v2l-media-frames' if '--v2l' in sys.argv else '/tmp/flybench-v2k-media-frames' if '--v2k' in sys.argv else '/tmp/flybench-v2j-a03-media-frames' if '--a03' in sys.argv else '/tmp/flybench-v2i-a02-media-frames')
p=root/'docs/media/media-provenance.json';provenance=json.loads(p.read_text())
# Retained lab media keep their original encoding metadata, even when the
# pre-capture declaration contains only the new game's selection rule.
if '--v2k' in sys.argv:
 historical=json.loads((root/provenance['history']).read_text())
 for name in ['docs/media/coupling-hero.gif','docs/media/coupling-still.png']:
  metadata=historical['assets'][name];data=(root/name).read_bytes()
  assert hashlib.sha256(data).hexdigest()==metadata['sha256']
  provenance['assets'][name]=metadata
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

if '--v2l' in sys.argv:
 for i in range(200):
  im=Image.open(frames/f'review-{i:03d}.png').convert('RGB');im.thumbnail((960,600),Image.Resampling.LANCZOS);im.save(frames/f'video-{i:03d}.png')
