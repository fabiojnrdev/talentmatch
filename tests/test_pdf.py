import io

import pytest
from reportlab.pdfgen import canvas

from app.privacy.pdf import DocumentError, extract_pdf_text

KW = dict(max_pages=2, max_chars=500, min_chars=20)


def make_pdf(lines=None, pages=1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(pages):
        for i, line in enumerate(lines or []):
            c.drawString(50, 800 - 20 * i, line)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_extracts_text():
    text = extract_pdf_text(make_pdf(["Experiencia com FastAPI e Celery em producao"]), **KW)
    assert "FastAPI" in text


@pytest.mark.parametrize("data,code,status", [
    (b"not a pdf", "INVALID_PDF", 422),
    (b"%PDF-1.4 lixo corrompido", "INVALID_PDF", 422),
    (make_pdf([]), "PDF_NO_TEXT", 422),
    (make_pdf(["texto"] * 1, pages=3), "PDF_TOO_MANY_PAGES", 413),
    (make_pdf(["x" * 100] * 10), "TEXT_TOO_LONG", 413),
])
def test_rejections(data, code, status):
    with pytest.raises(DocumentError) as exc:
        extract_pdf_text(data, **KW)
    assert exc.value.code == code and exc.value.http_status == status


def test_encrypted_pdf_rejected():
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(make_pdf(["Texto longo o bastante para passar"]))).pages:
        writer.add_page(page)
    writer.encrypt("segredo")
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(DocumentError) as exc:
        extract_pdf_text(buf.getvalue(), **KW)
    assert exc.value.code == "PDF_ENCRYPTED"
