#!/usr/bin/env python3
import argparse
import csv
import math
import sys
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ips_lbs.models import ReferencePoint, RssiVector
from ips_lbs.radio_map import RadioMap, load_radio_map


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def percentile(values: list[float], percentile_rank: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile_rank
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def distance_m(a: ReferencePoint, x: float, y: float) -> float:
    return math.hypot(a.x - x, a.y - y)


def rssi_distance(
    sample: RssiVector,
    fingerprint: RssiVector,
    infrastructure_ids: list[str],
    missing_rssi: float,
) -> float:
    total = 0.0
    for node_id in infrastructure_ids:
        total += (
            sample.get(node_id, missing_rssi)
            - fingerprint.get(node_id, missing_rssi)
        ) ** 2
    return math.sqrt(total)


def build_distance_matrix(
    points: list[ReferencePoint],
    infrastructure_ids: list[str],
    missing_rssi: float,
) -> list[list[float]]:
    matrix = []
    for sample in points:
        matrix.append(
            [
                rssi_distance(
                    sample.rssi,
                    fingerprint.rssi,
                    infrastructure_ids,
                    missing_rssi,
                )
                for fingerprint in points
            ]
        )
    return matrix


def evaluate(
    points: list[ReferencePoint],
    ranked_neighbors: list[list[int]],
    distance_matrix: list[list[float]],
    k: int,
    region_k: int,
    region_count: int,
    weight_power: float,
    use_region_filter: bool,
    epsilon: float = 1e-6,
) -> dict:
    errors = []
    nearest_errors = []

    for index, expected in enumerate(points):
        ranked = [neighbor for neighbor in ranked_neighbors[index] if neighbor != index]
        candidates = ranked
        if use_region_filter:
            vote_limit = max(region_k, k)
            votes = {}
            counts = {}
            for neighbor in ranked[:vote_limit]:
                area = points[neighbor].area
                distance = distance_matrix[index][neighbor]
                weight = 1.0 / ((distance + epsilon) ** weight_power)
                votes[area] = votes.get(area, 0.0) + weight
                counts[area] = counts.get(area, 0) + 1
            regions = sorted(
                votes,
                key=lambda area: (votes[area], counts[area]),
                reverse=True,
            )[:region_count]
            region_candidates = [
                neighbor for neighbor in ranked if points[neighbor].area in regions
            ]
            if len(region_candidates) >= k:
                candidates = region_candidates

        neighbors = candidates[:k]
        weighted = []
        for neighbor in neighbors:
            distance = distance_matrix[index][neighbor]
            weight = 1.0 / ((distance + epsilon) ** weight_power)
            weighted.append((neighbor, weight))

        weight_sum = sum(weight for _, weight in weighted)
        x = sum(points[neighbor].x * weight for neighbor, weight in weighted) / weight_sum
        y = sum(points[neighbor].y * weight for neighbor, weight in weighted) / weight_sum
        error = distance_m(expected, x, y)
        errors.append(error)

        if neighbors:
            nearest = points[neighbors[0]]
            nearest_errors.append(distance_m(expected, nearest.x, nearest.y))

    return {
        "k": k,
        "region_k": region_k,
        "region_count": region_count,
        "weight_power": weight_power,
        "use_region_filter": use_region_filter,
        "mean_error_m": mean(errors),
        "median_error_m": median(errors),
        "p90_error_m": percentile(errors, 0.9),
        "max_error_m": max(errors),
        "nearest_mean_error_m": mean(nearest_errors),
        "samples": len(points),
    }


def write_results(path: str, results: list[dict]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "k",
        "region_k",
        "region_count",
        "missing_rssi",
        "weight_power",
        "use_region_filter",
        "mean_error_m",
        "median_error_m",
        "p90_error_m",
        "max_error_m",
        "nearest_mean_error_m",
        "samples",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, row in enumerate(results, start=1):
            formatted = {"rank": rank, **row}
            for key in (
                "mean_error_m",
                "median_error_m",
                "p90_error_m",
                "max_error_m",
                "nearest_mean_error_m",
            ):
                formatted[key] = f"{formatted[key]:.4f}"
            writer.writerow(formatted)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tune WKNN parameters with leave-one-out validation."
    )
    parser.add_argument("radio_map")
    parser.add_argument("--room-length", type=float, default=15.0)
    parser.add_argument("--room-width", type=float, default=9.0)
    parser.add_argument("--area-mode", choices=("cell", "zone-grid"), default="cell")
    parser.add_argument("--area-prefix", default="cell")
    parser.add_argument("--zone-rows", type=int, default=3)
    parser.add_argument("--zone-cols", type=int, default=3)
    parser.add_argument("--k-values", default="1,2,3,4,5,6,7,8,9,10")
    parser.add_argument("--region-k-values", default="3,5,8,10,15,20")
    parser.add_argument("--region-count-values", default="1")
    parser.add_argument("--missing-rssi-values", default="-100,-95,-90")
    parser.add_argument("--weight-power-values", default="1.0,1.5,2.0")
    parser.add_argument(
        "--region-filter",
        choices=("both", "on", "off"),
        default="both",
        help="Whether to include the area/region pre-filter in the search.",
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", default="data/wknn_tuning_results.csv")
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
    points = radio_map.points
    if len(points) < 2:
        raise ValueError("Need at least two reference points for leave-one-out tuning")

    region_filter_values = {
        "both": [False, True],
        "on": [True],
        "off": [False],
    }[args.region_filter]

    results = []
    for missing_rssi in parse_float_list(args.missing_rssi_values):
        distance_matrix = build_distance_matrix(
            points,
            radio_map.infrastructure_ids,
            missing_rssi,
        )
        ranked_neighbors = [
            sorted(range(len(points)), key=lambda neighbor: distances[neighbor])
            for distances in distance_matrix
        ]
        for k in parse_int_list(args.k_values):
            if k >= len(points):
                continue
            for region_k in parse_int_list(args.region_k_values):
                for region_count in parse_int_list(args.region_count_values):
                    for weight_power in parse_float_list(args.weight_power_values):
                        for use_region_filter in region_filter_values:
                            result = evaluate(
                                points,
                                ranked_neighbors=ranked_neighbors,
                                distance_matrix=distance_matrix,
                                k=k,
                                region_k=region_k,
                                region_count=region_count,
                                weight_power=weight_power,
                                use_region_filter=use_region_filter,
                            )
                            result["missing_rssi"] = missing_rssi
                            results.append(result)

    results.sort(
        key=lambda row: (
            row["mean_error_m"],
            row["p90_error_m"],
            row["median_error_m"],
            row["k"],
        )
    )
    write_results(args.output, results)

    best = results[0]
    print(f"Loaded {len(points)} reference points from {args.radio_map}")
    print(f"Wrote full ranking to {args.output}")
    print(
        "Best: "
        f"k={best['k']} region_k={best['region_k']} "
        f"region_count={best['region_count']} "
        f"missing_rssi={best['missing_rssi']:.1f} "
        f"weight_power={best['weight_power']:.1f} "
        f"region_filter={'on' if best['use_region_filter'] else 'off'} "
        f"mean={best['mean_error_m']:.3f}m "
        f"median={best['median_error_m']:.3f}m "
        f"p90={best['p90_error_m']:.3f}m "
        f"max={best['max_error_m']:.3f}m "
        f"nearest_mean={best['nearest_mean_error_m']:.3f}m"
    )
    print()
    print("Top results:")
    for rank, row in enumerate(results[: args.top], start=1):
        print(
            f"{rank:>2}. k={row['k']:<2} region_k={row['region_k']:<2} "
            f"regions={row['region_count']:<2} "
            f"missing={row['missing_rssi']:<6.1f} "
            f"power={row['weight_power']:<3.1f} "
            f"region={'on ' if row['use_region_filter'] else 'off'} "
            f"mean={row['mean_error_m']:.3f}m "
            f"median={row['median_error_m']:.3f}m "
            f"p90={row['p90_error_m']:.3f}m"
        )


if __name__ == "__main__":
    main()
