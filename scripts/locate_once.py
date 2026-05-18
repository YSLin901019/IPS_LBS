#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.filters import MedianMovingFilter
from ips_lbs.radio_map import load_radio_map
from ips_lbs.scanner import SimulatedScanner
from ips_lbs.service import PositioningService
from ips_lbs.wknn import WKNNLocalizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one simulated WKNN estimate.")
    parser.add_argument("--radio-map", default="data/radio_map_sample.csv")
    parser.add_argument("--room-length", type=float, default=15.0)
    parser.add_argument("--room-width", type=float, default=9.0)
    parser.add_argument("--area-mode", choices=("cell", "zone-grid"), default="cell")
    parser.add_argument("--area-prefix", default="cell")
    parser.add_argument("--zone-rows", type=int, default=3)
    parser.add_argument("--zone-cols", type=int, default=3)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--region-k", type=int, default=5)
    parser.add_argument("--region-count", type=int, default=1)
    parser.add_argument("--missing-rssi", type=float, default=-100.0)
    parser.add_argument("--weight-power", type=float, default=1.0)
    parser.add_argument("--no-region-filter", action="store_true")
    args = parser.parse_args()

    radio_map = load_radio_map(
        args.radio_map,
        room_length=args.room_length,
        room_width=args.room_width,
        area_prefix=args.area_prefix,
        area_mode=args.area_mode,
        zone_rows=args.zone_rows,
        zone_cols=args.zone_cols,
    )
    service = PositioningService(
        SimulatedScanner(radio_map),
        WKNNLocalizer(
            radio_map,
            k=args.k,
            region_candidate_count=args.region_k,
            region_count=args.region_count,
            missing_rssi=args.missing_rssi,
            weight_power=args.weight_power,
            use_region_filter=not args.no_region_filter,
        ),
        MedianMovingFilter(window_size=3),
    )
    estimate = service.locate_once()
    print(f"area={estimate.area} x={estimate.x:.2f} y={estimate.y:.2f}")
    for point, distance, weight in estimate.neighbors:
        print(f"{point.point_id}: distance={distance:.2f} weight={weight:.4f}")


if __name__ == "__main__":
    main()
