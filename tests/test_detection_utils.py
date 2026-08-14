import unittest

from detection import Detection, bbox_iou, consensus


def d(bbox, conf=0.8, cls="fire"):
    return Detection(
        bbox=bbox,
        model_class=cls.capitalize(),
        canonical_class=cls,
        confidence=conf,
        distance_m=None,
        bearing_deg=0.0,
        gps=None,
        distance_quality="unavailable",
    )


class IoUTests(unittest.TestCase):
    def test_identical_boxes(self):
        self.assertAlmostEqual(
            bbox_iou((10, 10, 50, 50), (10, 10, 50, 50)),
            1.0,
        )

    def test_separate_boxes(self):
        self.assertEqual(
            bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)),
            0.0,
        )

    def test_same_object_two_frames_confirmed(self):
        sets = [
            [d((100, 100, 200, 200), 0.70)],
            [d((105, 103, 205, 203), 0.85)],
            [],
        ]
        result = consensus(sets, min_frames=2, iou_threshold=0.30)

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].confidence, 0.85)

    def test_same_class_far_apart_not_confirmed(self):
        sets = [
            [d((10, 10, 80, 80), 0.90)],
            [d((500, 400, 580, 480), 0.95)],
            [],
        ]
        result = consensus(sets, min_frames=2, iou_threshold=0.30)

        self.assertEqual(result, [])

    def test_two_real_objects_can_both_confirm(self):
        sets = [
            [
                d((10, 10, 80, 80), 0.80),
                d((300, 300, 380, 380), 0.81),
            ],
            [
                d((12, 12, 82, 82), 0.90),
                d((302, 303, 382, 383), 0.91),
            ],
            [],
        ]

        result = consensus(sets, min_frames=2, iou_threshold=0.30)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
