"""Small headless v2 runner shared by scripted calibration and parity.

Supported envelope: float64, 0.5 ms neural ticks, 20 ticks/control interval,
fixed canonical graph edge order, u32.v2 noise on all neurons. No re-execution
claim is made for missing observations or other platforms.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from flybench.body_v2 import BodyStateV2, advance_body_v2
from flybench.decoder_v2 import decode_spikes_v2
from flybench.encoding_v2 import HandStrikeV2, encode_hand_v2
from flybench.kernel_v2 import KernelStateV2, interval_counts

ROOT = Path(__file__).resolve().parents[2]
GROUP_NAMES = ('escape_left','escape_right','backward','turn_left','turn_right','forward')


def port_groups(ids: np.ndarray) -> tuple[tuple[int,...], ...]:
    ports=json.loads((ROOT/'profiles/ports-v2.json').read_text())['groups']
    directions={v['type']:v['direction'] for v in json.loads((ROOT/'profiles/turn-directions-v1.json').read_text())['entries']}
    present=set(int(v) for v in ids)
    result={name:[] for name in GROUP_NAMES}
    for name,entries in ports.items():
        for entry in entries:
            body=int(entry['body_id'])
            if body not in present:continue
            target=name
            if name.startswith('turn_'):
                direction=directions[entry['annotation_type']]
                if direction=='UNKNOWN':continue
                if direction=='contralateral':target='turn_right' if name=='turn_left' else 'turn_left'
            result[target].append(body)
    return tuple(tuple(sorted(result[name])) for name in GROUP_NAMES)


def visual_indices(ids: np.ndarray) -> dict[str,np.ndarray]:
    by_id={int(v):i for i,v in enumerate(ids)}
    profile=json.loads((ROOT/'profiles/visual-ports-sides-v1.json').read_text())['populations']
    return {f'{pop}_{side}': np.array([by_id[int(v)] for v in profile[pop][f'{side}_body_ids_decimal'] if int(v) in by_id],dtype=np.int64) for pop in ('LC4','LPLC2') for side in ('left','right')}


class RunnerV2:
    def __init__(self, state: KernelStateV2, ids: np.ndarray, gain: float,
                 *, body_enabled: bool = True, output_clamp: bool = False):
        self.state=state
        self.ids=np.array(ids,copy=True)
        self.groups=port_groups(ids)
        by_id={int(v):i for i,v in enumerate(ids)}
        self.group_indices=tuple(np.array([by_id[v] for v in group],dtype=np.int64) for group in self.groups)
        self.visual=visual_indices(ids)
        self.gain=gain
        self.body_enabled=body_enabled
        self.output_clamp=output_clamp
        self.profile=json.loads((ROOT/'profiles/decoder-v2-draft.json').read_text())
        self.reset()

    def reset(self):
        self.state.reset()
        self.body=BodyStateV2(0.,0.,1.,0.)
        self.rates=(0.,)*6
        self.held=(False,0.,0.)
        self.previous_escape=False

    def step(self, strike: HandStrikeV2, *, population: str | None = None) -> dict:
        # The held command acts before the new sensory/network interval.
        applied=self.held
        encoded=encode_hand_v2(strike,fly_x=self.body.x,fly_y=self.body.y,
            heading_x=self.body.heading_x,heading_y=self.body.heading_y,
            hand_radius=.75,initial_height=8.,dt_ms=.5,input_gain=self.gain)
        drive=np.zeros(self.state.n,dtype=np.float64)
        for key,indices in self.visual.items():
            if population is None or key.startswith(population+'_'):
                drive[indices]=getattr(encoded,key.lower()+'_drive')
        # Removal can occur inside a control interval. Stop visual current on
        # the first neural boundary at or after impact, retaining integer clocks.
        active_steps=20
        if strike.active and strike.downward_speed_per_ms>0.:
            for step in range(20):
                if strike.downward_speed_per_ms*(strike.elapsed_ms+step*.5)>=8.:
                    active_steps=step
                    break
        counts=np.zeros(self.state.n,dtype=np.int64)
        if active_steps:
            counts+=interval_counts(self.state,drive,active_steps)
        if active_steps<20:
            counts+=interval_counts(self.state,np.zeros(self.state.n,dtype=np.float64),20-active_steps)
        output_ids=tuple(body for group,indices in zip(self.groups,self.group_indices,strict=True) for body,i in zip(group,indices,strict=True) for _ in range(int(counts[i])))
        p=self.profile
        escape,speed,turn,rates=decode_spikes_v2(output_ids,self.rates,self.groups,
            float.fromhex(p['rate_filter']['decay_float64_hex']),.01,
            p['forward_speed']['k_f'],p['turn_rate']['k_t'],
            *p['forward_speed']['clamp_arena_units_per_ms'],p['turn_rate']['clamp_radians_per_ms'][1])
        if self.body_enabled:
            self.body=advance_body_v2(self.body,forward_speed_per_ms=applied[1],turn_rate_rad_per_ms=applied[2],dt_ms=10.)
        self.rates=rates
        if self.output_clamp:escape,speed,turn=False,0.,0.
        onset=escape and not self.previous_escape
        self.previous_escape=escape
        self.held=(escape,speed,turn)
        return dict(tick=self.state.tick,applied=applied,command=self.held,onset=onset,
            counts=counts,group_counts=[int(counts[i].sum()) for i in self.group_indices],
            encoded=asdict(encoded),drive_zero=bool(not np.any(drive)))

    def neural_bytes(self) -> bytes:
        return int(self.state.tick).to_bytes(8,'little')+b''.join(np.ascontiguousarray(v).tobytes() for v in (self.state.voltage,self.state.synaptic_current,self.state.refractory_until_tick,self.state.pending_spikes,self.state.pending_inputs))

    def digest(self) -> str:
        payload=b'FlyBench v2c runner state v1\0'+self.neural_bytes()
        payload+=struct.pack('<4d',self.body.x,self.body.y,self.body.heading_x,self.body.heading_y)
        payload+=struct.pack('<6d',*self.rates)+struct.pack('<?dd?',*self.held,self.previous_escape)
        return hashlib.sha256(payload).hexdigest()
