from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.infrastructure.cutting import dxf_reader
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError


SHEET = dxf_import_service.SHEET_OUTLINE_LAYER
CUT = dxf_import_service.CUT_PATH_LAYER

_LWPOLYLINE_DXF = """0
SECTION
2
ENTITIES
0
LWPOLYLINE
8
SHEET_OUTLINE
70
1
10
0
20
0
10
1220
20
0
10
1220
20
2440
10
0
20
2440
0
LWPOLYLINE
8
CUT_PATH
70
1
10
10
20
10
10
210
20
10
10
210
20
110
10
10
20
110
0
LWPOLYLINE
8
along
70
1
10
0
20
0
10
1
20
0
10
1
20
1
10
0
20
1
0
ENDSEC
0
EOF
"""

_LINE_DXF = """0
SECTION
2
ENTITIES
0
LINE
8
SHEET_OUTLINE
10
0
20
0
11
100
21
0
0
LINE
8
CUT_PATH
10
10
20
10
11
20
21
10
0
ENDSEC
0
EOF
"""


def _write_text(content: str) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False, mode="w", encoding="utf-8")
    handle.write(content)
    handle.close()
    return handle.name


class TestDxfLwpolylineAsciiFallback(unittest.TestCase):
    def test_ascii_fallback_explodes_closed_lwpolyline_on_canonical_layers(self) -> None:
        rows = dxf_import_service._parse_r12_lines(_LWPOLYLINE_DXF)
        by_layer: dict[str, list] = {}
        for row in rows:
            by_layer.setdefault(row["layer"], []).append(row)

        self.assertEqual(len(by_layer[SHEET]), 4)
        self.assertEqual(len(by_layer[CUT]), 4)
        self.assertEqual(len(by_layer["along"]), 4)
        self.assertTrue(all(row["type"] == "LWPOLYLINE" for row in rows))
        sheet_points = {(row["x1"], row["y1"], row["x2"], row["y2"]) for row in by_layer[SHEET]}
        self.assertIn((0.0, 0.0, 1220.0, 0.0), sheet_points)
        self.assertIn((0.0, 2440.0, 0.0, 0.0), sheet_points)

    def test_ascii_fallback_keeps_r12_line_entities(self) -> None:
        rows = dxf_import_service._parse_r12_lines(_LINE_DXF)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["layer"] for row in rows}, {SHEET, CUT})
        self.assertTrue(all(row["type"] == "LINE" for row in rows))

    def test_lwpolyline_file_does_not_report_empty_layers_without_ezdxf(self) -> None:
        path = _write_text(_LWPOLYLINE_DXF)
        try:
            with patch.object(dxf_reader, "_import_ezdxf", side_effect=ImportError):
                with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
                    with self.assertRaises(DxfImportError) as exc_info:
                        dxf_import_service.parse_production_dxf(
                            "/private/files/autocad-lwpolyline.dxf",
                            SimpleNamespace(
                                trim_margin_mm=0,
                                board_width_cm=0,
                                board_length_cm=0,
                                full_board_width_mm=0,
                                full_board_length_mm=0,
                            ),
                        )
        finally:
            Path(path).unlink(missing_ok=True)

        message = str(exc_info.exception)
        self.assertNotIn("غير موجودة أو فارغة", message)
        self.assertNotIn("الطبقات المكتشفة: لا توجد.", message)
        self.assertIn("أبعاد اللوح", message)

    def test_reader_preserves_lwpolyline_entity_type_in_legacy_diagnostics(self) -> None:
        with patch.object(dxf_reader, "_import_ezdxf", side_effect=ImportError):
            result = dxf_reader.read_dxf_geometry(
                "unused.dxf",
                relevant_layers={SHEET, CUT},
                legacy_line_parser=lambda: dxf_import_service._parse_r12_lines(_LWPOLYLINE_DXF),
            )

        self.assertEqual(len([row for row in result["segments"] if row["layer"] == SHEET]), 4)
        self.assertEqual(len([row for row in result["segments"] if row["layer"] == CUT]), 4)
        self.assertNotIn("ALONG", result["diagnostics"]["relevant_layers"])
        self.assertIn("ALONG", result["diagnostics"]["detected_layers"])
        self.assertEqual(result["diagnostics"]["entity_counts"].get("LWPOLYLINE"), 12)
        self.assertTrue(all(row["entity_type"] == "LWPOLYLINE" for row in result["segments"]))

        self.assertEqual(len([row for row in result["segments"] if row["layer"] == SHEET]), 4)
        self.assertEqual(len([row for row in result["segments"] if row["layer"] == CUT]), 4)
        self.assertNotIn("ALONG", result["diagnostics"]["relevant_layers"])
        self.assertIn("ALONG", result["diagnostics"]["detected_layers"])
        self.assertEqual(result["diagnostics"]["entity_counts"].get("LWPOLYLINE"), 12)
        self.assertTrue(all(row["entity_type"] == "LWPOLYLINE" for row in result["segments"]))


if __name__ == "__main__":
    unittest.main()
