import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from tess_chat.domain.errors import InvalidInput

MAX_PAGES = 100


class PdfTextExtractor:
    def extract(self, data: bytes, mime: str) -> str:
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise InvalidInput("encrypted PDFs are not supported")
            pages = reader.pages[:MAX_PAGES]
            return "\n\n".join(page.extract_text() or "" for page in pages)
        except PdfReadError as exc:
            raise InvalidInput("could not read the PDF") from exc
