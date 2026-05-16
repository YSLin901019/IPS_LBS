import unittest

from ips_lbs.radio_map import RadioMap
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


if __name__ == "__main__":
    unittest.main()
