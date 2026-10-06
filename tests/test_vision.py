"""Vision fallback tests use an in-memory image-only PDF, not customer files."""

import io
import json
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from app.nodes.rule_extract import rule_extract
from app.services.extraction import run_pipeline
from app.state import FIELDS
from app.tools.ai_extract import ai_extract, build_chat_request
from app.tools.document_reader import read_document
from app.tools.pdf_images import render_pdf_pages


def scanned_pdf() -> bytes:
    image = Image.new("RGB", (900, 450), "white")
    ImageDraw.Draw(image).text((35, 35), "B/L NO: TEST123456", fill="black")
    output = io.BytesIO()
    image.save(output, format="PDF")
    image.close()
    return output.getvalue()


class VisionTests(unittest.TestCase):
    def test_pdf_renderer_keeps_images_in_memory(self):
        images, total = render_pdf_pages(scanned_pdf())
        self.assertEqual(total, 1)
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0].startswith(b"\xff\xd8"))

    def test_deepseek_flash_receives_scan_image_without_extracted_text(self):
        pdf = scanned_pdf()
        self.assertEqual(read_document("scan.pdf", pdf), "")
        document = {"name": "scan.pdf", "role": "入货通知", "data": pdf, "text": ""}
        payload, warnings = build_chat_request([document], "deepseek-flash", base_url="https://api.deepseek.com")
        content = payload["messages"][0]["content"]
        self.assertTrue(any(part["type"] == "image_url" for part in content))
        self.assertIn("data:image/jpeg;base64,", content[-1]["image_url"]["url"])
        self.assertTrue(any("图像费用" in warning for warning in warnings))
        response = {field: {name: "" for name in ("value", "evidence", "source", "source_label", "review_reason")} for field in FIELDS}
        response["bl_number"].update(value="TEST123456", source="scan.pdf", evidence="B/L NO: TEST123456")
        settings = {"base_url": "https://api.deepseek.com", "api_key": "test-key", "model": "deepseek-flash"}
        body = {"choices": [{"message": {"content": json.dumps(response)}}]}
        with patch("app.tools.ai_extract.get_settings", return_value=settings), patch("app.tools.ai_extract.call_service", return_value=body) as send:
            result = run_pipeline([document], "ai", reader=read_document, rule_engine=rule_extract, ai_engine=ai_extract)
        self.assertEqual(result["fields"]["bl_number"]["value"], "TEST123456")
        self.assertEqual(result["documents"][0]["text_quality"], "little_text")
        self.assertTrue(any("扫描件" in warning for warning in result["warnings"]))
        self.assertTrue(any(part["type"] == "image_url" for part in send.call_args.args[1]["messages"][0]["content"]))

    def test_other_chat_models_remain_text_only(self):
        document = {"name": "scan.pdf", "role": "入货通知", "data": scanned_pdf(), "text": ""}
        payload, warnings = build_chat_request([document], "deepseek-v4-pro", base_url="https://api.deepseek.com")
        self.assertIsInstance(payload["messages"][0]["content"], str)
        self.assertTrue(any("仅发送提取到的文字" in warning for warning in warnings))
        settings = {"base_url": "https://api.deepseek.com", "api_key": "test-key", "model": "deepseek-v4-pro"}
        with patch("app.tools.ai_extract.get_settings", return_value=settings):
            with self.assertRaisesRegex(ValueError, "没有可读取的文字"):
                ai_extract([document])

    def test_vision_has_page_limit_and_does_not_enable_unknown_hosts(self):
        pages = [Image.new("RGB", (300, 200), "white") for _ in range(4)]
        output = io.BytesIO()
        pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:])
        for page in pages:
            page.close()
        document = {"name": "four-pages.pdf", "role": "入货通知", "data": output.getvalue(), "text": ""}
        payload, warnings = build_chat_request([document], "deepseek-flash", base_url="https://api.deepseek.com")
        self.assertEqual(sum(part["type"] == "image_url" for part in payload["messages"][0]["content"]), 3)
        self.assertTrue(any("前 3 页" in warning for warning in warnings))
        other, _ = build_chat_request([document], "deepseek-flash", base_url="https://example.com/v1")
        self.assertIsInstance(other["messages"][0]["content"], str)


if __name__ == "__main__":
    unittest.main()
