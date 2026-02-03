from __future__ import annotations

from fish_sorter.hardware.valves.sim import SimValves, SimValveConfig

def main() -> None:
    v = SimValves(SimValveConfig(n_valves=8))
    v.connect()
    print("PING", v.ping())
    print(v.status())
    v.set_valve(1, True)
    v.set_valve(3, True)
    print(v.status())
    v.all_off()
    print(v.status())

if __name__ == "__main__":
    main()
