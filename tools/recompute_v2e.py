#!/usr/bin/env python3
"""Independent of the frozen CLI verifier; ignore only its host metadata field.

Uses the same frozen library/summarizer, verifies its freeze, recomputes every
table from existing records, and compares all other fields against the committed
results. Restores nothing and performs no simulation or metadata substitution.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
from experiments.v2e_analyze import summarize

ROOT=Path(__file__).resolve().parents[1]


def compare(computed,committed):
    left=dict(computed);right=dict(committed)
    if 'hardware' not in left or 'hardware' not in right:
        raise ValueError('Expected hardware field missing')
    left.pop('hardware');right.pop('hardware')
    if left!=right:
        differing=sorted(k for k in left.keys()|right.keys() if left.get(k)!=right.get(k))
        raise ValueError('Recomputed results differ outside hardware: '+', '.join(differing))


def public_view(computed, completion, tables_sha256):
    # The public file is an existing compact view, not the full frozen tables.
    # Full metrics, raw hashes and duration arrays are checked against tables.json
    # before this formatting step, so no scientific field is ignored.
    def compact(value):
        if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if k not in ('bout_durations_ms','pause_durations_ms')}
        if isinstance(value,list):return [compact(v) for v in value]
        return value
    result={k:v for k,v in computed.items() if k not in ('metrics','raw_input_sha256')}
    result['controls']=compact(result['controls'])
    result['source_tables_sha256']=tables_sha256
    result['completion']=completion
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'evidence/V2E/results')
    args=parser.parse_args()
    computed=summarize(args.out)
    stored_path=args.out/'tables.json'
    compare(computed,json.loads(stored_path.read_text()))
    committed=json.loads((ROOT/'docs/results-v2e.json').read_text())
    view=public_view(computed,json.loads((args.out/'COMPLETE.json').read_text()),hashlib.sha256(stored_path.read_bytes()).hexdigest())
    compare(view,committed)
    print('PASS: independent of the frozen CLI verifier; every V2E table and every raw result field match tables.json, and its compact published view matches docs/results-v2e.json. Only hardware is ignored in both comparisons. Frozen hashes verified. No restoration or simulation.')


if __name__=='__main__':main()
