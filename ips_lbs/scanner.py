import random
import re
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

from ips_lbs.models import RssiVector
from ips_lbs.radio_map import RadioMap


class Scanner(ABC):
    @abstractmethod
    def scan(self) -> RssiVector:
        raise NotImplementedError


class SimulatedScanner(Scanner):
    def __init__(
        self,
        radio_map: RadioMap,
        path: Optional[Iterable[str]] = None,
        noise_dbm: float = 3.0,
    ) -> None:
        self.radio_map = radio_map
        self.noise_dbm = noise_dbm
        point_ids = list(path) if path else [point.point_id for point in radio_map.points]
        self._points = [
            point for point_id in point_ids for point in radio_map.points if point.point_id == point_id
        ]
        if not self._points:
            self._points = list(radio_map.points)
        self._index = 0

    def scan(self) -> RssiVector:
        point = self._points[self._index % len(self._points)]
        self._index += 1
        return {
            node_id: value + random.uniform(-self.noise_dbm, self.noise_dbm)
            for node_id, value in point.rssi.items()
        }


class IwlistScanner(Scanner):
    """Wi-Fi scanner for Raspberry Pi OS using iwlist.

    It maps AP BSSID addresses to infrastructure IDs used by the radio map.
    Example mapping: {"AA:BB:CC:DD:EE:FF": "AP_1"}.
    """

    def __init__(self, interface: str, bssid_to_node_id: dict, timeout: int = 8) -> None:
        self.interface = interface
        self.bssid_to_node_id = {
            key.upper(): value for key, value in bssid_to_node_id.items()
        }
        self.timeout = timeout

    def scan(self) -> RssiVector:
        command = ["sudo", "iwlist", self.interface, "scan"]
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        return self._parse_iwlist(result.stdout)

    def _parse_iwlist(self, output: str) -> RssiVector:
        readings: RssiVector = {}
        current_bssid = None
        for line in output.splitlines():
            address_match = re.search(r"Address:\s*([0-9A-Fa-f:]{17})", line)
            if address_match:
                current_bssid = address_match.group(1).upper()
                continue

            signal_match = re.search(r"Signal level=(-?\d+)\s*dBm", line)
            if current_bssid and signal_match:
                node_id = self.bssid_to_node_id.get(current_bssid)
                if node_id:
                    readings[node_id] = float(signal_match.group(1))
                current_bssid = None
        return readings


def timed_scan(scanner: Scanner, duration_seconds: float = 3.0) -> RssiVector:
    deadline = time.monotonic() + max(duration_seconds, 0.1)
    samples: List[RssiVector] = []
    while time.monotonic() < deadline:
        samples.append(scanner.scan())
        time.sleep(0.3)

    merged = {}
    counts = {}
    for sample in samples:
        for node_id, value in sample.items():
            merged[node_id] = merged.get(node_id, 0.0) + value
            counts[node_id] = counts.get(node_id, 0) + 1
    return {node_id: merged[node_id] / counts[node_id] for node_id in merged}

