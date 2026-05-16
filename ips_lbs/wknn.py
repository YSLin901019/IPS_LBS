import math
from collections import Counter, defaultdict
from typing import Iterable, List, Optional

from ips_lbs.models import PositionEstimate, ReferencePoint, RssiVector
from ips_lbs.radio_map import RadioMap


MISSING_RSSI = -100.0


def euclidean_distance(
    sample: RssiVector, fingerprint: RssiVector, infrastructure_ids: Iterable[str]
) -> float:
    total = 0.0
    for node_id in infrastructure_ids:
        observed = sample.get(node_id, MISSING_RSSI)
        reference = fingerprint.get(node_id, MISSING_RSSI)
        total += (observed - reference) ** 2
    return math.sqrt(total)


class WKNNLocalizer:
    def __init__(
        self,
        radio_map: RadioMap,
        k: int = 3,
        region_candidate_count: int = 5,
        epsilon: float = 1e-6,
    ) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        self.radio_map = radio_map
        self.k = k
        self.region_candidate_count = max(region_candidate_count, k)
        self.epsilon = epsilon

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

        region = self._classify_region(sample)
        candidates = [
            point for point in self.radio_map.points if point.area == region
        ] or self.radio_map.points

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
                sample, point.rssi, self.radio_map.infrastructure_ids
            )
            weight = 1.0 / (distance + self.epsilon)
            ranked.append((point, distance, weight))
        return sorted(ranked, key=lambda item: item[1])

    def _classify_region(self, sample: RssiVector) -> str:
        ranked = self._rank(sample, self.radio_map.points)
        top = ranked[: self.region_candidate_count]
        votes = defaultdict(float)
        counts = Counter()
        for point, distance, weight in top:
            votes[point.area] += weight
            counts[point.area] += 1
        if not votes:
            return "unknown"
        return max(votes, key=lambda area: (votes[area], counts[area]))

