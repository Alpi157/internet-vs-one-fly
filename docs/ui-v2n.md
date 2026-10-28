# V2N README media refresh

The four README GIFs and stills are captured from unmodified accepted V2M sources,
commit `1b670a9d371ce406a1865aa5c4b91085b4f87fea`. This is a display-only stage.
Every file under `apps/play/src` and `apps/play/public` stays byte-identical to
that commit. The existing social card, intro images and icons are retained.
No deployment is needed. Scientific profiles, frozen protocols, registered
results and raw records are unchanged. External review remains pending.

The frozen V2L hero rule is reused without amendment: neural seed 1, environment
seed 8128, game v2.9 with owner-selected T0, current-position swat after 1500 ms,
600 ms hold. Seed 1 still escapes with the exact historical authoritative log
and impact. Walking uses real speed, strike intervals use 5x slowdown, and the
ordinary recorded replay runs for 3 s at quarter speed. The current scrubber
advances visibly beside the frame and speed controls. No additional seed is tried.
The lab uses coupling 0.039, neural seed 2027101401, environment seed 8128,
step 1 then step 2, with 40 frames per step at 100 ms.

Chromium records a 1440x900 CSS viewport at deviceScaleFactor 2. A prior dry run
compares both scale factors: CSS layout, authoritative log, impact, recorded
frames, replay ticks and scrubber values match. The game activity canvas uses
1400x720 pixels, below the unchanged 1,048,576-pixel budget. Lab activity retains
its existing 32,768-pixel cap. The higher scale factor changes raster sharpness.
Full-size PNG frames remain in `evidence/V2N/source-frames`; both stills are exact
copies of source frames from these captures.

The existing recorder and encoder have separate `--v2n` modes. Their historical
mode bodies are unchanged and checked by a regression test. Both GIFs use
960x600 output, the V2M 112-color global median-cut palette rule with green and
tan samples and no dithering. Transparent GIF deltas compress unchanged pixels;
every decoded RGB frame is checked byte for byte against its palette-quantized
source. This lossless encoding keeps the detailed capture under 8 MB. Provenance
records source and asset SHA-256 hashes, frame identities, palette samples and
palette bytes. The previous provenance is retained verbatim under
`docs/media/history/v2m-provenance.json`; existing history is unchanged.
The README template has the same alt text and caption update so its generated
copy remains exact; all other README/template text and every number are retained.

V2M media assertions still check its accepted GIF bytes and historical
provenance, including semantic color pixel checks and the owner's pinned hash.
The V2N registry in `tools/acceptance.json` runs the fast offline acceptance
suite, V2M unit and preservation checks, and V2N media/source/frozen/raw-record
checks. Receipts are under `evidence/V2N/acceptance`. Only Chromium is used for
capture and presentation checks; the cross-browser runtime matrix is outside
this media-only stage. Contact sheets decode every tenth frame of each old and
new GIF side by side. The compact review archive is `reviews/v2n-a01.zip`.
