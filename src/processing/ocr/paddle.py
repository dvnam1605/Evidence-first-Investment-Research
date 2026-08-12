"""PaddleOCR engine adapter (optional heavy dependency)."""

from __future__ import annotations

import asyncio
import os
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

# Ensure PaddlePaddle 3.x uses static graph engine and bypasses hoster check on Windows
os.environ["FLAGS_ENABLE_PIR_API"] = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

from src.processing.errors import OCRFailure
from src.processing.ocr.models import OCRPageResult, OCRTextLine, PageImage

ENGINE_NAME = "paddleocr"


def _paddleocr_version() -> str:
    try:
        return version("paddleocr")
    except PackageNotFoundError:
        return "unknown"


def _import_paddle_ocr() -> Any:
    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRFailure(
            "paddleocr is not installed; install optional extra: "
            "uv sync --extra ocr"
        ) from exc
    return PaddleOCR


def _bbox_from_poly(poly: object) -> tuple[float, float, float, float] | None:
    if not isinstance(poly, (list, tuple)):
        return None
    points: list[tuple[float, float]] = []
    for point in poly:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            return None
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _mean_confidence(lines: tuple[OCRTextLine, ...]) -> float | None:
    scores = [line.confidence for line in lines if line.confidence is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _lines_from_classic_page(page: object) -> list[OCRTextLine]:
    """Normalize PaddleOCR 2.x-style page: list of [box, (text, conf)]."""
    if page is None:
        return []
    if not isinstance(page, list):
        return []
    lines: list[OCRTextLine] = []
    for item in page:
        try:
            box, payload = item[0], item[1]
            text, conf = payload[0], payload[1]
        except (TypeError, ValueError, IndexError):
            continue
        lines.append(
            OCRTextLine(
                text=str(text),
                confidence=float(conf) if conf is not None else None,
                bbox=_bbox_from_poly(box),
            )
        )
    return lines


def _as_mapping(result_item: object) -> dict[str, Any] | None:
    if isinstance(result_item, dict):
        return result_item
    json_attr = getattr(result_item, "json", None)
    if isinstance(json_attr, dict):
        return json_attr
    if callable(json_attr):
        payload = json_attr()
        if isinstance(payload, dict):
            return payload
    return None


def _lines_from_predict_item(item: object) -> list[OCRTextLine]:
    """Normalize PaddleOCR 3.x predict() item (rec_texts / rec_scores / dt_polys)."""
    data = _as_mapping(item) or {}
    # Some builds nest under "res".
    nested = data.get("res")
    if isinstance(nested, dict):
        data = nested

    texts = data.get("rec_texts") or data.get("rec_text") or getattr(item, "rec_texts", None)
    scores = data.get("rec_scores") or data.get("rec_score") or getattr(item, "rec_scores", None)
    polys = data.get("dt_polys") or data.get("rec_polys") or getattr(item, "dt_polys", None)

    if texts is None:
        return []
    text_list = list(texts)
    score_list = list(scores) if scores is not None else [None] * len(text_list)
    poly_list = list(polys) if polys is not None else [None] * len(text_list)

    lines: list[OCRTextLine] = []
    for idx, text in enumerate(text_list):
        conf = score_list[idx] if idx < len(score_list) else None
        poly = poly_list[idx] if idx < len(poly_list) else None
        lines.append(
            OCRTextLine(
                text=str(text),
                confidence=float(conf) if conf is not None else None,
                bbox=_bbox_from_poly(poly) if poly is not None else None,
            )
        )
    return lines


def normalize_paddle_output(result: object) -> tuple[OCRTextLine, ...]:
    """Convert paddleocr.ocr / .predict output into OCRTextLine tuples."""
    if result is None:
        return ()
    if not isinstance(result, list) or not result:
        # Single predict object.
        return tuple(_lines_from_predict_item(result))

    first = result[0]
    # Classic ocr(): [[lines...]] for one image → first element is the page line list.
    if isinstance(first, list):
        return tuple(_lines_from_classic_page(first))
    return tuple(_lines_from_predict_item(first))


def _raw_from_lines(lines: tuple[OCRTextLine, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "text": line.text,
            "confidence": line.confidence,
            "bbox": list(line.bbox) if line.bbox is not None else None,
        }
        for line in lines
    )


class PaddleOCREngine:
    """Thin async wrapper around PaddleOCR (loaded lazily on first recognize)."""

    def __init__(
        self,
        *,
        lang: str = "en",
        engine_version: str | None = None,
    ) -> None:
        self._lang = lang
        self._engine_version = engine_version or _paddleocr_version()
        self._ocr: Any | None = None

    @property
    def engine_name(self) -> str:
        return ENGINE_NAME

    @property
    def engine_version(self) -> str:
        return self._engine_version

    def _ensure_engine(self) -> Any:
        if self._ocr is not None:
            return self._ocr
        import os

        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["FLAGS_ENABLE_PIR_API"] = "0"
        paddle_cls = _import_paddle_ocr()
        try:
            self._ocr = paddle_cls(
                lang=self._lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            # Older paddleocr builds use different constructor kwargs.
            self._ocr = paddle_cls(lang=self._lang, use_angle_cls=True, show_log=False)
        except Exception as exc:  # noqa: BLE001 - paddle init errors vary
            raise OCRFailure(f"Failed to initialize PaddleOCR: {exc}") from exc
        return self._ocr

    def _run_paddle(self, image_path: str) -> object:
        ocr = self._ensure_engine()
        if hasattr(ocr, "predict"):
            return ocr.predict(image_path)
        if hasattr(ocr, "ocr"):
            return ocr.ocr(image_path)
        raise OCRFailure("Installed paddleocr exposes neither predict() nor ocr()")

    def _recognize_sync(self, image: PageImage) -> OCRPageResult:
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                handle.write(image.png_bytes)
                tmp_path = handle.name
            try:
                raw_result = self._run_paddle(tmp_path)
            except OCRFailure:
                raise
            except Exception as exc:  # noqa: BLE001 - paddle runtime errors vary
                raise OCRFailure(
                    f"PaddleOCR failed on page {image.page_number}: {exc}"
                ) from exc
            lines = normalize_paddle_output(raw_result)
            text = "\n".join(line.text for line in lines if line.text).strip()
            return OCRPageResult(
                page_number=image.page_number,
                engine=ENGINE_NAME,
                engine_version=self._engine_version,
                text=text,
                confidence=_mean_confidence(lines),
                lines=lines,
                raw=_raw_from_lines(lines),
                decision_reason="",
            )
        finally:
            if tmp_path is not None:
                Path(tmp_path).unlink(missing_ok=True)

    async def recognize(self, image: PageImage) -> OCRPageResult:
        return await asyncio.to_thread(self._recognize_sync, image)
