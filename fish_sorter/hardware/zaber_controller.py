import json
import logging
import tomllib
from pathlib import Path

def _zaber_home_on_startup() -> bool:
    try:
        repo = Path(__file__).resolve().parents[2]
        cfg = repo / "fish_sorter.local.toml"
        if not cfg.exists():
            return False
        data = tomllib.loads(cfg.read_text(encoding="utf-8"))
        z = data.get("zaber", {}) if isinstance(data, dict) else {}
        return bool(z.get("home_on_startup", False))
    except Exception:
        return False

from typing import Optional
from zaber_motion import Units
from zaber_motion.ascii import Connection
from zaber_motion.exceptions.connection_failed_exception import ConnectionFailedException
from zaber_motion.exceptions.movement_failed_exception import MovementFailedException


class ZaberController():
    """Communicate with Zaber devices over serial to move the stages.

    This installation uses Zaber ASCII protocol with one device per COM port.
    We support either config['port'] (single) or config['ports'] (multi).
    """

    def __init__(self, config: dict, env: str = 'prod'):
        self.config = config
        self.env = env
        self.stage_alias = {}

        self.connections = []
        self.port_devices = {}

        self._connect()

    def _connect(self):
        try:
            if self.env == 'prod':
                logging.info('Establishing connection with Zaber devices')

                ports = self.config.get('ports') or [self.config.get('port')]
                ports = [p for p in ports if p]

                self.connections = []
                self.port_devices = {}

                for port in ports:
                    c = Connection.open_serial_port(port)
                    self.connections.append(c)
                    devs = c.detect_devices()
                    self.port_devices[port] = devs
                    logging.info(f'{port}: detected {len(devs)} device(s)')

                logging.info('Zaber devices successfully connected')
                self._set_axis()
                if _zaber_home_on_startup():
                    logging.info('Homing all')
                    self.home_arm()
                else:
                    logging.info('Skipping homing on startup (zaber.home_on_startup=false)')
            elif self.env == 'dev':
                raise NotImplementedError("dev/mock mode not implemented for ASCII multi-port ZaberController")

        except ConnectionFailedException:
            logging.critical("Could not make connection to zaber stage")
            raise

    def disconnect(self):
        for c in getattr(self, "connections", []):
            try:
                c.close()
            except Exception:
                pass
        logging.info('Closed Zaber device connection(s)')

    def _set_axis(self):
        port_to_axis = {'COM3': 'x', 'COM4': 'y', 'COM5': 'p'}

        self.stage_alias = {}

        for port, devs in getattr(self, 'port_devices', {}).items():
            axis_name = port_to_axis.get(port)
            if axis_name is None:
                logging.warning(f'No axis mapping for port {port}; skipping')
                continue
            if not devs:
                logging.warning(f'No devices found on {port}')
                continue

            dev = devs[0]
            axis_obj = dev.get_axis(1)
            self.stage_alias[axis_obj] = axis_name

            try:
                sn = dev.serial_number
            except Exception:
                sn = None

            logging.info(f'Assigned {dev.name} (SN {sn}) on {port} axis 1 -> {axis_name}')

        logging.info('Done setting axis')

    def home_arm(self, arm: Optional[list] = None):
        home = ['p', 'x', 'y'] if arm is None else arm
        for h in home:
            self.move_arm(h)

    def move_arm(self, arm: str, dist: Optional[float] = None, is_relative: bool = False):
        device_arm = None
        for key, value in self.stage_alias.items():
            if value == arm:
                device_arm = key
                break

        if device_arm is None:
            raise ValueError(f"No device mapped for arm '{arm}'. Have: {set(self.stage_alias.values())}")

        try:
            if dist is None:
                device_arm.home()
                logging.info('homing')
            elif is_relative:
                device_arm.move_relative(dist, Units.LENGTH_MILLIMETRES)
            else:
                device_arm.move_absolute(dist, Units.LENGTH_MILLIMETRES)
        except MovementFailedException:
            cur_pos = device_arm.get_position(unit=Units.LENGTH_MILLIMETRES)
            logging.critical('Failed to move {} arm'.format(device_arm))
            logging.critical('Stuck At: {}, Desired Pos: {}'.format(cur_pos, dist))
            raise
        except ConnectionFailedException:
            logging.critical('Zaber Connection Failed')
            raise

    def get_pos(self, arm: str) -> float:
        device_arm = None
        for key, value in self.stage_alias.items():
            if value == arm:
                device_arm = key
                break

        if device_arm is None:
            raise ValueError(f"No device mapped for arm '{arm}'. Have: {set(self.stage_alias.values())}")

        try:
            return device_arm.get_position(unit=Units.LENGTH_MILLIMETRES)
        except ConnectionFailedException:
            logging.critical('Zaber Connection Failed')
            raise