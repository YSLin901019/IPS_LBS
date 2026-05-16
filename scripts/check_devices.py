#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.measurement import (
    DEFAULT_INFRA_SSIDS,
    WifiScanError,
    WifiSsidScanner,
    build_tof_reader,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check whether the Wi-Fi dongle can scan the infrastructure SSIDs."
    )
    parser.add_argument("--interface", default="wlan1")
    parser.add_argument("--command", choices=("iw", "iwlist", "mock"), default="iw")
    parser.add_argument("--no-sudo", action="store_true")
    parser.add_argument("--ssid", nargs="+", default=list(DEFAULT_INFRA_SSIDS))
    parser.add_argument("--tof-top", choices=("none", "mock", "file", "serial"), default="none")
    parser.add_argument("--tof-top-path", default="")
    parser.add_argument("--tof-top-value", type=float, default=0.0)
    parser.add_argument("--tof-top-scale", type=float, default=1.0)
    parser.add_argument("--tof-bottom", choices=("none", "mock", "file", "serial"), default="none")
    parser.add_argument("--tof-bottom-path", default="")
    parser.add_argument("--tof-bottom-value", type=float, default=0.0)
    parser.add_argument("--tof-bottom-scale", type=float, default=1.0)
    parser.add_argument("--tof-baudrate", type=int, default=115200)
    args = parser.parse_args()

    scanner = WifiSsidScanner(
        args.interface,
        args.ssid,
        command=args.command,
        use_sudo=not args.no_sudo,
    )
    print(f"Scanning {args.interface} for: {', '.join(args.ssid)}")
    try:
        readings = scanner.scan()
    except WifiScanError as exc:
        print(exc)
        print()
        print("Try these diagnostics:")
        print(f"  iw dev")
        print(f"  ip link show {args.interface}")
        print("  rfkill list")
        print(f"  sudo ip link set {args.interface} up")
        print(f"  python3 scripts/check_devices.py --interface {args.interface} --command iwlist")
        print(f"  python3 scripts/check_devices.py --interface {args.interface} --no-sudo")
        raise SystemExit(3) from exc

    if not readings:
        print("No target infrastructure SSID was found.")
        print("The dongle scanned successfully, but infra_1..infra_4 were not visible.")
        print("Check SSID spelling, AP power, 6 GHz regulatory domain, and distance.")
        raise SystemExit(2)

    for ssid in args.ssid:
        value = readings.get(ssid)
        if value is None:
            print(f"{ssid}: not found")
        else:
            print(f"{ssid}: {value:.1f} dBm")

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
    try:
        top = top_reader.read_m()
        bottom = bottom_reader.read_m()
        if args.tof_top != "none":
            print(f"tof_top_m: {'--' if top is None else f'{top:.4f}'}")
        if args.tof_bottom != "none":
            print(f"tof_bottom_m: {'--' if bottom is None else f'{bottom:.4f}'}")
    finally:
        top_reader.close()
        bottom_reader.close()


if __name__ == "__main__":
    main()
