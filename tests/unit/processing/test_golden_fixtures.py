"""DOC-14 / G2 golden processing fixtures: inventory + meaningful expects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from src.domain.enums import DetectedFileType, ProcessingStatus
from src.processing.ocr.models import OCRTextLine
from src.processing.pipeline import DocumentProcessor, DocumentProcessRequest
from src.processing.tables import PyMuPDFTableExtractor
from src.processing.tables.raw_source import load_raw_table_fixture
from tests.unit.processing.test_ocr_fallback import FakeOCREngine

REPO = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO / "tests" / "fixtures" / "processing" / "golden" / "catalog.json"


def _catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_pipeline_expect(result, expect: dict, *, item_id: str) -> None:
    if "file_type" in expect:
        assert result.file_type.value == expect["file_type"], item_id
    if "page_count" in expect:
        assert len(result.pages) == expect["page_count"], item_id
    if "page_numbers" in expect:
        assert [page.page_number for page in result.pages] == expect["page_numbers"], item_id
    if "needs_ocr" in expect and expect["needs_ocr"] is not None:
        assert result.ocr_decision is not None, item_id
        assert result.ocr_decision.needs_ocr is expect["needs_ocr"], item_id
    if "min_tables" in expect:
        assert len(result.reconstructed_tables) >= expect["min_tables"], item_id
    if "min_text_blocks" in expect:
        text_blocks = sum(1 for block in result.blocks if block.block_type.value == "text")
        assert text_blocks >= expect["min_text_blocks"], item_id
    if "sections_found" in expect:
        got = (
            []
            if result.sections is None
            else [section.value for section in result.sections.sections_found]
        )
        assert got == expect["sections_found"], item_id
    if "section" in expect:
        assert expect["section"] in (
            []
            if result.sections is None
            else [section.value for section in result.sections.sections_found]
        ), item_id
    if "document_class" in expect:
        assert result.classification is not None, item_id
        assert result.classification.document_class.value == expect["document_class"], item_id
    if "text_contains_any" in expect and expect["text_contains_any"]:
        blob = "\n".join(page.text for page in result.pages)
        assert any(token in blob for token in expect["text_contains_any"]), item_id
    if "min_page1_chars" in expect and result.pages:
        assert len(result.pages[0].text.strip()) >= expect["min_page1_chars"], item_id


def test_golden_catalog_meets_doc14_and_g2_targets() -> None:
    catalog = _catalog()
    targets = catalog["targets"]
    items = catalog["items"]

    digital = [
        i for i in items if i["kind"] == "digital_pdf" and i["storage"] == "committed"
    ]
    scanned = [
        i for i in items if i["kind"] == "scanned_pdf" and i["storage"] == "committed"
    ]
    complex_tables = [
        i for i in items if i["kind"] == "complex_table" and i["storage"] == "committed"
    ]
    excel = [
        i for i in items if i["kind"] == "excel_report" and i["storage"] == "committed"
    ]
    real_pipeline = [
        i
        for i in items
        if i.get("kind") == "real_report" and i.get("pipeline_expected_path")
    ]

    assert len(digital) >= targets["digital_pdfs"]
    assert len(scanned) >= targets["scanned_pdfs"]
    assert len(complex_tables) >= targets["complex_tables"]
    assert len(excel) >= targets["excel_reports"]
    assert len(real_pipeline) >= targets["real_report_pipeline_goldens"]
    assert len(catalog.get("g2_real_report_sample", [])) >= 5


def test_committed_golden_binaries_match_catalog_sha256() -> None:
    catalog = _catalog()
    for item in catalog["items"]:
        if item["storage"] != "committed":
            continue
        path = REPO / item["path"]
        assert path.is_file(), f"missing committed fixture {item['id']}: {path}"
        assert _sha256(path) == item["sha256"], item["id"]


@pytest.mark.asyncio
async def test_committed_digital_and_excel_meaningful_expects() -> None:
    catalog = _catalog()
    processor = DocumentProcessor(ocr_engine=None)
    kinds = {"digital_pdf", "excel_report"}
    for item in catalog["items"]:
        if item["storage"] != "committed" or item["kind"] not in kinds:
            continue
        expect = item.get("expect")
        assert expect, f"{item['id']} missing expect"
        path = REPO / item["path"]
        result = await processor.process(
            DocumentProcessRequest(
                artifact_id=uuid4(),
                data=path.read_bytes(),
                filename=path.name,
                title=item.get("role"),
                document_type=(
                    "financial_statement"
                    if item["kind"] == "excel_report"
                    or item["id"] in {"fs_section_headings"}
                    else None
                ),
            )
        )
        assert result.status is not ProcessingStatus.FAILED, item["id"]
        _assert_pipeline_expect(result, expect, item_id=item["id"])


@pytest.mark.asyncio
async def test_committed_scanned_fixtures_flag_needs_ocr() -> None:
    catalog = _catalog()
    processor = DocumentProcessor(ocr_engine=None)
    for item in catalog["items"]:
        if item["storage"] != "committed" or item["kind"] != "scanned_pdf":
            continue
        if item["id"] == "mixed_native_and_scan":
            continue  # covered by OCR golden with engine
        path = REPO / item["path"]
        result = await processor.process(
            DocumentProcessRequest(
                artifact_id=uuid4(),
                data=path.read_bytes(),
                filename=path.name,
            )
        )
        assert result.file_type is DetectedFileType.PDF
        assert result.ocr_decision is not None
        assert result.ocr_decision.needs_ocr is True, item["id"]
        assert result.status is ProcessingStatus.NEEDS_REVIEW
        assert "ocr_required_but_engine_not_configured" in result.warnings


@pytest.mark.asyncio
async def test_ocr_output_golden_preserves_native_and_records_ocr() -> None:
    catalog = _catalog()
    item = next(i for i in catalog["items"] if i["id"] == "mixed_native_and_scan")
    expected = json.loads((REPO / item["ocr_expected_path"]).read_text(encoding="utf-8"))
    path = REPO / item["path"]
    assert _sha256(path) == expected["sha256"]

    fake_page = expected["fake_ocr"]["pages"]["2"]
    lines = tuple(
        OCRTextLine(
            text=line["text"],
            confidence=line["confidence"],
            bbox=tuple(line["bbox"]),
        )
        for line in fake_page["lines"]
    )
    engine = FakeOCREngine(
        texts={2: fake_page["text"]},
        confidence=fake_page["confidence"],
        lines_by_page={2: lines},
    )
    processor = DocumentProcessor(ocr_engine=engine)
    result = await processor.process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=path.read_bytes(),
            filename=path.name,
        )
    )

    assert result.ocr_decision is not None
    by_page = {d.page_number: d for d in result.ocr_decision.pages}
    assert by_page[1].needs_ocr is expected["page_1_needs_ocr"]
    assert by_page[2].needs_ocr is expected["page_2_needs_ocr"]

    page1 = next(page for page in result.pages if page.page_number == 1)
    for token in expected["native_page_1_contains"]:
        assert token in page1.text
    # Native page text must remain native extraction (not OCR overwrite).
    assert page1.extraction_method.value == "native"

    assert result.ocr is not None
    assert len(result.ocr.pages) == expected["expect_after_ocr"]["ocr_page_count"]
    ocr_blob = "\n".join(page.text for page in result.ocr.pages)
    for token in expected["expect_after_ocr"]["ocr_text_contains"]:
        assert token in ocr_blob
    ocr_page = result.ocr.pages[0]
    assert ocr_page.confidence is not None and ocr_page.confidence >= 0.9
    assert ocr_page.lines
    assert ocr_page.lines[0].bbox is not None
    assert engine.calls == [2]
    assert result.status is not ProcessingStatus.FAILED


def test_complex_table_expected_or_raw_json_loadable() -> None:
    catalog = _catalog()
    for item in catalog["items"]:
        if item["storage"] != "committed" or item["kind"] != "complex_table":
            continue
        path = REPO / item["path"]
        assert path.is_file(), item["id"]
        if item.get("format") == "raw_table_json":
            table, payload = load_raw_table_fixture(path)
            assert table.row_count >= 1
            if "expected" in payload:
                assert payload["expected"]
            else:
                source = payload.get("source", {})
                assert source.get("sha256") == table.source_sha256
                assert table.status.value == "NEEDS_REVIEW"
                assert "partial_statement_region" in table.warnings
                assert "cell_bboxes_estimated_from_verified_region" in table.warnings
            continue
        expected = item.get("expected_path")
        assert expected, item["id"]
        expected_path = REPO / expected
        assert expected_path.is_file(), item["id"]
        payload = json.loads(expected_path.read_text(encoding="utf-8"))
        assert "tables" in payload or "name" in payload


@pytest.mark.asyncio
async def test_real_report_pipeline_goldens_when_pdf_present() -> None:
    catalog = _catalog()
    real_items = [
        i
        for i in catalog["items"]
        if i.get("kind") == "real_report" and i.get("pipeline_expected_path")
    ]
    assert len(real_items) >= 5

    present = []
    for item in real_items:
        path = REPO / item["path"]
        if path.is_file():
            present.append(item)
    if len(present) < 5:
        pytest.skip(
            "Need >=5 local FPT PDFs for real-report pipeline goldens; "
            "run: uv run python -m scripts.export_pdf_fixtures"
        )

    processor = DocumentProcessor(ocr_engine=None)
    for item in present[:5]:
        expected = json.loads(
            (REPO / item["pipeline_expected_path"]).read_text(encoding="utf-8")
        )
        path = REPO / item["path"]
        assert _sha256(path) == expected["sha256"] == item["sha256"]
        result = await processor.process(
            DocumentProcessRequest(
                artifact_id=uuid4(),
                data=path.read_bytes(),
                filename=path.name,
                title=item.get("role"),
                document_type="financial_statement",
            )
        )
        assert result.file_type.value == expected["file_type"]
        assert result.status.value == expected["status"]
        assert len(result.pages) == expected["page_count"]
        assert [page.page_number for page in result.pages] == expected["page_numbers"]
        assert result.ocr_decision is not None
        assert result.ocr_decision.needs_ocr is expected["ocr_decision"]["needs_ocr"]
        assert result.ocr_decision.reason == expected["ocr_decision"]["reason"]
        needing = sum(1 for d in result.ocr_decision.pages if d.needs_ocr)
        assert needing == expected["ocr_decision"]["pages_needing_ocr"]
        if "pages" in expected["ocr_decision"]:
            by_page = {d.page_number: d for d in result.ocr_decision.pages}
            for page_exp in expected["ocr_decision"]["pages"]:
                p_num = page_exp["page"]
                assert p_num in by_page
                assert by_page[p_num].needs_ocr is page_exp["needs_ocr"]
                assert by_page[p_num].reason == page_exp["reason"]
        if "classification" in expected:
            assert result.classification is not None
            want_class = expected["classification"]["document_class"]
            assert result.classification.document_class.value == want_class
            assert result.classification.method == expected["classification"]["method"]
            assert result.classification.confidence >= expected["classification"]["min_confidence"]
        if "sections_found" in expected:
            got_sections = (
                []
                if result.sections is None
                else [s.value for s in result.sections.sections_found]
            )
            assert got_sections == expected["sections_found"]
        assert (
            0
            if result.table_extraction is None
            else len(result.table_extraction.tables)
        ) == expected["native_tables"]
        if "table_page_issues_sample" in expected:
            issues_by_page = {
                issue.page: issue
                for issue in (
                    () if result.table_extraction is None else result.table_extraction.page_issues
                )
            }
            for sample in expected["table_page_issues_sample"]:
                p_num = sample["page"]
                assert p_num in issues_by_page
                assert issues_by_page[p_num].status.value == sample["status"]
                assert issues_by_page[p_num].reason == sample["reason"]
        reasons = sorted(
            {
                issue.reason
                for issue in (
                    ()
                    if result.table_extraction is None
                    else result.table_extraction.page_issues
                )
            }
        )
        for reason in expected["table_page_issue_reasons"]:
            assert reason in reasons
        for warning in expected["warnings"]:
            assert warning in result.warnings
        if "text_span_checks" in expected:
            pages_by_num = {page.page_number: page for page in result.pages}
            for check in expected["text_span_checks"]:
                p_num = check["page"]
                assert p_num in pages_by_num
                p_text = pages_by_num[p_num].text
                assert len(p_text.strip()) >= check["min_chars"]
                assert any(token in p_text for token in check["contains_any"])


@pytest.mark.asyncio
async def test_committed_native_pdf_golden_assertions() -> None:
    catalog = _catalog()
    processor = DocumentProcessor(ocr_engine=None)

    # 1. Committed Vietnamese native digital financial report fixture.
    bctc_item = next(i for i in catalog["items"] if i["id"] == "real_vi_bctc_sample")
    bctc_path = REPO / bctc_item["path"]
    assert bctc_path.is_file()
    assert bctc_item["kind"] == "digital_pdf"
    assert bctc_item["source"] == "synthetic"

    res1 = await processor.process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=bctc_path.read_bytes(),
            filename=bctc_path.name,
            title="BCTC Real VI",
            document_type="financial_statement",
        )
    )
    assert res1.file_type is DetectedFileType.PDF
    assert res1.ocr_decision is not None
    assert res1.ocr_decision.needs_ocr is False
    assert len(res1.pages) == 2
    assert [p.page_number for p in res1.pages] == [1, 2]
    assert abs(res1.pages[0].width - 595.32) <= 1.0
    assert abs(res1.pages[0].height - 841.92) <= 1.0

    p1_text = res1.pages[0].text
    assert "CÔNG\xa0TY\xa0CỔ\xa0PHẦN" in p1_text
    assert "BẢNG\xa0CÂN\xa0ĐỐI\xa0KẾ\xa0TOÁN" in p1_text
    assert res1.sections is not None
    assert "balance_sheet" in [s.value for s in res1.sections.sections_found]

    p2_text = res1.pages[1].text
    assert "HOẠT\xa0ĐỘNG\xa0KINH\xa0DOANH" in p2_text
    assert "income_statement" in [s.value for s in res1.sections.sections_found]

    # 2. Committed Vietnamese native digital IR announcement fixture.
    ir_item = next(
        i for i in catalog["items"] if i["id"] == "real_vi_ir_announcement"
    )
    ir_path = REPO / ir_item["path"]
    assert ir_path.is_file()
    assert ir_item["kind"] == "digital_pdf"
    assert ir_item["source"] == "synthetic"

    res2 = await processor.process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=ir_path.read_bytes(),
            filename=ir_path.name,
            title="IR Announcement Real VI",
        )
    )
    assert res2.file_type is DetectedFileType.PDF
    assert res2.ocr_decision is not None
    assert res2.ocr_decision.needs_ocr is False
    assert len(res2.pages) == 1
    assert [p.page_number for p in res2.pages] == [1]
    assert abs(res2.pages[0].width - 595.32) <= 1.0

    ir_text = res2.pages[0].text
    assert "CỘNG\xa0HÒA\xa0XÃ\xa0HỘI\xa0CHỦ\xa0NGHĨA\xa0VIỆT\xa0NAM" in ir_text
    assert "CÔNG\xa0TY\xa0CỔ\xa0PHẦN\xa0FPT" in ir_text
    assert "THÔNG\xa0BÁO\xa0NGHỊ\xa0QUYẾT\xa0HỘI\xa0ĐỒNG\xa0QUẢN\xa0TRỊ" in ir_text


def test_real_raster_bs_is_cf_page_extraction_expectation() -> None:
    catalog = _catalog()
    item = next(i for i in catalog["items"] if i["id"] == "q2_2026_consol_bs_is_cf_pages")
    expected = json.loads(
        (REPO / item["extraction_expected_path"]).read_text(encoding="utf-8")
    )
    path = REPO / item["path"]
    if not path.is_file():
        pytest.skip("Q2 consol PDF missing; export via scripts.export_pdf_fixtures")

    assert _sha256(path) == expected["sha256"] == item["sha256"]
    result = PyMuPDFTableExtractor().extract(path.read_bytes())
    for page_str, want in expected["pages"].items():
        page = int(page_str)
        tables = [table for table in result.tables if table.page == page]
        issues = [issue for issue in result.page_issues if issue.page == page]
        assert len(tables) == want["native_table_count"]
        reasons = {issue.reason for issue in issues}
        for reason in want["expect_reason_in"]:
            assert reason in reasons
        assert any(issue.status.value == want["extraction_status"] for issue in issues)
        raw_path = REPO / want["raw_table_fixture"]
        assert raw_path.is_file()
        table, payload = load_raw_table_fixture(raw_path)
        assert table.page == page
        assert table.source_sha256 == expected["sha256"] == item["sha256"]
        assert payload["source"]["sha256"] == expected["sha256"] == item["sha256"]
        assert payload["expected"]["table_type"] == want["statement"]

