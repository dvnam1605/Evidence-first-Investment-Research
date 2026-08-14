"""One-shot builder for DOC-14/G2 golden catalog + expects."""

from __future__ import annotations

import asyncio
import hashlib
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
from src.processing.pipeline import DocumentProcessor, DocumentProcessRequest

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests/fixtures/processing/golden"
ROOT = REPO / "tests/fixtures/processing"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_xlsx(path: Path, sheet: str, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row, start=1):
            ws.cell(r, c, val)
    buf = BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())


async def probe(path: Path, **kw: object):
    return await DocumentProcessor(ocr_engine=None).process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=path.read_bytes(),
            filename=path.name,
            **kw,  # type: ignore[arg-type]
        )
    )


async def build_expects() -> dict[str, dict]:
    mapping: list[tuple[str, Path, dict]] = [
        ("vietnamese_sample", ROOT / "vietnamese_sample.pdf", {}),
        ("exact_vi_grid", ROOT / "tables" / "exact_vi_grid.pdf", {}),
        ("multiline_vi_label", ROOT / "tables" / "multiline_vi_label.pdf", {}),
        ("narrative_adjacent", ROOT / "tables" / "narrative_adjacent.pdf", {}),
        ("large_8x4", ROOT / "tables" / "large_8x4.pdf", {}),
        ("page_spanning", ROOT / "tables" / "page_spanning.pdf", {}),
        ("false_positive_layout", ROOT / "tables" / "false_positive_layout.pdf", {}),
        ("two_tables_page", ROOT / "tables" / "two_tables_page.pdf", {}),
        (
            "fs_section_headings",
            GOLDEN / "digital" / "fs_section_headings.pdf",
            {"document_type": "financial_statement", "title": "BCTC"},
        ),
        (
            "board_resolution_vi",
            GOLDEN / "digital" / "board_resolution_vi.pdf",
            {"title": "Nghi quyet HDQT"},
        ),
        (
            "real_vi_bctc_sample",
            GOLDEN / "digital" / "real_vi_bctc_sample.pdf",
            {"document_type": "financial_statement", "title": "BCTC Real VI"},
        ),
        (
            "real_vi_ir_announcement",
            GOLDEN / "digital" / "real_vi_ir_announcement.pdf",
            {"title": "IR Announcement Real VI"},
        ),
        (
            "fs_balance_sheet",
            GOLDEN / "excel" / "fs_balance_sheet.xlsx",
            {"document_type": "financial_statement", "title": "BCTC"},
        ),
        (
            "fs_income_statement",
            GOLDEN / "excel" / "fs_income_statement.xlsx",
            {"document_type": "financial_statement", "title": "BCTC"},
        ),
    ]
    expects: dict[str, dict] = {}
    for id_, path, kw in mapping:
        result = await probe(path, **kw)
        exp: dict = {
            "file_type": result.file_type.value,
            "page_count": len(result.pages),
            "page_numbers": [page.page_number for page in result.pages],
            "needs_ocr": None
            if result.ocr_decision is None
            else result.ocr_decision.needs_ocr,
            "min_tables": len(result.reconstructed_tables),
            "min_text_blocks": sum(
                1 for block in result.blocks if block.block_type.value == "text"
            ),
            "sections_found": []
            if result.sections is None
            else [section.value for section in result.sections.sections_found],
        }
        if result.classification is not None:
            exp["document_class"] = result.classification.document_class.value
        if result.pages and result.file_type.value == "PDF":
            text = result.pages[0].text
            candidates = [
                "Doanh thu",
                "BANG CAN DOI",
                "LUU CHUYEN",
                "NGHI QUYET",
                "Chi tieu",
                "FORM",
                "FPT",
            ]
            exp["text_contains_any"] = [c for c in candidates if c in text][:3]
            exp["min_page1_chars"] = min(20, len(text.strip())) if text.strip() else 0
        if id_ in {
            "exact_vi_grid",
            "multiline_vi_label",
            "narrative_adjacent",
            "large_8x4",
            "page_spanning",
            "false_positive_layout",
            "two_tables_page",
        }:
            exp["expected_table_path"] = (
                f"tests/fixtures/processing/tables/{id_}.expected.json"
            )
        if id_ == "fs_balance_sheet":
            exp["section"] = "balance_sheet"
        if id_ == "fs_income_statement":
            exp["section"] = "income_statement"
        expects[id_] = exp
    return expects


async def main() -> None:
    _write_xlsx(
        GOLDEN / "excel" / "fs_income_statement.xlsx",
        "Income Statement",
        [
            ["Chi tieu", "Ma so", "Ky nay", "Ky truoc"],
            ["1. Doanh thu thuan", "10", "5000", "4500"],
            ["2. Gia von hang ban", "11", "3000", "2800"],
            ["3. Loi nhuan gop", "20", "2000", "1700"],
        ],
    )
    _write_xlsx(
        GOLDEN / "excel" / "fs_balance_sheet.xlsx",
        "Bang can doi ke toan",
        [
            ["Chi tieu", "Ma so", "So cuoi ky", "So dau ky"],
            ["A. TAI SAN NGAN HAN", "100", "1000", "900"],
            ["I. Tien va tuong duong tien", "110", "400", "350"],
            ["1. Tien", "111", "250", "200"],
        ],
    )

    expects = await build_expects()
    items: list[dict] = []

    digital_meta = [
        ("vietnamese_sample", ROOT / "vietnamese_sample.pdf", "Vietnamese digital text"),
        ("exact_vi_grid", ROOT / "tables" / "exact_vi_grid.pdf", "Exact VI table matrix"),
        (
            "multiline_vi_label",
            ROOT / "tables" / "multiline_vi_label.pdf",
            "Multiline VI label table",
        ),
        (
            "narrative_adjacent",
            ROOT / "tables" / "narrative_adjacent.pdf",
            "Table between narrative",
        ),
        ("large_8x4", ROOT / "tables" / "large_8x4.pdf", "Larger digital grid"),
        (
            "page_spanning",
            ROOT / "tables" / "page_spanning.pdf",
            "Page-local continuation tables",
        ),
        (
            "false_positive_layout",
            ROOT / "tables" / "false_positive_layout.pdf",
            "Ruled non-table layout",
        ),
        (
            "two_tables_page",
            ROOT / "tables" / "two_tables_page.pdf",
            "Two tables on one page",
        ),
        (
            "fs_section_headings",
            GOLDEN / "digital" / "fs_section_headings.pdf",
            "FS section heading detection",
        ),
        (
            "board_resolution_vi",
            GOLDEN / "digital" / "board_resolution_vi.pdf",
            "Non-FS digital disclosure text",
        ),
        (
            "real_vi_bctc_sample",
            GOLDEN / "digital" / "real_vi_bctc_sample.pdf",
            "Real Vietnamese native-text digital financial report",
        ),
        (
            "real_vi_ir_announcement",
            GOLDEN / "digital" / "real_vi_ir_announcement.pdf",
            "Real Vietnamese native-text IR disclosure announcement",
        ),
    ]
    for id_, path, role in digital_meta:
        items.append(
            {
                "id": id_,
                "kind": "digital_pdf",
                "storage": "committed",
                "path": path.relative_to(REPO).as_posix(),
                "role": role,
                "sha256": sha(path),
                "source": "synthetic",
                "expect": expects[id_],
            }
        )

    for id_, role in [
        ("image_only_page", "Image-only page (needs_ocr)"),
        ("low_text_high_image", "Low text + high image coverage"),
        ("sparse_scan_page", "Sparse text scan-like page"),
    ]:
        path = GOLDEN / "scanned" / f"{id_}.pdf"
        items.append(
            {
                "id": id_,
                "kind": "scanned_pdf",
                "storage": "committed",
                "path": path.relative_to(REPO).as_posix(),
                "role": role,
                "sha256": sha(path),
                "source": "synthetic",
                "expect": {"needs_ocr": True, "file_type": "PDF"},
            }
        )

    path = GOLDEN / "scanned" / "mixed_native_and_scan.pdf"
    items.append(
        {
            "id": "mixed_native_and_scan",
            "kind": "scanned_pdf",
            "storage": "committed",
            "path": path.relative_to(REPO).as_posix(),
            "role": "Mixed native+scan OCR golden",
            "sha256": sha(path),
            "source": "synthetic",
            "ocr_expected_path": (
                "tests/fixtures/processing/golden/scanned/"
                "mixed_native_and_scan.ocr.expected.json"
            ),
            "expect": {
                "needs_ocr": True,
                "file_type": "PDF",
                "has_native_and_ocr_pages": True,
            },
        }
    )

    for id_ in ["exact_vi_grid", "large_8x4", "two_tables_page"]:
        path = ROOT / "tables" / f"{id_}.pdf"
        items.append(
            {
                "id": f"complex_{id_}",
                "kind": "complex_table",
                "storage": "committed",
                "path": path.relative_to(REPO).as_posix(),
                "expected_path": (
                    (ROOT / "tables" / f"{id_}.expected.json").relative_to(REPO).as_posix()
                ),
                "role": f"Complex digital table: {id_}",
                "sha256": sha(path),
                "source": "synthetic",
            }
        )

    for path in sorted((ROOT / "tables" / "fpt_raw").glob("*.json")):
        name = path.stem
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = payload.get("source", {})
        items.append(
            {
                "id": f"fpt_raw_{name}",
                "kind": "complex_table",
                "storage": "committed",
                "path": path.relative_to(REPO).as_posix(),
                "role": source.get(
                    "document", "Vetted FPT raster transcription for reconstruction"
                ),
                "sha256": sha(path),
                "source": "vetted_transcription",
                "format": "raw_table_json",
                "source_pdf_sha256": source.get("sha256"),
            }
        )

    for id_ in ["fs_balance_sheet", "fs_income_statement"]:
        path = GOLDEN / "excel" / f"{id_}.xlsx"
        items.append(
            {
                "id": id_,
                "kind": "excel_report",
                "storage": "committed",
                "path": path.relative_to(REPO).as_posix(),
                "role": f"Excel {id_}",
                "sha256": sha(path),
                "source": "synthetic",
                "expect": expects[id_],
            }
        )

    manifest = json.loads(
        (ROOT / "tables" / "fpt_real" / "manifest.json").read_text(encoding="utf-8")
    )
    g2_report_ids: list[str] = []
    for row in manifest["items"]:
        pipeline_path = None
        for expected in (GOLDEN / "real_reports").glob("*.pipeline.expected.json"):
            payload = json.loads(expected.read_text(encoding="utf-8"))
            if payload.get("sha256") == row["sha256"]:
                pipeline_path = expected.relative_to(REPO).as_posix()
                break
        item = {
            "id": row["slug"],
            "kind": "real_report",
            "storage": "local_only",
            "path": row["local_path"],
            "role": row.get("publication_title") or row["filename"],
            "sha256": row["sha256"],
            "artifact_id": row["artifact_id"],
            "source": "issuer_ir_export",
            "note": "PDF gitignored; refresh via scripts.export_pdf_fixtures",
        }
        if pipeline_path:
            item["pipeline_expected_path"] = pipeline_path
            item["g2_review_sample"] = True
            g2_report_ids.append(row["slug"])
        items.append(item)

    extraction = json.loads(
        (
            GOLDEN
            / "real_reports"
            / "q2_2026_consol_bs_is_cf_pages.extraction.expected.json"
        ).read_text(encoding="utf-8")
    )
    items.append(
        {
            "id": "q2_2026_consol_bs_is_cf_pages",
            "kind": "real_raster_table_pages",
            "storage": "local_only",
            "path": (
                "tests/fixtures/processing/tables/fpt_real/"
                "20260727_FPT_Consolidated_Financial_Statements_for_Q22026_"
                "055fe1ecd3_024b14f8ceff.pdf"
            ),
            "role": "Q2 2026 consol BS/IS/CF native extraction expectation",
            "sha256": extraction["sha256"],
            "source": "issuer_ir_export",
            "extraction_expected_path": (
                GOLDEN
                / "real_reports"
                / "q2_2026_consol_bs_is_cf_pages.extraction.expected.json"
            ).relative_to(REPO).as_posix(),
            "g2_review_sample": True,
        }
    )

    catalog = {
        "doc": "DOC-14",
        "description": "Golden processing fixtures for document processing review (G2).",
        "policy": (
            "Synthetic binaries are committed with meaningful expect blocks. "
            "Real issuer PDFs are local-only (gitignored) with committed "
            "pipeline/extraction expected JSON keyed by sha256."
        ),
        "targets": {
            "digital_pdfs": 10,
            "scanned_pdfs": 3,
            "complex_tables": 3,
            "excel_reports": 2,
            "real_report_pipeline_goldens": 5,
        },
        "g2_real_report_sample": g2_report_ids,
        "counts": {
            "digital_pdfs_committed": sum(
                1
                for i in items
                if i["kind"] == "digital_pdf" and i["storage"] == "committed"
            ),
            "scanned_pdfs_committed": sum(
                1
                for i in items
                if i["kind"] == "scanned_pdf" and i["storage"] == "committed"
            ),
            "complex_tables_committed": sum(
                1
                for i in items
                if i["kind"] == "complex_table" and i["storage"] == "committed"
            ),
            "excel_reports_committed": sum(
                1
                for i in items
                if i["kind"] == "excel_report" and i["storage"] == "committed"
            ),
            "real_reports_with_pipeline_expected": len(g2_report_ids),
        },
        "items": items,
    }
    (GOLDEN / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("counts", catalog["counts"])
    print("g2_real_report_sample", len(g2_report_ids))
    for key, value in expects.items():
        print(
            key,
            "sections=",
            value.get("sections_found"),
            "tables=",
            value["min_tables"],
            "class=",
            value.get("document_class"),
        )


if __name__ == "__main__":
    asyncio.run(main())
