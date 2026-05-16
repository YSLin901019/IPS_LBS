#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.radio_map import RadioMap


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert repeated RSSI samples into a median radio map."
    )
    parser.add_argument("samples_csv", help="CSV with repeated measurements")
    parser.add_argument("output_csv", help="Path for the generated radio map")
    parser.add_argument(
        "--group-column",
        action="append",
        default=[],
        help="Column used to group repeated samples. Defaults to point_id, area, x, y.",
    )
    args = parser.parse_args()

    radio_map = RadioMap.from_samples(
        args.samples_csv, args.output_csv, group_columns=args.group_column
    )
    print(
        f"Generated {args.output_csv} with {len(radio_map.points)} reference points "
        f"and {len(radio_map.infrastructure_ids)} infrastructure nodes."
    )


if __name__ == "__main__":
    main()
