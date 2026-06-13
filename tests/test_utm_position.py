import unittest

from scripts.locate import build_position_payload


class UTMPositionTests(unittest.TestCase):
    def test_build_position_payload_includes_coordinates_and_height(self):
        payload = build_position_payload(
            map_id=11,
            row=4,
            col=11,
            confidence=0.69,
            x=13.27,
            y=1.69,
            z=0.0,
        )

        self.assertEqual(
            payload,
            {
                "map_id": 11,
                "row": 4,
                "col": 11,
                "confidence": 0.69,
                "x": 13.27,
                "y": 1.69,
                "z": 0.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
