#!/usr/bin/env python3
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.measurement import (
    DEFAULT_INFRA_SSIDS,
    DEFAULT_ROOM_HEIGHT_M,
    DEFAULT_ROOM_LENGTH_M,
    DEFAULT_ROOM_WIDTH_M,
    WifiSsidScanner,
    WifiScanError,
    build_tof_reader,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record real RSSI and top/bottom ToF measurements to CSV."
    )
    parser.add_argument("--output", default="data/raw_measurements.csv")
    parser.add_argument("--interface", default="wlan1")
    parser.add_argument("--scan-command", choices=("iw", "iwlist", "mock"), default="iw")
    parser.add_argument("--no-sudo", action="store_true")
    parser.add_argument("--ssid", nargs="+", default=list(DEFAULT_INFRA_SSIDS))
    parser.add_argument("--point-id", required=True)
    parser.add_argument("--area", required=True)
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--z", type=float, default=0.0)
    parser.add_argument("--room-length", type=float, default=DEFAULT_ROOM_LENGTH_M)
    parser.add_argument("--room-width", type=float, default=DEFAULT_ROOM_WIDTH_M)
    parser.add_argument("--room-height", type=float, default=DEFAULT_ROOM_HEIGHT_M)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--tof-top",
        choices=("none", "mock", "file", "serial"),
        default="none",
        help="Reader for the upper ToF sensor.",
    )
    parser.add_argument("--tof-top-path", default="")
    parser.add_argument("--tof-top-value", type=float, default=0.0)
    parser.add_argument("--tof-top-scale", type=float, default=1.0)
    parser.add_argument(
        "--tof-bottom",
        choices=("none", "mock", "file", "serial"),
        default="none",
        help="Reader for the lower ToF sensor.",
    )
    parser.add_argument("--tof-bottom-path", default="")
    parser.add_argument("--tof-bottom-value", type=float, default=0.0)
    parser.add_argument("--tof-bottom-scale", type=float, default=1.0)
    parser.add_argument("--tof-baudrate", type=int, default=115200)
    return parser.parse_args()


def validate_point(args: argparse.Namespace) -> None:
    if not 0 <= args.x <= args.room_length:
        raise ValueError(f"x must be within 0..{args.room_length} m")
    if not 0 <= args.y <= args.room_width:
        raise ValueError(f"y must be within 0..{args.room_width} m")
    if not 0 <= args.z <= args.room_height:
        raise ValueError(f"z must be within 0..{args.room_height} m")


def fmt(value) -> str:
    return "" if value is None else f"{value:.4f}"


def main() -> None:
    args = parse_args()
    validate_point(args)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "point_id",
        "area",
        "x",
        "y",
        "z",
        "tof_top_m",
        "tof_bottom_m",
        *args.ssid,
    ]

    scanner = WifiSsidScanner(
        args.interface,
        args.ssid,
        command=args.scan_command,
        use_sudo=not args.no_sudo,
    )
    top_reader = build_tof_reader(
        args.tof_top,
        args.tof_top_path,
        args.tof_top_value,
        args.tof_top_scale,
        args.tof_baudrate,
    )
    bottom_reader = build_tof_reader(
        args.tof_bottom,
        args.tof_bottom_path,
        args.tof_bottom_value,
        args.tof_bottom_scale,
        args.tof_baudrate,
    )

    write_header = not output.exists() or output.stat().st_size == 0
    try:
        with output.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()

            for index in range(args.samples):
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                try:
                    rssi = scanner.scan()
                except WifiScanError as exc:
                    print(exc)
                    print()
                    print("Measurement stopped because Wi-Fi scan failed.")
                    print(f"Try: python3 scripts/check_devices.py --interface {args.interface}")
                    print(
                        f"Or:  python3 scripts/check_devices.py --interface {args.interface} --command iwlist"
                    )
                    raise SystemExit(3) from exc
                row = {
                    "timestamp": timestamp,
                    "point_id": args.point_id,
                    "area": args.area,
                    "x": f"{args.x:.3f}",
                    "y": f"{args.y:.3f}",
                    "z": f"{args.z:.3f}",
                    "tof_top_m": fmt(top_reader.read_m()),
                    "tof_bottom_m": fmt(bottom_reader.read_m()),
                }
                for ssid in args.ssid:
                    row[ssid] = fmt(rssi.get(ssid))
                writer.writerow(row)
                handle.flush()

                visible = ", ".join(
                    f"{ssid}={row[ssid] or '--'}" for ssid in args.ssid
                )
                print(
                    f"[{index + 1}/{args.samples}] {timestamp} "
                    f"top={row['tof_top_m'] or '--'} bottom={row['tof_bottom_m'] or '--'} "
                    f"{visible}"
                )
                if index < args.samples - 1:
                    time.sleep(args.interval)
    finally:
        top_reader.close()
        bottom_reader.close()


if __name__ == "__main__":
    main()
