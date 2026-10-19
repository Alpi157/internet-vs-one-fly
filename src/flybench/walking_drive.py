"""Declared game input, independent of the sensory environment and scientific runner."""
import math
from flybench.detmath import u32


def log_unit(x):
    exponent = 0
    while x < 1:
        x *= 2
        exponent -= 1
    z = (x - 1) / (x + 1)
    square = z * z
    term = total = z
    for k in range(1, 18):
        term = term * square
        total = total + term / (2 * k + 1)
    return 2 * total + exponent * 0.6931471805599453


class WalkingDrive:
    def __init__(self, environment_seed, point):
        self.seed = u32(environment_seed, 97, 0, 0)
        self.point = dict(point)
        if not all(math.isfinite(v) and v > 0 for v in point.values()):
            raise ValueError('Invalid walking drive point')
        self.reset()

    def uniform(self):
        value = (u32(self.seed, 97, self.counter, 0) + .5) / 4294967296
        self.counter += 1
        return value

    def dwell(self):
        return max(1, math.ceil(-log_unit(self.uniform()) * self.point['walk_seconds' if self.walk else 'stop_seconds'] / .01))

    def normal(self):
        while True:
            x, y = 2 * self.uniform() - 1, 2 * self.uniform() - 1
            s = x * x + y * y
            if 0 < s < 1:
                return x * math.sqrt(-2 * log_unit(s) / s)

    def reset(self):
        self.interval = self.counter = 0
        self.turn = 0.
        self.walk = self.uniform() < self.point['walk_seconds'] / (self.point['walk_seconds'] + self.point['stop_seconds'])
        self.remaining = self.dwell()

    def next(self):
        if self.remaining == 0:
            self.walk = not self.walk
            self.remaining = self.dwell()
        self.turn = 0.9867551618071957 * self.turn + 0.16221667807859647 * self.point['turn_sigma'] * self.normal()
        self.remaining -= 1
        self.interval += 1
        return [self.point['forward'], 0., max(0., self.turn), max(0., -self.turn)] if self.walk else [0., 0., 0., 0.]

    def snapshot(self):
        return [self.seed, self.interval, self.counter, int(self.walk), self.remaining, self.turn]
