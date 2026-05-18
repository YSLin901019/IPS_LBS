import argparse

from ips_lbs.filters import MedianMovingFilter
from ips_lbs.radio_map import load_radio_map
from ips_lbs.scanner import IwlistScanner, SimulatedScanner
from ips_lbs.service import PositioningService
from ips_lbs.wknn import WKNNLocalizer


def add_positioning_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--radio-map", default="data/radio_map_sample.csv")
    parser.add_argument("--room-length", type=float, default=15.0)
    parser.add_argument("--room-width", type=float, default=9.0)
    parser.add_argument("--area-mode", choices=("cell", "zone-grid"), default="cell")
    parser.add_argument("--area-prefix", default="cell")
    parser.add_argument("--zone-rows", type=int, default=3)
    parser.add_argument("--zone-cols", type=int, default=3)
    parser.add_argument("--mode", choices=("sim", "iwlist"), default="sim")
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--bssid-map", nargs="*", default=[])
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--region-k", type=int, default=5)
    parser.add_argument("--region-count", type=int, default=1)
    parser.add_argument("--missing-rssi", type=float, default=-100.0)
    parser.add_argument("--weight-power", type=float, default=1.0)
    parser.add_argument("--no-region-filter", action="store_true")
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--interval-ms", type=int, default=3000)


def build_service(args: argparse.Namespace) -> tuple:
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
    scanner = SimulatedScanner(radio_map)
    if args.mode == "iwlist":
        mapping = {}
        for item in args.bssid_map:
            bssid, node_id = item.split("=", 1)
            mapping[bssid] = node_id
        scanner = IwlistScanner(args.interface, mapping)
    service = PositioningService(scanner, localizer, MedianMovingFilter(args.window))
    return radio_map, service
