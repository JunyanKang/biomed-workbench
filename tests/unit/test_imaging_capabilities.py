import unittest

from biomed_workbench.capabilities.imaging import colocalization, image_profile, segment_components, track_points


class ImagingCapabilityTests(unittest.TestCase):
    def test_image_profile_reports_known_statistics(self):
        result = image_profile([[0, 1], [2, 3]])
        self.assertEqual(result["shape"], [2, 2])
        self.assertEqual(result["minimum"], 0.0)
        self.assertEqual(result["maximum"], 3.0)
        self.assertEqual(result["mean"], 1.5)

    def test_segmentation_recovers_component_geometry(self):
        image = [
            [0, 0, 0, 0, 0],
            [0, 5, 5, 0, 0],
            [0, 5, 5, 0, 7],
            [0, 0, 0, 0, 7],
        ]
        result = segment_components(image, threshold=4, connectivity=4, minimum_area=1)
        self.assertEqual(result["component_count"], 2)
        first = result["components"][0]
        self.assertEqual(first["area"], 4)
        self.assertEqual(first["bounding_box"], {"min_row": 2, "min_column": 2, "max_row": 3, "max_column": 3})
        self.assertEqual(first["centroid"], {"row": 2.5, "column": 2.5})
        self.assertEqual(first["perimeter"], 8)

    def test_colocalization_reports_pearson_and_manders(self):
        result = colocalization([[0, 1], [2, 3]], [[0, 2], [4, 6]], threshold_a=0, threshold_b=0)
        self.assertAlmostEqual(result["pearson_r"], 1.0)
        self.assertAlmostEqual(result["manders_m1"], 1.0)
        self.assertAlmostEqual(result["manders_m2"], 1.0)

    def test_point_tracking_links_nearest_candidates_and_starts_new_tracks(self):
        result = track_points(
            frames=[[[0, 0], [10, 10]], [[1, 0], [20, 20]], [[2, 0]]],
            max_distance=2,
        )
        lengths = sorted(len(track["points"]) for track in result["tracks"])
        self.assertEqual(lengths, [1, 1, 3])
        longest = max(result["tracks"], key=lambda track: len(track["points"]))
        self.assertEqual([point["x"] for point in longest["points"]], [0.0, 1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
