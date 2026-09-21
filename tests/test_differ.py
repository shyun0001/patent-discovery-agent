import pytest

from core.differ import DiffEngine
from exceptions import DiffError


def test_compute_diff_detects_changed_sections(sample_docs):
    old, new = sample_docs
    diff = DiffEngine().compute_diff(old, new)

    assert 0.0 < diff.change_ratio < 1.0
    headings = [s.heading for s in diff.changed_sections]
    assert any("학습 알고리즘" in h for h in headings)
    assert any("데이터 처리" in h for h in headings)
    assert diff.summary.added_lines > 0


def test_unchanged_sections_are_excluded(sample_docs):
    old, new = sample_docs
    diff = DiffEngine().compute_diff(old, new)
    # "1. 개요"는 두 문서에서 동일하므로 변경 목록에 없어야 한다.
    assert not any("개요" in s.heading for s in diff.changed_sections)


def test_identical_documents_raise_e2002(sample_docs):
    old, _ = sample_docs
    with pytest.raises(DiffError) as exc:
        DiffEngine().compute_diff(old, old)
    assert exc.value.error_code == "E2002"


def test_change_ratio_range(sample_docs):
    old, new = sample_docs
    ratio = DiffEngine().calculate_change_ratio(old.content, new.content)
    assert 0.0 <= ratio <= 1.0
    assert DiffEngine().calculate_change_ratio("abc", "abc") == 0.0


def test_format_diff_html_colors_lines():
    html = DiffEngine().format_diff_html("+added\n-removed")
    assert "#dcfce7" in html and "#fee2e2" in html
