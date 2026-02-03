from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class SimValveConfig:
    n_valves: int = 8


class SimValves:
    def __init__(self, cfg: SimValveConfig):
        self.cfg = cfg
        self.state: List[bool] = [False] * int(cfg.n_valves)

    def connect(self) -> None:
        return

    def close(self) -> None:
        return

    def ping(self) -> bool:
        return True

    def set_valve(self, n: int, on: bool) -> None:
        idx = int(n) - 1
        if idx < 0 or idx >= len(self.state):
            raise ValueError(f"valve out of range: {n}")
        self.state[idx] = bool(on)

    def all_off(self) -> None:
        for i in range(len(self.state)):
            self.state[i] = False

    def status(self) -> str:
        # bitmask string, valve 1 on the left
        return "STATUS " + "".join("1" if v else "0" for v in self.state)
