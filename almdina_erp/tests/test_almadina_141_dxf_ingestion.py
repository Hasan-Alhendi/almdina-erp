from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import ezdxf

from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    DxfReadError,
    read_dxf_geometry,
)


SHEET = "SHEET_OUTLINE"
CUT = "CUT_PATH"


def _write(doc) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    doc.saveas(handle.name)
    return handle.name


def _point_close(point, expected, places=5):
    return all(round(a - b, places) == 0 for a, b in zip(point, expected))


class TestAlmadina141DxfReader(unittest.TestCase):
    def tearDown(self) -> None:
        for path in getattr(self, "paths", []):
            Path(path).unlink(missing_ok=True)

    def _read(self, doc):
        path = _write(doc)
        self.paths = getattr(self, "paths", []) + [path]
        return read_dxf_geometry(path, relevant_layers={SHEET, CUT})

    def test_direct_modelspace_line_behavior_is_preserved(self) -> None:
        doc = ezdxf.new("R2010")
        doc.modelspace().add_line((1, 2), (11, 12), dxfattribs={"layer": CUT})

        result = self._read(doc)

        self.assertEqual(result["unsupported"], [])
        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["segments"][0]["layer"], CUT)
        self.assertEqual(result["segments"][0]["start"], (1.0, 2.0))
        self.assertEqual(result["segments"][0]["end"], (11.0, 12.0))

    def test_layer_matching_normalizes_case_and_surrounding_whitespace_only(self) -> None:
        doc = ezdxf.new("R2010")
        doc.layers.add(" cut_path ")
        doc.layers.add("CUT-PATH")
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": " cut_path "})
        msp.add_line((0, 5), (10, 5), dxfattribs={"layer": "CUT-PATH"})

        result = self._read(doc)

        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["segments"][0]["layer"], CUT)
        self.assertNotIn("CUT-PATH", result["diagnostics"]["relevant_layers"])

    def test_insert_layer_zero_inherits_effective_insert_layer_and_translation(self) -> None:
        doc = ezdxf.new("R2010")
        block = doc.blocks.new("PART")
        block.add_line((0, 0), (20, 0), dxfattribs={"layer": "0"})
        doc.modelspace().add_blockref("PART", (100, 50), dxfattribs={"layer": CUT})

        result = self._read(doc)

        self.assertEqual(len(result["segments"]), 1)
        segment = result["segments"][0]
        self.assertEqual(segment["layer"], CUT)
        self.assertTrue(_point_close(segment["start"], (100.0, 50.0)))
        self.assertTrue(_point_close(segment["end"], (120.0, 50.0)))
        self.assertTrue(result["diagnostics"]["has_inserts"])
        self.assertIn("PART", result["diagnostics"]["block_names"])

    def test_explicit_child_layer_does_not_inherit_insert_layer(self) -> None:
        doc = ezdxf.new("R2010")
        block = doc.blocks.new("MIXED")
        block.add_line((0, 0), (20, 0), dxfattribs={"layer": SHEET})
        doc.modelspace().add_blockref("MIXED", (0, 0), dxfattribs={"layer": CUT})

        result = self._read(doc)

        self.assertEqual(result["segments"][0]["layer"], SHEET)

    def test_insert_rotation_and_non_uniform_scale_are_applied(self) -> None:
        doc = ezdxf.new("R2010")
        block = doc.blocks.new("SCALED")
        block.add_line((0, 0), (10, 0), dxfattribs={"layer": "0"})
        doc.modelspace().add_blockref(
            "SCALED",
            (30, 40),
            dxfattribs={"layer": CUT, "rotation": 90, "xscale": 2, "yscale": 3},
        )

        result = self._read(doc)

        segment = result["segments"][0]
        points = (segment["start"], segment["end"])
        self.assertTrue(any(_point_close(point, (30.0, 40.0)) for point in points))
        self.assertTrue(any(_point_close(point, (30.0, 60.0)) for point in points))

    def test_nested_insert_composes_transforms_and_layer_inheritance(self) -> None:
        doc = ezdxf.new("R2010")
        inner = doc.blocks.new("INNER")
        inner.add_line((0, 0), (5, 0), dxfattribs={"layer": "0"})
        outer = doc.blocks.new("OUTER")
        outer.add_blockref("INNER", (10, 0), dxfattribs={"layer": "0", "rotation": 90})
        doc.modelspace().add_blockref("OUTER", (100, 100), dxfattribs={"layer": CUT})

        result = self._read(doc)

        self.assertEqual(len(result["segments"]), 1)
        segment = result["segments"][0]
        self.assertEqual(segment["layer"], CUT)
        points = (segment["start"], segment["end"])
        self.assertTrue(any(_point_close(point, (110.0, 100.0)) for point in points))
        self.assertTrue(any(_point_close(point, (110.0, 105.0)) for point in points))

    def test_unsupported_entity_inside_relevant_block_is_reported_with_diagnostics(self) -> None:
        doc = ezdxf.new("R2010")
        block = doc.blocks.new("BAD")
        block.add_text("x", dxfattribs={"layer": "0", "insert": (0, 0)})
        doc.modelspace().add_blockref("BAD", (0, 0), dxfattribs={"layer": CUT})

        result = self._read(doc)

        self.assertEqual(result["unsupported"], [{"layer": CUT, "entity_type": "TEXT"}])
        self.assertEqual(result["diagnostics"]["entity_counts"]["TEXT"], 1)

    def test_minsert_is_fail_closed_instead_of_silently_collapsing_instances(self) -> None:
        doc = ezdxf.new("R2010")
        block = doc.blocks.new("ARRAY_PART")
        block.add_line((0, 0), (10, 0), dxfattribs={"layer": "0"})
        insert = doc.modelspace().add_blockref("ARRAY_PART", (0, 0), dxfattribs={"layer": CUT})
        insert.dxf.row_count = 2
        insert.dxf.row_spacing = 20

        with self.assertRaises(DxfReadError):
            self._read(doc)

    def test_diagnostics_include_detected_layers_and_insert_presence(self) -> None:
        doc = ezdxf.new("R2010")
        doc.layers.add("OTHER")
        msp = doc.modelspace()
        msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "OTHER"})
        msp.add_line((0, 1), (1, 1), dxfattribs={"layer": CUT})

        result = self._read(doc)

        diagnostics = result["diagnostics"]
        self.assertIn("OTHER", diagnostics["detected_layers"])
        self.assertIn(CUT, diagnostics["detected_layers"])
        self.assertIn(CUT, diagnostics["relevant_layers"])
        self.assertEqual(diagnostics["entity_counts"]["LINE"], 2)


if __name__ == "__main__":
    unittest.main()
