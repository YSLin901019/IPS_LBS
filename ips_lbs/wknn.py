import math
from collections import Counter, defaultdict
from typing import Iterable, List, Optional

from ips_lbs.models import PositionEstimate, ReferencePoint, RssiVector
from ips_lbs.radio_map import RadioMap


MISSING_RSSI = -100.0


def euclidean_distance(
    sample: RssiVector,
    fingerprint: RssiVector,
    infrastructure_ids: Iterable[str],
    missing_rssi: float = MISSING_RSSI,
) -> float:
    total = 0.0
    for node_id in infrastructure_ids:
        observed = sample.get(node_id, missing_rssi)
        reference = fingerprint.get(node_id, missing_rssi)
        total += (observed - reference) ** 2
    return math.sqrt(total)


class WKNNLocalizer:
    def __init__(
        self,
        radio_map: RadioMap,
        k: int = 3,
        region_candidate_count: int = 5,
        epsilon: float = 1e-6,
        missing_rssi: float = MISSING_RSSI,
        weight_power: float = 1.0,
        use_region_filter: bool = True,
        region_count: int = 1,
    ) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        if weight_power <= 0:
            raise ValueError("weight_power must be > 0")
        self.radio_map = radio_map
        self.k = k
        self.region_candidate_count = max(region_candidate_count, k)
        self.epsilon = epsilon
        self.missing_rssi = missing_rssi
        self.weight_power = weight_power
        self.use_region_filter = use_region_filter
        self.region_count = max(1, region_count)

    def estimate(self, sample: RssiVector) -> PositionEstimate:
        if not sample:
            return PositionEstimate(
                x=0.0,
                y=0.0,
                area="unknown",
                confidence=0.0,
                neighbors=[],
                raw_rssi={},
                filtered_rssi={},
                message="No RSSI sample available.",
            )

        regions = self._classify_regions(sample)
        region = regions[0] if regions else "unknown"
        candidates = self.radio_map.points
        if self.use_region_filter:
            candidates = [
                point for point in self.radio_map.points if point.area in regions
            ] or self.radio_map.points
            if len(candidates) < self.k:
                candidates = self.radio_map.points

        ranked = self._rank(sample, candidates)
        neighbors = ranked[: self.k]
        weight_sum = sum(weight for _, _, weight in neighbors)

        if weight_sum <= 0:
            best = neighbors[0][0]
            return PositionEstimate(
                x=best.x,
                y=best.y,
                area=best.area,
                confidence=0.0,
                neighbors=neighbors,
                raw_rssi=dict(sample),
                filtered_rssi=dict(sample),
                message="Unable to compute positive WKNN weights.",
            )

        x = sum(point.x * weight for point, _, weight in neighbors) / weight_sum
        y = sum(point.y * weight for point, _, weight in neighbors) / weight_sum
        best_distance = neighbors[0][1]
        confidence = 1.0 / (1.0 + best_distance)
        return PositionEstimate(
            x=x,
            y=y,
            area=region,
            confidence=confidence,
            neighbors=neighbors,
            raw_rssi=dict(sample),
            filtered_rssi=dict(sample),
        )

    def _rank(
        self, sample: RssiVector, points: Iterable[ReferencePoint]
    ) -> List[tuple]:
        ranked = []
        for point in points:
            distance = euclidean_distance(
                sample,
                point.rssi,
                self.radio_map.infrastructure_ids,
                missing_rssi=self.missing_rssi,
            )
            weight = 1.0 / ((distance + self.epsilon) ** self.weight_power)
            ranked.append((point, distance, weight))
        return sorted(ranked, key=lambda item: item[1])

    def _classify_regions(self, sample: RssiVector) -> List[str]:
        ranked = self._rank(sample, self.radio_map.points)
        top = ranked[: self.region_candidate_count]
        votes = defaultdict(float)
        counts = Counter()
        for point, distance, weight in top:
            votes[point.area] += weight
            counts[point.area] += 1
        if not votes:
            return ["unknown"]
        return sorted(
            votes,
            key=lambda area: (votes[area], counts[area]),
            reverse=True,
        )[: self.region_count]

    def _classify_region(self, sample: RssiVector) -> str:
        return self._classify_regions(sample)[0]
