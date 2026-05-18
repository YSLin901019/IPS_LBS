#!/usr/bin/env python3
"""
Live WiFi positioning — scans RSSI, runs WKNN, and optionally reports
the estimated cell to the SkyNode UTM backend in a loop.

Usage (one-shot, no reporting):
    python scripts/locate_live.py --radio-map data/indoor-map-11.json

Usage (continuous loop, report to UTM):
    python scripts/locate_live.py \
        --radio-map data/indoor-map-11.json \
        --map-id 11 \
        --loop --loop-interval 5
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import json as _json
import urllib.request
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


def extract_row_col(point_id: str) -> tuple[int, int] | None:
    match = re.match(r"R(\d+)C(\d+)$", point_id)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def post_position(utm_url: str, utm_key: str, map_id: int, row: int, col: int, confidence: float) -> None:
    url = f"{utm_url.rstrip('/')}/api/indoor/position"
    payload = _json.dumps({"map_id": map_id, "row": row, "col": col, "confidence": confidence}).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {utm_key}")
    req.add_header("User-Agent", "SkyNode-UTM-Drone/1.0")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  → UTM updated: row={row} col={col} (HTTP {resp.status})")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"  → UTM report failed: HTTP {exc.code} body={detail}")
    except Exception as exc:
        print(f"  → UTM report failed: {exc}")


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
    parser.add_argument("--radio-map", default="data/indoor-map-11 (4).json")
    parser.add_argument("--room-length", type=float, default=15.0)
    parser.add_argument("--room-width", type=float, default=9.0)
    parser.add_argument("--interface", default="wlan1")
    parser.add_argument("--scan-command", choices=("iw", "iwlist", "mock"), default="iw")
    parser.add_argument("--no-sudo", action="store_true")
    parser.add_argument("--ssid", nargs="+", default=list(DEFAULT_INFRA_SSIDS))
    parser.add_argument("--rssi", nargs="*", default=[])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--region-k", type=int, default=5)
    parser.add_argument("--missing-rssi", type=float, default=-100.0)
    parser.add_argument("--weight-power", type=float, default=1.0)
    parser.add_argument("--no-region-filter", action="store_true")
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--x-offset", type=float, default=0.0)
    parser.add_argument("--y-offset", type=float, default=0.0)
    # UTM reporting
    parser.add_argument("--utm-url", default="https://skynode-utm-api.h03895-64272.workers.dev", help="SkyNode UTM backend URL, e.g. https://ky-ode.h03895.workers.dev")
    parser.add_argument("--utm-key", default="sk_9d2af2ee656168fc32fc08ddadb3a1f4327e8d92c50d69f371bbf6758011109c", help="Device API key (Bearer token)")
    parser.add_argument("--map-id", type=int, default=None, help="Indoor map ID to report position to")
    # Loop mode
    parser.add_argument("--loop", action="store_true", help="Keep scanning and reporting in a loop")
    parser.add_argument("--loop-interval", type=float, default=5.0, help="Seconds between loop iterations (default: 5)")
    return parser.parse_args()


def run_estimate(args, localizer, rssi_filter, scanner=None):
    """Run one scan+estimate cycle. Returns the estimate object."""
    if args.rssi:
        filtered = rssi_filter.update(parse_rssi_pairs(args.rssi))
    else:
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

    return localizer.estimate(filtered)


def main() -> None:
    args = parse_args()
    radio_map = load_radio_map(
        args.radio_map,
        room_length=args.room_length,
        room_width=args.room_width,
    )
    localizer = WKNNLocalizer(
        radio_map,
        k=args.k,
        region_candidate_count=args.region_k,
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

    utm_enabled = bool(args.utm_url and args.utm_key and args.map_id is not None)
    if utm_enabled:
        print(f"UTM reporting: {args.utm_url}  map_id={args.map_id}")
    if args.loop:
        print(f"Loop mode: every {args.loop_interval}s  (Ctrl+C to stop)")

    scanner = None
    if not args.rssi:
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

    iteration = 0
    try:
        while True:
            iteration += 1
            if args.loop:
                print(f"\n--- Iteration {iteration} ---")

            estimate = run_estimate(args, localizer, rssi_filter, scanner)
            print_estimate(estimate, x_offset=args.x_offset, y_offset=args.y_offset)

            if utm_enabled and estimate.neighbors:
                best_point = estimate.neighbors[0][0]
                rc = extract_row_col(best_point.point_id)
                if rc:
                    post_position(args.utm_url, args.utm_key, args.map_id, rc[0], rc[1], estimate.confidence)
                else:
                    print(f"  → Cannot parse cell id: {best_point.point_id}")

            if not args.loop:
                break
            time.sleep(args.loop_interval)

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
