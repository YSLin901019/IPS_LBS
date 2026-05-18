import unittest

from ips_lbs.radio_map import RadioMap
from ips_lbs.models import ReferencePoint
from ips_lbs.wknn import WKNNLocalizer


class WKNNTests(unittest.TestCase):
    def test_wknn_estimates_near_matching_reference_point(self):
        radio_map = RadioMap.from_csv("data/radio_map_sample.csv")
        localizer = WKNNLocalizer(radio_map, k=3)

        estimate = localizer.estimate(
            {"infra_1": -63, "infra_2": -61, "infra_3": -61, "infra_4": -63}
        )

        self.assertEqual(estimate.area, "中央區")
        self.assertTrue(5.0 <= estimate.x <= 10.0)
        self.assertTrue(3.0 <= estimate.y <= 6.0)
        self.assertEqual(len(estimate.neighbors), 3)

    def test_empty_sample_returns_unknown(self):
        radio_map = RadioMap.from_csv("data/radio_map_sample.csv")
        localizer = WKNNLocalizer(radio_map)

        estimate = localizer.estimate({})

        self.assertEqual(estimate.area, "unknown")
        self.assertEqual(estimate.confidence, 0.0)

    def test_weight_power_changes_neighbor_blending(self):
        radio_map = RadioMap.from_csv("data/radio_map_sample.csv")
        sample = {"infra_1": -63, "infra_2": -61, "infra_3": -61, "infra_4": -63}

        estimate_soft = WKNNLocalizer(
            radio_map, k=3, use_region_filter=False, weight_power=1.0
        ).estimate(sample)
        estimate_sharp = WKNNLocalizer(
            radio_map, k=3, use_region_filter=False, weight_power=2.0
        ).estimate(sample)

        self.assertNotEqual(
            round(estimate_soft.neighbors[1][2], 6),
            round(estimate_sharp.neighbors[1][2], 6),
        )

    def test_region_count_keeps_top_n_regions_as_candidates(self):
        radio_map = RadioMap(
            [
                ReferencePoint("A1", "zone_A", 0.0, 0.0, {"infra_1": -40}),
                ReferencePoint("A2", "zone_A", 1.0, 0.0, {"infra_1": -41}),
                ReferencePoint("B1", "zone_B", 10.0, 0.0, {"infra_1": -42}),
                ReferencePoint("B2", "zone_B", 11.0, 0.0, {"infra_1": -43}),
                ReferencePoint("C1", "zone_C", 20.0, 0.0, {"infra_1": -80}),
                ReferencePoint("C2", "zone_C", 21.0, 0.0, {"infra_1": -81}),
            ]
        )

        estimate = WKNNLocalizer(
            radio_map,
            k=3,
            region_candidate_count=4,
            region_count=2,
        ).estimate({"infra_1": -42})

        self.assertEqual({point.area for point, _, _ in estimate.neighbors}, {"zone_A", "zone_B"})


if __name__ == "__main__":
    unittest.main()
