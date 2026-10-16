"""Anonymous, bounded, resumable acquisition of the documented MaleCNS anatomy."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

BASE = 'https://storage.googleapis.com/flyem-male-cns/'
SWC = 'v1.0/segmentation/skeletons-malecns/skeletons-swc/'
ROIS = ['rois/fullbrain-roi-v4', 'rois/malecns-vnc-neuropil-roi-v0']


class SameBucketRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith(BASE): raise ValueError('Redirect outside documented source')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(root, relative):
    if relative.startswith('/') or '..' in Path(relative).parts: raise ValueError('Unsafe source path')
    cache = root/'data/anatomy/raw'/relative
    receipt = cache.with_name(cache.name+'.receipt.json')
    cache.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        row = json.loads(receipt.read_text())
        if row.get('http_status') == 404: return row
        if cache.is_file() and hashlib.sha256(cache.read_bytes()).hexdigest() == row['sha256']:
            return row
        raise ValueError('Cached anatomy input differs from receipt: '+relative)
    part = cache.with_name(cache.name+'.part')
    opener = urllib.request.build_opener(SameBucketRedirect())
    for attempt in range(4):
        start = part.stat().st_size if part.exists() else 0
        try:
            req = urllib.request.Request(BASE+relative, headers={'Range':f'bytes={start}-'} if start else {})
            with opener.open(req, timeout=60) as response:
                append = bool(start and response.status == 206)
                if append and not response.headers['Content-Range'].startswith(f'bytes {start}-'):
                    raise ValueError('Invalid resumed response')
                length = int(response.headers['Content-Length']) if response.headers.get('Content-Length') else None
                received = 0
                with part.open('ab' if append else 'wb') as stream:
                    while chunk := response.read(1024*1024):
                        stream.write(chunk); received += len(chunk)
                if length is not None and received != length: raise OSError('Incomplete response')
            os.replace(part, cache)
            row = dict(url=BASE+relative, bytes=cache.stat().st_size,
                       sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),
                       retrieved_utc=datetime.now(timezone.utc).isoformat(), cache_path=str(cache.relative_to(root)))
            receipt.write_text(json.dumps(row, indent=2)+'\n')
            return row
        except urllib.error.HTTPError as error:
            if error.code == 404:
                row = dict(url=BASE+relative, bytes=0, sha256=None, http_status=404,
                           retrieved_utc=datetime.now(timezone.utc).isoformat())
                receipt.write_text(json.dumps(row, indent=2)+'\n'); return row
            if error.code < 500 and error.code != 429: raise
            if attempt == 3: raise
        except OSError:
            if attempt == 3: raise
        time.sleep(2**attempt)
    raise AssertionError('Unreachable')


def chunk_paths(root, roi):
    info = json.loads((root/'data/anatomy/raw'/roi/'info').read_text())
    if info['data_type'] != 'uint64' or info['num_channels'] != 1: raise ValueError('ROI layout differs')
    scale = next(s for s in info['scales'] if all(1000 <= r <= 2000 for r in s['resolution']))
    if scale['encoding'] != 'compressed_segmentation' or 'sharding' in scale: raise ValueError('ROI layout differs')
    size, offset, chunk = scale['size'], scale['voxel_offset'], scale['chunk_sizes'][0]
    for z in range(0,size[2],chunk[2]):
        for y in range(0,size[1],chunk[1]):
            for x in range(0,size[0],chunk[0]):
                begin = [x,y,z]; end = [min(a+b,s) for a,b,s in zip(begin,chunk,size)]
                name = '_'.join(f'{a+o}-{b+o}' for a,b,o in zip(begin,end,offset))
                yield roi+'/'+scale['key']+'/'+name, begin, end, scale


def fetch_many(root, names, workers=8):
    if not 1 <= workers <= 8: raise ValueError('At most eight requests')
    started = time.monotonic(); rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch,root,name): name for name in sorted(set(names))}
        for future in as_completed(futures):
            row = future.result(); rows.append(row)
            if len(rows)%100 == 0 or len(rows) == len(futures):
                elapsed = time.monotonic()-started
                print(f'Acquisition {len(rows)}/{len(futures)}, {elapsed:.1f} s, ETA {elapsed/len(rows)*(len(futures)-len(rows)):.1f} s', flush=True)
    return sorted(rows, key=lambda r:r['url'])
