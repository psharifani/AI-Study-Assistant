"""Unit tests for document extraction (async paths use mocks; no real OpenAI calls)."""

from __future__ import annotations

from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from document_extract import (
    PDF_VISION_FALLBACK_MIN_CHARS,
    extract_text_from_file,
    extract_text_from_file_async,
)


class TestPdfVisionThresholdConstant(TestCase):
    def test_value_is_40(self) -> None:
        self.assertEqual(PDF_VISION_FALLBACK_MIN_CHARS, 40)


class TestExtractPlainText(TestCase):
    def test_reads_utf8_file(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_read.txt"
        try:
            p.write_text("alpha\nbeta\n", encoding="utf-8")
            out = extract_text_from_file(p, "x.txt")
            self.assertIn("alpha", out)
            self.assertIn("beta", out)
        finally:
            if p.is_file():
                p.unlink()


class TestExtractMarkdownExtension(TestCase):
    def test_treated_as_text(self) -> None:
        p = Path(__file__).resolve().parent / "_tmp_read.md"
        try:
            p.write_text("# Title\n", encoding="utf-8")
            out = extract_text_from_file(p, "x.md")
            self.assertIn("Title", out)
        finally:
            if p.is_file():
                p.unlink()


class TestSyncPdfBlankPage(TestCase):
    def test_returns_placeholder(self) -> None:
        import fitz

        p = Path(__file__).resolve().parent / "_blank.pdf"
        try:
            doc = fitz.open()
            doc.new_page()
            doc.save(p)
            doc.close()
            out = extract_text_from_file(p, "blank.pdf")
            self.assertEqual(out, "[No extractable text from PDF]")
        finally:
            if p.is_file():
                p.unlink()


def _pdf_with_long_text(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Study content line. " * 5)
    doc.save(path)
    doc.close()


class TestAsyncPdfSkipsVisionWhenEmbeddedTextLong(IsolatedAsyncioTestCase):
    async def test_vision_not_called(self) -> None:
        import fitz

        p = Path(__file__).resolve().parent / "_long.pdf"
        try:
            _pdf_with_long_text(p)
            vision = AsyncMock(return_value="SHOULD_NOT_APPEAR")
            with patch("llm_service.transcribe_pdf_pages_vision", vision):
                out = await extract_text_from_file_async(p, "long.pdf")
            vision.assert_not_awaited()
            self.assertNotIn("SHOULD_NOT_APPEAR", out)
            self.assertGreaterEqual(len(out), PDF_VISION_FALLBACK_MIN_CHARS)
        finally:
            if p.is_file():
                p.unlink()


class TestAsyncPdfCallsVisionWhenSparse(IsolatedAsyncioTestCase):
    async def test_vision_mock_used(self) -> None:
        import fitz

        p = Path(__file__).resolve().parent / "_sparse.pdf"
        try:
            doc = fitz.open()
            doc.new_page()
            doc.save(p)
            doc.close()
            vision = AsyncMock(return_value="--- Page 1 ---\nMock scan text.")
            with patch("llm_service.transcribe_pdf_pages_vision", vision):
                out = await extract_text_from_file_async(p, "sparse.pdf")
            vision.assert_awaited_once()
            self.assertIn("Mock scan text", out)
        finally:
            if p.is_file():
                p.unlink()


class TestAsyncImageDelegatesToTranscribe(IsolatedAsyncioTestCase):
    async def test_transcribe_image_file_mock(self) -> None:
        from PIL import Image

        p = Path(__file__).resolve().parent / "_tiny.png"
        try:
            Image.new("RGB", (16, 16), color=(0, 128, 0)).save(p)
            mock = AsyncMock(return_value="mock transcription")
            with patch("llm_service.transcribe_image_file", mock):
                out = await extract_text_from_file_async(p, "tiny.png")
            mock.assert_awaited_once()
            self.assertEqual(out, "mock transcription")
        finally:
            if p.is_file():
                p.unlink()
