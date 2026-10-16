"""Public copy must remain tied to frozen tables, including inconvenient results."""
import json
from pathlib import Path
from experiments.v2f_publish import outputs, verdict

ROOT = Path(__file__).resolve().parents[1]


def test_public_outputs_match_committed_results():
    for name, expected in outputs().items():
        assert (ROOT/name).read_text() == expected, name
    raw = ROOT/'evidence/V2F/results/tables.json'
    if raw.exists():
        assert json.loads(raw.read_text()) == json.loads((ROOT/'docs/results-v2f.json').read_text())


def test_censored_and_opposite_direction_are_not_positive_claims():
    r=json.loads((ROOT/'docs/results-v2f.json').read_text())
    strength=[v for v in r['tables'] if v['family']=='N-STRENGTH']
    assert not any(verdict(v).startswith('Supports') for v in strength)
    public=json.loads((ROOT/'apps/play/public/results-v2f.json').read_text())
    assert len(public['families']) == 6
    assert all('did not replicate' in s for s in public['families'] if 'N-STRENGTH' in s)
    assert 'preregistered SKIPPED' in public['exploratory'][-1]
    for row in r['exploratory']+r['correlations']:
        assert 'p' not in row and 'holm_p' not in row
