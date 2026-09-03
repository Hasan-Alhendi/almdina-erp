from __future__ import annotations

import base64
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.services import dxf_export_service


ORIGINAL_DXF = b"0\nSECTION\n8\nalong\n8\nCUT_PATH\n0\nEOF\n"


class _FakeThrow(Exception):
    def __init__(self, message: str, *args: object) -> None:
        super().__init__(str(message))


def _throw(message: str, *args: object, **kwargs: object) -> None:
    raise _FakeThrow(message)


def _file_row(*, plan_name: str = "PLAN-1", is_private: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        name="FILE-1",
        file_name="cutting_plan_DCO-2026-00018_corrected.dxf",
        file_url="/private/files/corrected.dxf",
        is_private=is_private,
        attached_to_doctype="Cutting Plan",
        attached_to_name=plan_name,
        attached_to_field="dxf_file",
    )


class TestDxfOriginalUploadDownload(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        handle.write(ORIGINAL_DXF)
        handle.close()
        self.path = handle.name
        self.order = SimpleNamespace(name="DCO-2026-00018")
        self.plan = SimpleNamespace(
            name="PLAN-1",
            door_cutting_order="DCO-2026-00018",
            dxf_file="/private/files/corrected.dxf",
        )
        self.response: dict[str, object] = {}

    def tearDown(self) -> None:
        Path(self.path).unlink(missing_ok=True)

    def _run(
        self,
        *,
        plan_source: str,
        plan: object | None = None,
        file_row: SimpleNamespace | None = None,
    ) -> dict[str, str]:
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(dxf_export_service, "_require_export_access", return_value=self.order)
            )
            stack.enter_context(
                patch.object(
                    dxf_export_service,
                    "_saved_plan_for_source",
                    return_value=self.plan if plan is None else plan,
                )
            )
            stack.enter_context(
                patch.object(
                    dxf_export_service,
                    "_dxf_file_row",
                    return_value=_file_row() if file_row is None else file_row,
                )
            )
            stack.enter_context(
                patch.object(dxf_export_service, "_existing_dxf_disk_path", return_value=self.path)
            )
            stack.enter_context(
                patch.object(dxf_export_service, "_attach_download_response", side_effect=self._capture)
            )
            stack.enter_context(patch.object(dxf_export_service, "_", side_effect=lambda msg: msg))
            stack.enter_context(patch.object(dxf_export_service.frappe, "throw", side_effect=_throw))
            return dxf_export_service.download_uploaded_dxf("DCO-2026-00018", plan_source)

    def _capture(self, filename: str, content: bytes) -> None:
        self.response["filename"] = filename
        self.response["filecontent"] = content

    def test_uploaded_plan_returns_original_bytes(self) -> None:
        result = self._run(plan_source="custom")

        self.assertEqual(base64.b64decode(result["content_b64"]), ORIGINAL_DXF)
        self.assertEqual(result["filename"], "cutting_plan_DCO-2026-00018_corrected.dxf")
        self.assertEqual(self.response["filecontent"], ORIGINAL_DXF)
        self.assertEqual(self.response["filename"], result["filename"])

    def test_system_plan_does_not_enter_original_download(self) -> None:
        with self.assertRaises(_FakeThrow) as exc_info:
            self._run(plan_source="system")

        self.assertIn("لا يوجد ملف DXF مرفوع لهذه الخطة", str(exc_info.exception))

    def test_missing_dxf_file_fails_closed(self) -> None:
        missing = SimpleNamespace(
            name="PLAN-1",
            door_cutting_order="DCO-2026-00018",
            dxf_file="",
        )
        with self.assertRaises(_FakeThrow) as exc_info:
            self._run(plan_source="custom", plan=missing)

        self.assertIn("لا يوجد ملف DXF مرفوع لهذه الخطة", str(exc_info.exception))

    def test_foreign_plan_attachment_is_rejected(self) -> None:
        with self.assertRaises(_FakeThrow) as exc_info:
            self._run(plan_source="custom", file_row=_file_row(plan_name="PLAN-OTHER"))

        self.assertIn("غير مرتبط بهذه الخطة", str(exc_info.exception))

    def test_client_cannot_supply_file_url(self) -> None:
        source = Path(dxf_export_service.__file__).read_text(encoding="utf-8")
        download = source.split("def download_uploaded_dxf", 1)[1].split(
            "def get_validated_dxf_plan", 1
        )[0]
        self.assertNotIn("file_url", download)
        self.assertIn("order_name", download)
        self.assertIn("plan_source", download)


if __name__ == "__main__":
    unittest.main()
