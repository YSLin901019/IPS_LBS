#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.filters import MedianMovingFilter
from ips_lbs.radio_map import RadioMap
from ips_lbs.scanner import SimulatedScanner
from ips_lbs.service import PositioningService
from ips_lbs.wknn import WKNNLocalizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one simulated WKNN estimate.")
    parser.add_argument("--radio-map", default="data/radio_map_sample.csv")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()

    radio_map = RadioMap.from_csv(args.radio_map)
    service = PositioningService(
        SimulatedScanner(radio_map),
        WKNNLocalizer(radio_map, k=args.k),
        MedianMovingFilter(window_size=3),
    )
    estimate = service.locate_once()
    print(f"area={estimate.area} x={estimate.x:.2f} y={estimate.y:.2f}")
    for point, distance, weight in estimate.neighbors:
        print(f"{point.point_id}: distance={distance:.2f} weight={weight:.4f}")


if __name__ == "__main__":
    main()
