"""V2L product identities and owner-authorized game-only changes."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='f30ae501a21c71e714084bd378ae59d6e2144a9e'
def load(p):return json.loads((ROOT/p).read_text())
def test_v2l_only_declared_game_parameters_change():
 old=load('profiles/game-v2.8.json');new=load('profiles/game-v2.9.json')
 assert new==load('profiles/game-v2.json')==load('apps/play/public/data/game.json')
 allowed={'profile_id','version','hold_thresholds_ms','strikes','takeoff_duration_ms','takeoff_path_arena_units','change_reason','physics_disclosure','walking_drive'}
 for k in old:
  if k not in allowed:assert new[k]==old[k],k
 assert new['strikes']==[old['strikes'][0],old['strikes'][2]]
 assert new['hold_thresholds_ms']==[300]
 assert new['takeoff_speed']==old['takeoff_speed']==.018
 assert new['takeoff_duration_ms']==330
 assert abs(new['takeoff_speed']*new['takeoff_duration_ms']-new['takeoff_path_arena_units'])<1e-12
 assert new['takeoff_path_arena_units']==5.94
 before=old['walking_drive'].copy();after=new['walking_drive'].copy()
 before.pop('copy');after.pop('copy');assert before==after
 assert load('apps/play/public/data/coupling/game-v2.8.json')==old

def test_v2l_protected_science_anatomy_kernel_and_reference():
 paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
 allowed={'profiles/game-v2.json','apps/play/public/data/game.json','apps/play/public/data/runtime.json','apps/play/public/data/HASHES.json','src/flybench/game_runner_v28.py'}
 protected=[p for p in paths if p not in allowed and (p.startswith(('src/','packages/kernel-ts/src/','apps/play/public/data/','profiles/','decisions/','docs/media/anatomy/')) or p in {'docs/results-v2e.json','docs/results-v2f.json','docs/results-v2e-lab-curves.json'})]
 result=subprocess.run(['git','diff','--exit-code',BASE,'--',*protected],cwd=ROOT,capture_output=True,text=True)
 assert result.returncode==0,result.stdout
 result=subprocess.run(['git','diff','--exit-code','b34c30ec396152e7cb4e75e6ae1c1b19d61f4fbb','--','docs/design/v5'],cwd=ROOT,capture_output=True,text=True)
 assert result.returncode==0,result.stdout
 for manifest in ['profiles/freeze-v2.json','profiles/freeze-v2.1.json']:
  for p,h in load(manifest)['files'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p

def test_v2l_registered_story_uses_results_and_public_disclosure():
 published=load('apps/play/public/results-v2f.json');row=published['comparison_rows'][0]
 expected=[row['real'],next(r['null_median'] for r in row['earlier'] if r['family']=='N-SIGN'),row['strength']['null_median']]
 assert [r['rate_hz'] for r in published['registered_story']]==expected
 assert [f'{x:.1f}' if x<10 else f'{x:.0f}' for x in expected]==['2.7','120','4.4']
 assert published['game_profile_id']=='flybench.game.v2.9'
 assert 'game profile v2.9' in published['walking_disclosure']
 assert 'A fly brain simulated from its real wiring. Try to swat it, then look inside its head.' in (ROOT/'README.md').read_text()
 for p in ['how-it-works.html','model.html','preregistration.html']:
  text=(ROOT/'apps/play/public'/p).read_text()
  assert 'Made by Alpar Arman' in text and 'Wiring lab' in text
 assert (ROOT/'docs/media/history/v2k-provenance.json').read_bytes()==subprocess.check_output(['git','show',BASE+':docs/media/media-provenance.json'],cwd=ROOT)
