from __future__ import annotations

import json
from urllib.parse import urlencode

import pytest

from tests.browser.al129_link_search_request import decode_search_link_request_args


EXPECTED = {
    "doctype": "Customer",
    "txt": "AL129 Customer",
    "reference_doctype": "Door Cutting Order",
    "page_length": 10,
    "link_fieldname": "customer",
    "filters": [["Customer", "disabled", "=", 0]],
}


@pytest.mark.parametrize(
    ("url", "post_data"),
    [
        ("https://desk.test/api/method/frappe.desk.search.search_link", json.dumps(EXPECTED)),
        (
            "https://desk.test/api/method/frappe.desk.search.search_link",
            urlencode({"args": json.dumps({**EXPECTED, "page_length": "10"})}),
        ),
        (
            "https://desk.test/api/method/frappe.desk.search.search_link",
            urlencode({
                "doctype": "Customer",
                "txt": EXPECTED["txt"],
                "reference_doctype": EXPECTED["reference_doctype"],
                "page_length": "10",
                "link_fieldname": "customer",
                "filters": json.dumps(EXPECTED["filters"]),
            }),
        ),
        (
            "https://desk.test/api/method/frappe.desk.search.search_link?"
            + urlencode({key: json.dumps(value) if key == "filters" else value for key, value in EXPECTED.items()}),
            None,
        ),
    ],
)
def test_decode_search_link_request_args(url: str, post_data: str | None) -> None:
    assert decode_search_link_request_args(url, post_data) == EXPECTED


def test_decode_nested_serialized_args_inside_json_body() -> None:
    body = json.dumps({"cmd": "frappe.desk.search.search_link", "args": json.dumps(EXPECTED)})

    assert decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link", body
    ) == EXPECTED


def test_decode_nested_form_args_inside_serialized_json_body() -> None:
    body = json.dumps({"args": urlencode({**EXPECTED, "filters": json.dumps(EXPECTED["filters"])})})

    assert decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link", body
    ) == EXPECTED


def test_search_text_is_not_mistaken_for_serialized_json() -> None:
    quoted_text = '"AL129 Customer"'
    body = urlencode({"doctype": "Customer", "txt": quoted_text})

    assert decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link", body
    )["txt"] == quoted_text
