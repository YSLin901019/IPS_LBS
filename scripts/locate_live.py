#!/usr/bin/env python3
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.filters import MedianMovingFilter
from ips_lbs.measurement import DEFAULT_INFRA_SSIDS, WifiScanError, WifiSsidScanner
from ips_lbs.radio_map import load_radio_map
from ips_lbs.wknn import WKNNLocalizer


def parse_rssi_pairs(items):
    readings = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"RSSI item must use ssid=value format: {item}")
        ssid, value = item.split("=", 1)
        readings[ssid.strip()] = float(value)
    return readings


def point_grid_label(point_id: str) -> str:
    match = re.match(r"R(\d+)C(\d+)$", point_id)
    if not match:
        return point_id
    row, col = match.groups()
    return f"row={int(row)} col={int(col)}"


def print_estimate(estimate, x_offset: float = 0.0, y_offset: float = 0.0) -> None:
    best_point = estimate.neighbors[0][0] if estimate.neighbors else None
    calibrated_x = estimate.x + x_offset
    calibrated_y = estimate.y + y_offset
    print("WKNN result")
    print(f"  estimated_area: {estimate.area}")
    print(f"  estimated_xy: x={estimate.x:.2f} m, y={estimate.y:.2f} m")
    if x_offset or y_offset:
        print(
            f"  calibrated_xy: x={calibrated_x:.2f} m, y={calibrated_y:.2f} m "
            f"(offset x={x_offset:+.2f} m, y={y_offset:+.2f} m)"
        )
    print(f"  confidence: {estimate.confidence:.4f}")
    if best_point is not None:
        print(
            f"  nearest_cell: {best_point.point_id} "
            f"({point_grid_label(best_point.point_id)})"
        )
        print(f"  nearest_xy: x={best_point.x:.2f} m, y={best_point.y:.2f} m")
    print("  filtered_rssi:")
    for ssid, value in sorted(estimate.filtered_rssi.items()):
        print(f"    {ssid}: {value:.2f} dBm")
    print("  neighbors:")
    for point, distance, weight in estimate.neighbors:
        print(
            f"    {point.point_id} {point_grid_label(point.point_id)} "
            f"x={point.x:.2f} y={point.y:.2f} "
            f"distance={distance:.2f} weight={weight:.4f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate the current location from live or manual RSSI readings."
    )
    parser.add_argument("--radio-map", default="data/indoor-map-5.json")
    parser.add_argument("--room-length", type=float, default=15.0)
    parser.add_argument("--room-width", type=float, default=9.0)
    parser.add_argument("--area-mode", choices=("cell", "zone-grid"), default="cell")
    parser.add_argument("--area-prefix", default="cell")
    parser.add_argument("--zone-rows", type=int, default=3)
    parser.add_argument("--zone-cols", type=int, default=3)
    parser.add_argument("--interface", default="wlan1")
    parser.add_argument("--scan-command", choices=("iw", "iwlist", "mock"), default="iw")
    parser.add_argument("--no-sudo", action="store_true")
    parser.add_argument("--ssid", nargs="+", default=list(DEFAULT_INFRA_SSIDS))
    parser.add_argument("--rssi", nargs="*", default=[])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--region-k", type=int, default=5)
    parser.add_argument("--region-count", type=int, default=1)
    parser.add_argument("--missing-rssi", type=float, default=-100.0)
    parser.add_argument("--weight-power", type=float, default=1.0)
    parser.add_argument("--no-region-filter", action="store_true")
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--x-offset", type=float, default=0.0)
    parser.add_argument("--y-offset", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    radio_map = load_radio_map(
        args.radio_map,
        room_length=args.room_length,
        room_width=args.room_width,
        area_prefix=args.area_prefix,
        area_mode=args.area_mode,
        zone_rows=args.zone_rows,
        zone_cols=args.zone_cols,
    )
    localizer = WKNNLocalizer(
        radio_map,
        k=args.k,
        region_candidate_count=args.region_k,
        region_count=args.region_count,
        missing_rssi=args.missing_rssi,
        weight_power=args.weight_power,
        use_region_filter=not args.no_region_filter,
    )
    rssi_filter = MedianMovingFilter(window_size=args.window)

    print(
        f"Loaded radio map: {len(radio_map.points)} cells, "
        f"{len(radio_map.infrastructure_ids)} infrastructure nodes"
    )
    print(f"Infrastructure: {', '.join(radio_map.infrastructure_ids)}")

    if args.rssi:
        filtered = rssi_filter.update(parse_rssi_pairs(args.rssi))
    else:
        scanner = WifiSsidScanner(
            args.interface,
            args.ssid,
            command=args.scan_command,
            use_sudo=not args.no_sudo,
        )
        print(
            f"Scanning current RSSI from {args.interface} "
            f"({args.samples} samples, command={args.scan_command})"
        )
        try:
            filtered = {}
            for index in range(args.samples):
                sample = scanner.scan()
                filtered = rssi_filter.update(sample)
                visible = ", ".join(
                    f"{ssid}={sample[ssid]:.1f}" for ssid in sorted(sample)
                )
                print(f"  sample {index + 1}/{args.samples}: {visible or 'no target SSID'}")
                if index < args.samples - 1:
                    time.sleep(args.interval)
        except WifiScanError as exc:
            print(exc)
            print()
            print("Try:")
            print(f"  python3 scripts/check_devices.py --interface {args.interface}")
            print(
                f"  python3 scripts/check_devices.py --interface {args.interface} --command iwlist"
            )
            raise SystemExit(3) from exc

    estimate = localizer.estimate(filtered)
    print_estimate(estimate, x_offset=args.x_offset, y_offset=args.y_offset)


if __name__ == "__main__":
    main()
