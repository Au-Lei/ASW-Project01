"""Run a small real-provider smoke test against the already configured local app.

Only synthetic shipment data is sent. API credentials remain in the app process.
Run after the AI settings page reports a successful connection test.
"""

import base64
import io
import json
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont


BASE = "http://127.0.0.1:8765"


def _request(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(req, timeout=150) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {error.code}: {body[:300]}") from error


def _text_pdf() -> bytes:
    lines = ["B/L NO: TESTAI2601001", "VESSEL/VOYAGE: DEMO STAR / 101E",
             "ETD: 2026-10-12", "CONTAINER: 1X40HC", "POD: KOBE", "POL: QINGDAO"]
    stream = "BT /F1 18 Tf 50 740 Td " + " ".join(
        f"({line}) Tj 0 -32 Td" for line in lines
    ) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode('ascii'))} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n{value}\nendobj\n".encode("ascii"))
    xref = output.tell()
    output.write(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii"))
    return output.getvalue()


def _scan_pdf(page_count: int) -> bytes:
    pages = []
    try:
        for index in range(page_count):
            image = Image.new("RGB", (1200, 700), "white")
            draw = ImageDraw.Draw(image)
            try:
                font = ImageFont.truetype("arial.ttf", 44)
            except OSError:
                font = ImageFont.load_default()
            if index == 0:
                draw.text((60, 70), "B/L NO: TESTSCAN2601002", fill="black", font=font)
                draw.text((60, 160), "VESSEL: DEMO VISION", fill="black", font=font)
                draw.text((60, 250), "ETD: 2026-10-15", fill="black", font=font)
                draw.text((60, 340), "POD: KOBE", fill="black", font=font)
            elif index == page_count - 1 and page_count > 3:
                draw.text((60, 70), "FOURTH PAGE ONLY: TESTLASTPAGE", fill="black", font=font)
            pages.append(image)
        output = io.BytesIO()
        pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:])
        return output.getvalue()
    finally:
        for page in pages:
            page.close()


def _extract(name: str, data: bytes) -> dict:
    started = time.monotonic()
    result = _request("/api/extract", {"mode": "ai", "documents": [
        {"name": name, "role": "入货通知", "data": base64.b64encode(data).decode("ascii")}
    ]})
    fields = result["fields"]
    return {"seconds": round(time.monotonic() - started, 1),
            "bl_number": fields["bl_number"]["value"],
            "vessel": fields["vessel"]["value"],
            "sailing_date": fields["sailing_date"]["value"],
            "destination": fields["destination"]["value"],
            "warnings": result.get("warnings", [])}


def main() -> int:
    config = _request("/api/config")
    print("provider:", config.get("base_url"), "model:", config.get("model"), flush=True)
    if not config.get("ai_available"):
        print("AI settings are not saved in the current server process.", flush=True)
        return 2
    if config.get("base_url") != "https://api.deepseek.com" or config.get("model", "").lower() != "deepseek-flash":
        print("This check requires official DeepSeek deepseek-flash for image input.", flush=True)
        return 2
    from app.tools.document_reader import read_document
    fixtures = [("ordinary.pdf", _text_pdf()), ("scan.pdf", _scan_pdf(1)),
                ("four-pages.pdf", _scan_pdf(4))]
    if not read_document(*fixtures[0]):
        raise RuntimeError("Text PDF fixture has no extractable text")
    if read_document(*fixtures[1]):
        raise RuntimeError("Scanned PDF fixture unexpectedly has a text layer")
    for name, data in fixtures:
        try:
            print(name, json.dumps(_extract(name, data), ensure_ascii=False), flush=True)
        except Exception as error:
            print(name, "FAILED:", str(error)[:350], flush=True)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
