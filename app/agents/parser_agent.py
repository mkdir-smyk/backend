import fitz  # PyMuPDF
from fastapi import UploadFile


async def parse_pdf(file: UploadFile) -> str:
    """Extracts text from an uploaded PDF file asynchronously."""
    content = await file.read()
    text = ""
    try:
        # PyMuPDF can read from memory via fitz.Document(stream=...)
        doc = fitz.Document(stream=content, filetype="pdf")
        for page in doc:
            text += page.get_text() + "\n"
    except Exception as e:
        from app.core.logger import get_logger
        logger = get_logger(__name__)
        logger.error(f"Error parsing PDF: {e}")
    finally:
        await file.seek(0)
        
    return text.strip()
