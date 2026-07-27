import unittest

from biomed_workbench.capabilities.imaging import (
    colocalization,
    image_profile,
    medical_metadata_audit,
    medical_volume_summary,
    register_image_translation,
    scientific_illustration_generation,
    segment_components,
    summarize_cell_migration_tracks,
    track_points,
)


class ImagingCapabilityTests(unittest.TestCase):
    def test_cell_migration_metrics_preserve_calibration_and_directionality(self):
        result = summarize_cell_migration_tracks([{"track_id": 1, "points": [{"frame": 0, "x": 0, "y": 0}, {"frame": 1, "x": 3, "y": 4}, {"frame": 2, "x": 6, "y": 4}]}], time_interval_min=2)
        self.assertEqual(result["included_track_count"], 1)
        self.assertEqual(result["track_metrics"][0]["path_length_um"], 8.0)
        self.assertEqual(result["track_metrics"][0]["speed_um_per_min"], 2.0)
        self.assertEqual(result["track_metrics"][0]["directionality"], 0.90138782)

    def test_integer_translation_registration_recovers_known_shift(self):
        fixed = [[0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        moving = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 0]]
        result = register_image_translation(fixed, moving, max_shift_pixels=2)

        self.assertEqual(result["transform"]["fixed_to_moving_row_shift"], -1)
        self.assertEqual(result["transform"]["fixed_to_moving_column_shift"], -1)
        self.assertEqual(result["mean_squared_error"], 0.0)

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
        self.assertEqual(first["axis_aspect_ratio"], 1.0)
        self.assertEqual(first["eccentricity_second_moment"], 0.0)
        self.assertEqual(first["orientation_degrees_from_column_axis"], 0.0)

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

    def test_scientific_illustration_handoff_is_codex_native_and_non_evidentiary(self):
        result = scientific_illustration_generation(
            "retinal progenitor differentiation into rods and cones",
            "BANP loss disrupts the transition from progenitor state to mature photoreceptor lineages",
            "conceptual-mechanism",
            labels=["RPC", "Rod", "Cone"],
            palette=["teal progenitor", "magenta rod", "gold cone"],
            visual_semantics=["solid arrows indicate differentiation", "dashed bar indicates disrupted transition"],
            constraints=["white background", "color-blind-safe lineage colors"],
            avoid=["photorealistic microscopy"],
            disclosure_context="manuscript",
        )

        self.assertTrue(result["ready"])
        self.assertEqual(result["representation_scope"], "scientific-communication-only")
        self.assertEqual(result["execution_handoff"]["tool"], "image_gen")
        self.assertEqual(result["execution_handoff"]["authentication"], "codex-managed")
        self.assertFalse(result["execution_handoff"]["cli_fallback_allowed"])
        self.assertIn("not measured data", result["execution_handoff"]["prompt"])
        self.assertIn("Visual semantics", result["execution_handoff"]["prompt"])
        self.assertEqual(result["disclosure_context"], "manuscript")
        self.assertEqual({gate["id"] for gate in result["quality_gates"]}, {"generated-not-observed-data", "scientific-accuracy-review", "text-label-fidelity", "reference-invariant-preservation", "generation-disclosure"})

    def test_scientific_illustration_edit_requires_visible_reference_and_rejects_unknown_modes(self):
        with self.assertRaisesRegex(ValueError, "visible reference"):
            scientific_illustration_generation("cell", "show a conceptual edit", "scientific-illustration", mode="edit")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            scientific_illustration_generation("cell", "show data", "microscopy-result")

    def test_medical_volume_summary_validates_3d_shape_and_returns_expected_statistics(self):
        result = medical_volume_summary(
            volume=[
                [[0, 1], [2, 3]],
                [[4, 5], [6, 7]],
            ],
            mm_per_voxel=(1.0, 1.0, 1.5),
        )

        self.assertEqual(result["shape"], [2, 2, 2])
        self.assertEqual(result["voxel_geometry"]["voxel_count"], 8)
        self.assertAlmostEqual(result["intensity"]["mean"], 3.5)
        self.assertEqual(len(result["intensity"]["mean_by_slice"]), 2)
        self.assertEqual(result["intensity"]["mean_by_slice"][0]["slice"], 0)

    def test_medical_metadata_audit_flags_potential_pii_and_missing_required_fields(self):
        result = medical_metadata_audit(
            metadata={
                "PatientID": "P-01",
                "Modality": "MR",
                "SeriesDescription": "T2 FLAIR",
                "StudyDate": "20260101",
            },
            minimum_required_fields=["Modality", "StudyDate", "StudyInstanceUID", "SeriesDescription", "PixelSpacing"],
        )

        self.assertEqual(result["declared_modality"], "MR")
        self.assertTrue(result["pii_risk"]["has_potential_pii_key"])
        self.assertEqual(result["pii_risk"]["risk_level"], "high")
        self.assertIn("studyinstanceuid", result["required_fields"]["missing"])
        self.assertIn("pixelspacing", result["required_fields"]["missing"])
        self.assertIn("patientid", result["pii_risk"]["sensitive_fields"])


if __name__ == "__main__":
    unittest.main()
