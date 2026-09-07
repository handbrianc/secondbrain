"""Unit tests for the docling label -> element_type mapping in the chunker."""

from types import SimpleNamespace

import pytest

from secondbrain.document.chunker import (
    docling_item_label,
    label_to_element_type,
)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("title", "heading"),
        ("section_header", "heading"),
        ("document_index", "toc_entry"),
        ("page_header", "navigation"),
        ("page_footer", "navigation"),
        ("caption", "caption"),
        ("text", "body"),
        ("paragraph", "body"),
        ("list_item", "body"),
        ("footnote", "body"),
        ("reference", "body"),
        ("code", "body"),
        ("formula", "body"),
        ("chart", "body"),
        ("form", "body"),
        ("marker", "body"),
        ("key_value_region", "body"),
        ("checkbox_selected", "body"),
        ("checkbox_unselected", "body"),
        ("empty_value", "body"),
        ("field_region", "body"),
        ("field_heading", "body"),
        ("field_item", "body"),
        ("field_key", "body"),
        ("field_value", "body"),
        ("field_hint", "body"),
        ("handwritten_text", "body"),
        ("grading_scale", "body"),
        ("picture", "body"),
        ("table", "body"),
    ],
)
def test_label_to_element_type_known_labels(label: str, expected: str) -> None:
    """Every label in the mapping table resolves to its element type."""
    assert label_to_element_type(label) == expected


def test_label_to_element_type_unknown_returns_none() -> None:
    """Unknown labels fall through so callers use the statistical classifier."""
    assert label_to_element_type("brand_new_future_label") is None


def test_label_to_element_type_none_returns_none() -> None:
    assert label_to_element_type(None) is None


def test_docling_item_label_extracts_enum_value() -> None:
    """A docling item exposes its label as an enum-like object with .value."""
    item = SimpleNamespace(label=SimpleNamespace(value="section_header"))
    assert docling_item_label(item) == "section_header"


def test_docling_item_label_plain_string() -> None:
    item = SimpleNamespace(label="caption")
    assert docling_item_label(item) == "caption"


def test_docling_item_label_missing_returns_none() -> None:
    assert docling_item_label(SimpleNamespace(text="x")) is None


def test_docling_item_label_none_returns_none() -> None:
    item = SimpleNamespace(label=None)
    assert docling_item_label(item) is None


def test_docling_item_label_none_object_returns_none() -> None:
    assert docling_item_label(None) is None
