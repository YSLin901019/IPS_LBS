import json
import tempfile
import unittest
from pathlib import Path

from ips_lbs.radio_map import RadioMap
from ips_lbs.wknn import WKNNLocalizer


class UTMJsonTests(unittest.TestCase):
    def test_utm_json_converts_grid_indices_to_absolute_coordinates(self):
        data = {
            "map": {"id": 3, "name": "Test", "rows": 24, "cols": 13, "scans_per_cell": 2},
            "fingerprints": [
                {
                    "row": 23,
                    "col": 12,
                    "ap_data": [
                        {"ssid": "infra_1", "rssi_avg": -42.5},
                        {"ssid": "infra_2", "rssi_avg": -25.5},
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "utm.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            radio_map = RadioMap.from_utm_json(str(path), room_length=15.0, room_width=9.0)

        self.assertEqual(len(radio_map.points), 1)
        point = radio_map.points[0]
        self.assertEqual(point.point_id, "R23C12")
        self.assertAlmostEqual(point.x, 13.8)
        self.assertAlmostEqual(point.y, 7.2)
        self.assertEqual(point.rssi["infra_2"], -25.5)

    def test_wknn_can_estimate_from_utm_json_radio_map(self):
        data = {
            "map": {"id": 3, "name": "Test", "rows": 2, "cols": 2, "scans_per_cell": 2},
            "fingerprints": [
                {"row": 0, "col": 0, "ap_data": [{"ssid": "infra_1", "rssi_avg": -40}]},
                {"row": 0, "col": 1, "ap_data": [{"ssid": "infra_1", "rssi_avg": -60}]},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "utm.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            radio_map = RadioMap.from_utm_json(str(path))

        estimate = WKNNLocalizer(radio_map, k=1).estimate({"infra_1": -41})

        self.assertEqual(estimate.neighbors[0][0].point_id, "R00C00")

    def test_utm_json_can_assign_three_by_three_zone_labels(self):
        data = {
            "map": {"id": 3, "name": "Test", "rows": 6, "cols": 6, "scans_per_cell": 1},
            "fingerprints": [
                {"row": 0, "col": 0, "ap_data": [{"ssid": "infra_1", "rssi_avg": -40}]},
                {"row": 0, "col": 2, "ap_data": [{"ssid": "infra_1", "rssi_avg": -41}]},
                {"row": 0, "col": 4, "ap_data": [{"ssid": "infra_1", "rssi_avg": -42}]},
                {"row": 2, "col": 0, "ap_data": [{"ssid": "infra_1", "rssi_avg": -43}]},
                {"row": 2, "col": 2, "ap_data": [{"ssid": "infra_1", "rssi_avg": -44}]},
                {"row": 2, "col": 4, "ap_data": [{"ssid": "infra_1", "rssi_avg": -45}]},
                {"row": 4, "col": 0, "ap_data": [{"ssid": "infra_1", "rssi_avg": -46}]},
                {"row": 4, "col": 2, "ap_data": [{"ssid": "infra_1", "rssi_avg": -47}]},
                {"row": 4, "col": 4, "ap_data": [{"ssid": "infra_1", "rssi_avg": -48}]},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "utm.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            radio_map = RadioMap.from_utm_json(
                str(path),
                area_prefix="zone",
                area_mode="zone-grid",
                zone_rows=3,
                zone_cols=3,
            )

        self.assertEqual(
            [point.area for point in radio_map.points],
            [
                "zone_A",
                "zone_B",
                "zone_C",
                "zone_D",
                "zone_E",
                "zone_F",
                "zone_G",
                "zone_H",
                "zone_I",
            ],
        )


if __name__ == "__main__":
    unittest.main()
