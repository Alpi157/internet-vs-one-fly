"""Pure declared-neural-output decoder for M06."""

from __future__ import annotations


def decode_dnp01(dnp01_spike_body_ids: tuple[int, ...]) -> bool:
    """Return one command pulse when either declared DNp01 body spiked."""

    return any(body_id == 10001 or body_id == 10010 for body_id in dnp01_spike_body_ids)
