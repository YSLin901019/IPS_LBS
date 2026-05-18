#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.radio_map import RadioMap


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert cloud UTM fingerprint JSON into radio map CSV."
    )
    parser.add_argument("input_json")
    parser.add_argument("output_csv")
    parser.add_argument("--room-length", type=float, default=15.0)
    parser.add_argument("--room-width", type=float, default=9.0)
    parser.add_argument("--area-prefix", default="cell")
    parser.add_argument("--area-mode", choices=("cell", "zone-grid"), default="cell")
    parser.add_argument("--zone-rows", type=int, default=3)
    parser.add_argument("--zone-cols", type=int, default=3)
    args = parser.parse_args()

    radio_map = RadioMap.from_utm_json(
        args.input_json,
        room_length=args.room_length,
        room_width=args.room_width,
        area_prefix=args.area_prefix,
        area_mode=args.area_mode,
        zone_rows=args.zone_rows,
        zone_cols=args.zone_cols,
    )
    radio_map.to_csv(args.output_csv)
    print(
        f"Converted {args.input_json} -> {args.output_csv}: "
        f"{len(radio_map.points)} cells, "
        f"{len(radio_map.infrastructure_ids)} infrastructure nodes."
    )


if __name__ == "__main__":
    main()
