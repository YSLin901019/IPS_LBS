import re
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, Optional


DEFAULT_ROOM_LENGTH_M = 15.0
DEFAULT_ROOM_WIDTH_M = 9.0
DEFAULT_ROOM_HEIGHT_M = 2.7
DEFAULT_INFRA_SSIDS = ("infra_1", "infra_2", "infra_3", "infra_4")


class WifiScanError(RuntimeError):
    def __init__(self, command, returncode, stdout, stderr) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout.strip()
        self.stderr = stderr.strip()
        command_text = " ".join(command)
        details = [
            f"Wi-Fi scan command failed with exit code {returncode}: {command_text}",
        ]
        if self.stdout:
            details.append(f"stdout: {self.stdout}")
        if self.stderr:
            details.append(f"stderr: {self.stderr}")
        super().__init__("\n".join(details))


@dataclass(frozen=True)
class RoomConfig:
    length_m: float = DEFAULT_ROOM_LENGTH_M
    width_m: float = DEFAULT_ROOM_WIDTH_M
    height_m: float = DEFAULT_ROOM_HEIGHT_M


class WifiSsidScanner:
    """Scan RSSI values by SSID using a Linux Wi-Fi interface."""

    def __init__(
        self,
        interface: str,
        target_ssids: Iterable[str] = DEFAULT_INFRA_SSIDS,
        command: str = "iw",
        timeout: int = 12,
        use_sudo: bool = True,
    ) -> None:
        self.interface = interface
        self.target_ssids = tuple(target_ssids)
        self.command = command
        self.timeout = timeout
        self.use_sudo = use_sudo

    def scan(self) -> Dict[str, float]:
        if self.command == "mock":
            return self._mock_scan()
        if self.command == "iwlist":
            output = self._run(self._with_privilege(["iwlist", self.interface, "scan"]))
            return self._parse_iwlist(output)
        output = self._run(self._with_privilege(["iw", "dev", self.interface, "scan"]))
        return self._parse_iw(output)

    def _run(self, command) -> str:
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.CalledProcessError as exc:
            raise WifiScanError(
                exc.cmd,
                exc.returncode,
                exc.stdout or "",
                exc.stderr or "",
            ) from exc
        return result.stdout

    def _with_privilege(self, command):
        if self.use_sudo:
            return ["sudo", *command]
        return command

    def _parse_iw(self, output: str) -> Dict[str, float]:
        readings: Dict[str, float] = {}
        current_signal: Optional[float] = None
        for raw_line in output.splitlines():
            line = raw_line.strip()
            signal_match = re.match(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", line)
            if signal_match:
                current_signal = float(signal_match.group(1))
                continue

            ssid_match = re.match(r"SSID:\s*(.*)", line)
            if ssid_match:
                ssid = ssid_match.group(1)
                if ssid in self.target_ssids and current_signal is not None:
                    readings[ssid] = max(readings.get(ssid, -200.0), current_signal)
                current_signal = None
        return readings

    def _mock_scan(self) -> Dict[str, float]:
        base_values = (-48.0, -56.0, -63.0, -70.0)
        return {
            ssid: base_values[index % len(base_values)]
            for index, ssid in enumerate(self.target_ssids)
        }

    def _parse_iwlist(self, output: str) -> Dict[str, float]:
        readings: Dict[str, float] = {}
        current_signal: Optional[float] = None
        for raw_line in output.splitlines():
            line = raw_line.strip()
            signal_match = re.search(r"Signal level=(-?\d+(?:\.\d+)?)\s*dBm", line)
            if signal_match:
                current_signal = float(signal_match.group(1))
                continue

            essid_match = re.search(r'ESSID:"(.*)"', line)
            if essid_match:
                ssid = essid_match.group(1)
                if ssid in self.target_ssids and current_signal is not None:
                    readings[ssid] = max(readings.get(ssid, -200.0), current_signal)
                current_signal = None
        return readings


class ToFReader(ABC):
    @abstractmethod
    def read_m(self) -> Optional[float]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class NullToFReader(ToFReader):
    def read_m(self) -> Optional[float]:
        return None


class MockToFReader(ToFReader):
    def __init__(self, value_m: float) -> None:
        self.value_m = value_m

    def read_m(self) -> Optional[float]:
        return self.value_m


class FileToFReader(ToFReader):
    """Read a numeric distance from a text file, sysfs node, or named pipe."""

    def __init__(self, path: str, scale: float = 1.0) -> None:
        self.path = path
        self.scale = scale

    def read_m(self) -> Optional[float]:
        with open(self.path, "r", encoding="utf-8") as handle:
            text = handle.read()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group(0)) * self.scale


class SerialToFReader(ToFReader):
    """Read one numeric distance per line from a serial ToF bridge."""

    def __init__(self, port: str, baudrate: int = 115200, scale: float = 1.0) -> None:
        try:
            import serial
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Serial ToF mode requires pyserial. Install it with: "
                "python3 -m pip install pyserial"
            ) from exc

        self.scale = scale
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=1.0)
        time.sleep(0.2)

    def read_m(self) -> Optional[float]:
        line = self._serial.readline().decode("utf-8", errors="ignore")
        match = re.search(r"-?\d+(?:\.\d+)?", line)
        if not match:
            return None
        return float(match.group(0)) * self.scale

    def close(self) -> None:
        self._serial.close()


def build_tof_reader(kind: str, path: str, value_m: float, scale: float, baudrate: int) -> ToFReader:
    if kind == "none":
        return NullToFReader()
    if kind == "mock":
        return MockToFReader(value_m)
    if kind == "file":
        if not path:
            raise ValueError("file ToF reader requires a path")
        return FileToFReader(path, scale=scale)
    if kind == "serial":
        if not path:
            raise ValueError("serial ToF reader requires a port path")
        return SerialToFReader(path, baudrate=baudrate, scale=scale)
    raise ValueError(f"unsupported ToF reader kind: {kind}")
