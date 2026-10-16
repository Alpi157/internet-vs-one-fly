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


def test_strength_framing_and_numbers_are_generated():
    public=json.loads((ROOT/'apps/play/public/results-v2f.json').read_text())
    r=json.loads((ROOT/'docs/results-v2f.json').read_text())
    old=json.loads((ROOT/'docs/results-v2e.json').read_text())
    strength=next(v for v in r['tables'] if v['test']=='H0-STR' and v['metric']=='H0b')
    sign=next(v for v in old['tables'] if v['hypothesis']=='H0' and v['circuit']=='T1a' and v['family']=='N-SIGN' and v['metric']=='H0b')
    for value in [strength['real'],strength['null_median'],sign['null_median']]:
        assert f'{value:.2f} Hz' in public['lab_caveat']
    for v in r['exploratory']:
        if v['test']=='E1' and v['circuit']=='T1a' and v['metric']=='in_strength_gini' and v['family'] in ('N-SIGN','N-STRENGTH'):
            assert f"{v['null_median']:.2f}" in public['mechanism']
            assert f"{v['real']:.2f}" in public['mechanism']
    assert 'not a preregistered mechanism test' in public['mechanism']
    assert public['lab_heading']=='Measured vs shuffled wiring'
    for text in [public['original'],public['combined'],public['comparison_table'],public['mechanism'],public['limitations']]:
        assert text in (ROOT/'README.md').read_text()
    assert 'measured wiring is faster' in public['comparison_rows'][-1]['verdict'].lower()
    assert 'also holds' not in json.dumps(public)
    assert all('measured ' in line and 'null median ' in line for line in public['families'])
