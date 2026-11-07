import io

from pypdf import PdfReader


class DocumentError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def extract_pdf_text(data: bytes, *, max_pages: int, max_chars: int, min_chars: int) -> str:
    if not data.startswith(b"%PDF-"):
        raise DocumentError("INVALID_PDF", "O arquivo não é um PDF válido.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("PDF_ENCRYPTED", "PDF protegido por senha não é suportado.")
        if len(reader.pages) > max_pages:
            raise DocumentError("PDF_TOO_MANY_PAGES", f"PDF excede o limite de {max_pages} páginas.", 413)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except DocumentError:
        raise
    except Exception as exc:  # pypdf lança tipos variados em arquivos corrompidos
        raise DocumentError("INVALID_PDF", "Não foi possível ler o PDF.") from exc
    if len(text.strip()) < min_chars:
        raise DocumentError(
            "PDF_NO_TEXT", "PDF sem texto extraível (escaneado?). OCR não é suportado no MVP."
        )
    if len(text) > max_chars:
        raise DocumentError("TEXT_TOO_LONG", f"Texto excede {max_chars} caracteres.", 413)
    return text
