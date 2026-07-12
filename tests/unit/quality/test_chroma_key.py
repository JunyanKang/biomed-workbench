import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from biomed_workbench.implementations.chroma_key import remove_chroma_key
from biomed_workbench.quality import ChromaKeyReportError, parse_chroma_key_outputs


PARAMETERS = {
    "source_format": "png",
    "key_color": "#00ff00",
    "auto_key": "corners",
    "transparent_threshold": 8.0,
    "opaque_threshold": 90.0,
    "auto_key_maximum_deviation": 18.0,
    "auto_key_minimum_consensus": 0.9,
    "despill_strength": 1.0,
    "edge_contract": 0,
    "edge_feather": 0.0,
}


def synthetic_source(path: Path) -> None:
    image = Image.new("RGBA", (64, 64), (0, 255, 0, 255))
    pixels = image.load()
    for y in range(16, 48):
        for x in range(16, 48):
            pixels[x, y] = (224, 24, 40, 255)
    for offset in range(16, 48):
        pixels[15, offset] = (24, 228, 4, 255)
        pixels[48, offset] = (24, 228, 4, 255)
        pixels[offset, 15] = (24, 228, 4, 255)
        pixels[offset, 48] = (24, 228, 4, 255)
    pixels[32, 32] = (224, 24, 40, 128)
    image.save(path, format="PNG")


class ChromaKeyQualityTests(unittest.TestCase):
    def execute(self, root: Path):
        source = root / "source.png"
        output = root / "transparent.png"
        report = root / "report.json"
        synthetic_source(source)
        remove_chroma_key(
            source,
            output,
            report,
            source_format=PARAMETERS["source_format"],
            key_color=PARAMETERS["key_color"],
            auto_key=PARAMETERS["auto_key"],
            transparent_threshold=PARAMETERS["transparent_threshold"],
            opaque_threshold=PARAMETERS["opaque_threshold"],
            auto_key_maximum_deviation=PARAMETERS["auto_key_maximum_deviation"],
            auto_key_minimum_consensus=PARAMETERS["auto_key_minimum_consensus"],
            despill_strength=PARAMETERS["despill_strength"],
            edge_contract=PARAMETERS["edge_contract"],
            edge_feather=PARAMETERS["edge_feather"],
        )
        return source, output, report

    def test_builds_and_independently_validates_soft_matte(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, output, report = self.execute(Path(temporary))
            summary = parse_chroma_key_outputs(source, output, report, expected_parameters=PARAMETERS)
            with Image.open(output) as image:
                rgba = image.convert("RGBA")
                self.assertEqual(rgba.getpixel((0, 0)), (0, 0, 0, 0))
                self.assertEqual(rgba.getpixel((24, 24))[3], 255)
                self.assertTrue(0 < rgba.getpixel((15, 32))[3] < 255)
                self.assertEqual(rgba.getpixel((32, 32))[3], 128)

        self.assertEqual(summary["quality_status"], "passed")
        self.assertFalse(summary["quantitative_interpretation_allowed"])
        self.assertGreater(summary["alpha_counts"]["partial"], 0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            output = root / "filtered.png"
            report = root / "filtered.json"
            synthetic_source(source)
            filtered_parameters = {**PARAMETERS, "edge_contract": 1, "edge_feather": 0.5}
            remove_chroma_key(
                source,
                output,
                report,
                source_format="png",
                key_color="#00ff00",
                auto_key="corners",
                transparent_threshold=8,
                opaque_threshold=90,
                auto_key_maximum_deviation=18,
                auto_key_minimum_consensus=0.9,
                despill_strength=1,
                edge_contract=1,
                edge_feather=0.5,
            )
            filtered = parse_chroma_key_outputs(source, output, report, expected_parameters=filtered_parameters)

        self.assertGreater(filtered["alpha_counts"]["partial"], summary["alpha_counts"]["partial"])

    def test_rejects_tampered_raster_or_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output, report = self.execute(root)
            with Image.open(output) as image:
                changed = image.convert("RGBA")
            changed.putpixel((24, 24), (0, 0, 0, 0))
            changed.save(output, format="PNG")
            with self.assertRaisesRegex(ChromaKeyReportError, "digest"):
                parse_chroma_key_outputs(source, output, report, expected_parameters=PARAMETERS)

            source, output, report = self.execute(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["scientific_use"] = "quantitative-segmentation"
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ChromaKeyReportError, "scientific-use"):
                parse_chroma_key_outputs(source, output, report, expected_parameters=PARAMETERS)

    def test_rejects_format_spoof_and_heterogeneous_auto_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            output = root / "out.png"
            report = root / "report.json"
            synthetic_source(source)
            with self.assertRaisesRegex(ValueError, "declared source format"):
                remove_chroma_key(source, output, report, source_format="jpeg", key_color="#00ff00", auto_key="none", transparent_threshold=8, opaque_threshold=90, auto_key_maximum_deviation=18, auto_key_minimum_consensus=0.9, despill_strength=1, edge_contract=0, edge_feather=0)

            image = Image.new("RGB", (32, 32), (0, 255, 0))
            pixels = image.load()
            for x in range(16):
                for y in range(16):
                    pixels[x, y] = (0, 0, 255)
            image.save(source, format="PNG")
            with self.assertRaisesRegex(ValueError, "heterogeneous"):
                remove_chroma_key(source, output, report, source_format="png", key_color="#00ff00", auto_key="corners", transparent_threshold=8, opaque_threshold=90, auto_key_maximum_deviation=18, auto_key_minimum_consensus=0.9, despill_strength=1, edge_contract=0, edge_feather=0)


if __name__ == "__main__":
    unittest.main()
