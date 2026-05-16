import argparse

from ips_lbs.filters import MedianMovingFilter
from ips_lbs.radio_map import RadioMap
from ips_lbs.scanner import IwlistScanner, SimulatedScanner
from ips_lbs.service import PositioningService
from ips_lbs.wknn import WKNNLocalizer


def add_positioning_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--radio-map", default="data/radio_map_sample.csv")
    parser.add_argument("--mode", choices=("sim", "iwlist"), default="sim")
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--bssid-map", nargs="*", default=[])
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--region-k", type=int, default=5)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--interval-ms", type=int, default=3000)


def build_service(args: argparse.Namespace) -> tuple:
    radio_map = RadioMap.from_csv(args.radio_map)
    localizer = WKNNLocalizer(radio_map, k=args.k, region_candidate_count=args.region_k)
    scanner = SimulatedScanner(radio_map)
    if args.mode == "iwlist":
        mapping = {}
        for item in args.bssid_map:
            bssid, node_id = item.split("=", 1)
            mapping[bssid] = node_id
        scanner = IwlistScanner(args.interface, mapping)
    service = PositioningService(scanner, localizer, MedianMovingFilter(args.window))
    return radio_map, service

