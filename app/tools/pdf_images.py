"""Render a bounded number of PDF pages in memory for vision-capable models."""

import io

import pypdfium2


MAX_VISION_PAGES = 3


def render_pdf_pages(data: bytes, *, max_pages: int = MAX_VISION_PAGES) -> tuple[list[bytes], int]:
    """Return JPEG page images and the total page count without writing files."""
    pdf = pypdfium2.PdfDocument(data)
    images = []
    try:
        total = len(pdf)
        for index in range(min(total, max_pages)):
            page = pdf[index]
            try:
                width, height = page.get_size()
                scale = min(2.2, 1800 / max(width, height))
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert("RGB")
                    try:
                        output = io.BytesIO()
                        image.save(output, format="JPEG", quality=83, optimize=True)
                        images.append(output.getvalue())
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return images, total
    finally:
        pdf.close()
