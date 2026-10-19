"""Game-only adapter. Frozen RunnerV2, kernel, encoder and decoder stay untouched.

Walking current is determined before encoding, by a seed-only object. There is no
hand information in that object or in the decoder. Lab code uses RunnerV2 directly.
"""
from dataclasses import asdict, replace
import math
import numpy as np
from flybench.runner_v2 import RunnerV2
from flybench.walking_drive import WalkingDrive
from flybench.encoding_v2 import HandStrikeV2, encode_hand_v2
from flybench.kernel_v2 import interval_counts
from flybench.decoder_v2 import decode_spikes_v2
from flybench.body_v2 import advance_body_v2
from flybench.detmath import u32


class GameRunnerV28(RunnerV2):
    def __init__(self, state, ids, gain, environment_seed, point):
        self.walking = WalkingDrive(environment_seed, point)
        super().__init__(state, ids, gain, body_enabled=False)
        forbidden = set(np.concatenate((*self.group_indices[:2], *self.visual.values())).tolist())
        if forbidden.intersection(np.concatenate(self.group_indices[2:]).tolist()):
            raise ValueError('Walking ports overlap sensory or escape ports')

    def reset(self):
        super().reset()
        self.walking.reset()

    def step(self, strike: HandStrikeV2, *, population: str | None = None, hand_radius: float = .75) -> dict:
        # The held command acts before the new sensory/network interval.
        applied=self.held
        encoded=encode_hand_v2(strike,fly_x=self.body.x,fly_y=self.body.y,
            heading_x=self.body.heading_x,heading_y=self.body.heading_y,
            hand_radius=hand_radius,initial_height=8.,dt_ms=.5,input_gain=self.gain)
        walking=np.zeros(self.state.n,dtype=np.float64)
        currents=self.walking.next()
        for group,current in zip((5,2,3,4),currents,strict=True):
            walking[self.group_indices[group]]=current
        drive=walking.copy()
        for key,indices in self.visual.items():
            if population is None or key.startswith(population+'_'):
                drive[indices]+=getattr(encoded,key.lower()+'_drive')
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
            counts+=interval_counts(self.state,walking,20-active_steps)
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


class WalkingGame:
    """Python counterpart of the v2.7 body/collision loop with the v2.8 adapter."""
    def __init__(self, runner, profile, environment_seed):
        self.runner, self.profile, self.environment_seed = runner, profile, environment_seed
        self.strike = None
        self.air_until = 0
        self.air_direction = (1., 0.)
        self.strikes = self.catches = 0
        self.done = False
        self.frames, self.inputs, self.impacts = [], [], []

    @property
    def tick(self):
        return self.runner.state.tick

    def apply(self, tick, x, y, hold_ms):
        if self.done or self.strike or self.strikes >= self.profile['max_strikes']:
            return False
        if tick != self.tick or tick % 20 or not all(math.isfinite(v) for v in (x,y,hold_ms)) or hold_ms < 0 or math.hypot(x,y) > self.profile['arena_radius']:
            raise ValueError('Invalid authoritative input')
        thresholds = self.profile['hold_thresholds_ms']
        kind = 0 if hold_ms < thresholds[0] else 1 if hold_ms < thresholds[1] else 2
        spec = self.profile['strikes'][kind]
        self.strikes += 1
        self.inputs.append(dict(tick=tick,x=x,y=y,hold_ms=hold_ms))
        self.strike = dict(spec,aim_x=x,aim_y=y,start_tick=tick,impact_tick=tick+round(8/spec['speed']/.5),number=self.strikes)
        return True

    def step(self):
        if self.done:
            raise ValueError('Round complete')
        start, strike = self.tick, self.strike
        stimulus = HandStrikeV2(start < strike['impact_tick'],strike['aim_x'],strike['aim_y'],(start-strike['start_tick'])*.5,strike['speed']) if strike else HandStrikeV2(False)
        value = self.runner.step(stimulus,hand_radius=strike['radius'] if strike else .75)
        b = self.runner.body
        if start < self.air_until:
            b = replace(b,x=b.x+self.air_direction[0]*self.profile['takeoff_speed']*10,y=b.y+self.air_direction[1]*self.profile['takeoff_speed']*10)
        else:
            b = advance_body_v2(b,forward_speed_per_ms=value['applied'][1],turn_rate_rad_per_ms=value['applied'][2],dt_ms=10.)
        radius = self.profile['arena_radius']
        distance = math.hypot(b.x,b.y)
        while distance > radius:
            nx, ny = b.x/distance, b.y/distance
            factor = 2*radius/distance-1
            heading_dot = b.heading_x*nx+b.heading_y*ny
            b = replace(b,x=b.x*factor,y=b.y*factor,heading_x=b.heading_x-2*heading_dot*nx,heading_y=b.heading_y-2*heading_dot*ny)
            air_dot = self.air_direction[0]*nx+self.air_direction[1]*ny
            self.air_direction = (self.air_direction[0]-2*air_dot*nx,self.air_direction[1]-2*air_dot*ny)
            distance = math.hypot(b.x,b.y)
        self.runner.body = b
        impact = None
        if strike and self.tick == strike['impact_tick']:
            dx,dy = b.x-strike['aim_x'],b.y-strike['aim_y']
            caught = dx*dx+dy*dy <= strike['radius']*strike['radius']
            impact = dict(tick=self.tick,caught=caught,type=strike['name'],position=dict(x=b.x,y=b.y))
            self.impacts.append(impact)
            self.catches += int(caught)
        if value['onset'] and self.tick >= self.air_until:
            delta = (u32(self.environment_seed,43,self.tick,0)/2**32*2-1)*self.profile['takeoff_jitter_tangent']
            x,y = b.heading_x-delta*b.heading_y,b.heading_y+delta*b.heading_x
            norm = math.sqrt(x*x+y*y)
            self.air_direction = (x/norm,y/norm)
            self.air_until = self.tick+self.profile['takeoff_duration_ms']*2
        frame = dict(tick=self.tick,body=asdict(b),applied=value['applied'],air=self.tick<self.air_until,onset=value['onset'],impact=impact,counts=value['counts'])
        self.frames.append(frame)
        if len(self.frames)>self.profile['recording_max_intervals']:
            raise ValueError('Declared recording bound exceeded')
        if strike and self.tick >= strike['impact_tick']+self.profile['replay_post_ms']*2:
            self.strike = None
            self.done = self.strikes>=self.profile['max_strikes']
        if self.tick>=self.profile['round_ms']*2:
            self.done = True
        return frame
