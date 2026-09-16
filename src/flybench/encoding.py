"""Transparent feature-level sensory encoding for the M06 controller."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


OBJECT_RADIUS = 1.0
THETA_PEAK_RAD = math.pi / 2.0
EXPANSION_PEAK_RAD_PER_MS = 0.0275


@dataclass(frozen=True, slots=True)
class ThreatObservation:
    """The declared sensory-side observation at one control boundary."""

    visual_threat_present: bool
    distance: float | None = None
    radial_velocity_per_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class LoomingFeatures:
    """The two disclosed, non-directional encoder features."""

    angular_size_rad: float
    angular_velocity_rad_per_ms: float
    positive_expansion: float
    size_feature: float
    expansion_feature: float


@dataclass(frozen=True, slots=True)
class EncodedDrive:
    """Population scalars and the held per-neuron external-drive vector."""

    lc4_drive: float
    lplc2_drive: float
    vector: np.ndarray


def compute_features(observation: ThreatObservation) -> LoomingFeatures:
    """Compute the frozen M06 size and positive-expansion features."""

    if not observation.visual_threat_present:
        return LoomingFeatures(0.0, 0.0, 0.0, 0.0, 0.0)
    if observation.distance is None:
        raise ValueError("a present visual threat requires distance")
    distance = float(observation.distance)
    velocity = float(observation.radial_velocity_per_ms)
    if not math.isfinite(distance) or distance <= 0.0:
        raise ValueError("distance must be finite and positive")
    if not math.isfinite(velocity):
        raise ValueError("radial velocity must be finite")

    angular_size = 2.0 * math.atan(OBJECT_RADIUS / distance)
    angular_velocity = (
        -2.0
        * OBJECT_RADIUS
        / (distance * distance + OBJECT_RADIUS * OBJECT_RADIUS)
        * velocity
    )
    positive_expansion = max(angular_velocity, 0.0)
    size_feature = min(max(angular_size / THETA_PEAK_RAD, 0.0), 1.0)
    expansion_feature = min(
        max(positive_expansion / EXPANSION_PEAK_RAD_PER_MS, 0.0), 1.0
    )
    return LoomingFeatures(
        angular_size_rad=angular_size,
        angular_velocity_rad_per_ms=angular_velocity,
        positive_expansion=positive_expansion,
        size_feature=size_feature,
        expansion_feature=expansion_feature,
    )


def encode_population_drive(
    features: LoomingFeatures,
    peak_sensory_external_drive: float,
    *,
    neuron_count: int,
    lc4_indices: np.ndarray,
    lplc2_indices: np.ndarray,
    dnp01_indices: np.ndarray,
) -> EncodedDrive:
    """Apply one scalar to every member of each declared sensory port."""

    peak = float(peak_sensory_external_drive)
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValueError("peak sensory external drive must be finite and positive")
    if type(neuron_count) is not int or neuron_count <= 0:
        raise ValueError("neuron_count must be a positive integer")
    lc4_drive = peak * features.expansion_feature
    lplc2_drive = peak * features.size_feature
    drive = np.zeros(neuron_count, dtype=np.float64)
    drive[np.asarray(lc4_indices, dtype=np.int64)] = lc4_drive
    drive[np.asarray(lplc2_indices, dtype=np.int64)] = lplc2_drive
    dnp = np.asarray(dnp01_indices, dtype=np.int64)
    if np.any(drive[dnp] != 0.0):
        raise RuntimeError("DNp01 must receive no encoder external drive")
    drive.flags.writeable = False
    return EncodedDrive(lc4_drive=lc4_drive, lplc2_drive=lplc2_drive, vector=drive)
