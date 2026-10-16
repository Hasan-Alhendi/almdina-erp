from __future__ import annotations

import json
from urllib.parse import urlencode

import pytest

from tests.browser.al129_link_search_request import (
    decode_search_link_request_args,
    normalize_search_link_args,
    search_link_argument_differences,
)


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


def test_jquery_empty_wire_values_match_omitted_undefined_link_args() -> None:
    expected = normalize_search_link_args({
        "doctype": "Customer",
        "txt": "AL129 Customer",
        "reference_doctype": "Door Cutting Order",
        "page_length": 10,
        "link_fieldname": "customer",
        # Playwright's page.evaluate serializes JavaScript undefined as None.
        "ignore_user_permissions": None,
        "filters": None,
    })
    actual = decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link",
        urlencode({
            **expected,
            "page_length": "10",
            "ignore_user_permissions": "",
            "filters": "",
        }),
    )

    assert actual == expected


def test_frappe_undefined_optionals_match_across_evaluate_and_form_transport() -> None:
    javascript_result = normalize_search_link_args({
        **EXPECTED,
        "ignore_user_permissions": None,
        "filters": None,
    })
    form_request = decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link",
        urlencode({
            **EXPECTED,
            "ignore_user_permissions": "",
            "filters": "",
            "page_length": "10",
        }),
    )

    assert search_link_argument_differences(javascript_result, form_request) == {}


def test_native_search_args_match_frappe_form_encoded_request_exactly() -> None:
    native_args = normalize_search_link_args({
        **EXPECTED,
        "ignore_user_permissions": None,
    })
    wire_args = decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link",
        urlencode({
            **EXPECTED,
            "ignore_user_permissions": "",
            "page_length": "10",
            "filters": json.dumps(EXPECTED["filters"]),
        }),
    )

    assert search_link_argument_differences(native_args, wire_args) == {}
    assert wire_args["filters"] == EXPECTED["filters"]
    assert wire_args["page_length"] == EXPECTED["page_length"]


def test_explicit_permission_flag_and_serialized_filters_are_preserved() -> None:
    expected = {
        **EXPECTED,
        "ignore_user_permissions": False,
    }
    actual = decode_search_link_request_args(
        "https://desk.test/api/method/frappe.desk.search.search_link",
        urlencode({
            **EXPECTED,
            "ignore_user_permissions": "false",
            "filters": json.dumps(EXPECTED["filters"]),
            "page_length": "10",
        }),
    )

    assert actual == expected
    assert actual["filters"] == EXPECTED["filters"]
    assert actual["ignore_user_permissions"] is False


def test_argument_difference_keeps_boolean_and_number_distinct() -> None:
    assert search_link_argument_differences({"ignore_user_permissions": False}, {"ignore_user_permissions": 0}) == {
        "ignore_user_permissions": {"expected": False, "actual": 0}
    }


def test_optional_normalization_does_not_drop_other_empty_arguments() -> None:
    assert normalize_search_link_args({
        "doctype": "",
        "ignore_user_permissions": "",
        "filters": "",
    }) == {"doctype": ""}


def test_normalized_filters_match_structurally_without_reordering() -> None:
    expected = normalize_search_link_args({
        **EXPECTED,
        "ignore_user_permissions": None,
    })
    actual = normalize_search_link_args({
        **EXPECTED,
        "filters": json.dumps(EXPECTED["filters"]),
        "page_length": "10",
    })

    assert search_link_argument_differences(expected, actual) == {}
