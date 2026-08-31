from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError


SHEET = dxf_import_service.SHEET_OUTLINE_LAYER
CUT = dxf_import_service.CUT_PATH_LAYER


def _write_dxf(doc) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    doc.saveas(handle.name)
    return handle.name


def _add_rectangle(msp, *, layer: str) -> None:
    points = ((0, 0), (100, 0), (100, 200), (0, 200))
    for start, end in zip(points, (*points[1:], points[0])):
        msp.add_line(start, end, dxfattribs={"layer": layer})


class TestAlmadina142CuttingDxfContract(unittest.TestCase):
    def test_missing_canonical_layer_reports_normalized_detected_layers(self) -> None:
        """ALMADINA-142: missing-role errors keep ALMADINA-141 reader diagnostics."""

        for present_layer, missing_layer in ((SHEET, CUT), (CUT, SHEET)):
            with self.subTest(missing_layer=missing_layer):
                doc = ezdxf.new("R2010")
                doc.layers.add(" door_cut ")
                msp = doc.modelspace()
                _add_rectangle(msp, layer=present_layer)
                msp.add_line((0, 250), (10, 250), dxfattribs={"layer": " door_cut "})
                path = _write_dxf(doc)

                try:
                    with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
                        with self.assertRaises(DxfImportError) as exc_info:
                            dxf_import_service.parse_production_dxf(
                                "/private/files/almadina-142-missing-layer.dxf",
                                SimpleNamespace(),
                            )
                finally:
                    Path(path).unlink(missing_ok=True)

                message = str(exc_info.exception)
                self.assertIn(missing_layer, message)
                self.assertIn("الطبقات المكتشفة", message)
                self.assertIn(present_layer, message)
                self.assertIn("DOOR_CUT", message)


if __name__ == "__main__":
    unittest.main()
