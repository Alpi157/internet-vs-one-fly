import math
from flybench.walking_drive import WalkingDrive, log_unit


def test_log_and_seeded_reset():
    for x in [2**-33,.001,.1,.5,.99,1]:
        assert abs(log_unit(x)-math.log(x))<1e-14
    point=dict(forward=1.5,turn_sigma=.5,walk_seconds=1.,stop_seconds=.6)
    a,b=WalkingDrive(7,point),WalkingDrive(8,point)
    first=[a.next() for _ in range(1000)]
    assert first!=[b.next() for _ in range(1000)]
    a.reset()
    assert first==[a.next() for _ in range(1000)]
    assert all(v[1]==0 and v[2]*v[3]==0 for v in first)


def test_no_geometry_input_or_shared_state():
    point=dict(forward=1.5,turn_sigma=.5,walk_seconds=1.,stop_seconds=.6)
    a,b=WalkingDrive(7,point),WalkingDrive(7,point)
    a.next()
    assert b.interval==0
    point['forward']=99
    assert a.point['forward']==1.5
    assert set(a.__dict__)=={'seed','point','interval','counter','turn','walk','remaining'}


def test_ui_numbers_never_use_host_default_locale():
    from pathlib import Path
    import re
    root=Path(__file__).resolve().parents[1]
    for path in (root/'apps/play/src').glob('*.ts'):
        assert not re.search(r'\.toLocaleString\(\s*\)|new Intl.NumberFormat\(\s*\)',path.read_text()),path


def test_python_game_collision_precedes_new_onset():
    import json
    from pathlib import Path
    from types import SimpleNamespace
    from flybench.body_v2 import BodyStateV2
    from flybench.game_runner_v28 import WalkingGame
    profile=json.loads((Path(__file__).resolve().parents[1]/'profiles/game-v2.8.json').read_text())
    class FakeRunner:
        state=SimpleNamespace(tick=0)
        body=BodyStateV2(0.,0.,1.,0.)
        def step(self,strike,hand_radius):
            self.state.tick+=20
            return dict(applied=(False,0.,0.),onset=self.state.tick==400,counts=[])
    game=WalkingGame(FakeRunner(),profile,1001)
    assert game.apply(0,0.,0.,80)
    for _ in range(20):frame=game.step()
    assert frame['impact']['caught']
    assert frame['body']['x']==0.
    assert game.air_until==640
    assert game.step()['body']['x']!=0.
