# V2I: wiring lab and launch readiness

Scope and evidence interpretation: [ui-v2i.md](ui-v2i.md).

```sh
uv run --offline python experiments/v2f_publish.py --check
npm --prefix apps/play run build
npm --prefix apps/play test
node apps/play/test/v2i-e2e.mjs
uv run --offline python tools/run_acceptance.py V2I --out evidence/V2I/acceptance
uv run --offline python tools/review_bundle.py --milestone V2I --attempt 1 --base 0498868a9470e9be2f9037207e6cc5421b80e299 --out reviews/V2I-a01.zip
```

Acceptance and the ZIP must identify the final submitted commit. Do not mark the
stage accepted. No push, tag or deployment is authorized.
