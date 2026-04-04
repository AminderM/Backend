from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import Response
from auth import get_current_user
import tempfile
import os
import re
import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/convert", tags=["File Conversion"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

ACCEPTED_WORD_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
ACCEPTED_WORD_EXTS = (".docx", ".doc")


def _safe_filename(filename: str) -> str:
    """Strip path separators and null bytes from a user-supplied filename."""
    name = os.path.basename(filename)           # drop any directory component
    name = re.sub(r'[^\w\s.\-]', '_', name)    # replace special chars
    return name or "file"


def _check_libreoffice():
    """Raise a 500 if libreoffice is not on PATH."""
    if not shutil.which("libreoffice"):
        logger.error("libreoffice not found on PATH — word-to-pdf conversion unavailable")
        raise HTTPException(
            status_code=500,
            detail="Conversion service unavailable: LibreOffice is not installed on this server.",
        )


# ---------------------------------------------------------------------------
# POST /api/convert/pdf-to-word
# ---------------------------------------------------------------------------

@router.post("/pdf-to-word")
async def pdf_to_word(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """Convert an uploaded PDF to a .docx file and return the binary."""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 20 MB limit")

    safe_name = _safe_filename(file.filename or "input.pdf")
    output_name = re.sub(r'\.pdf$', '.docx', safe_name, flags=re.IGNORECASE)
    if not output_name.lower().endswith(".docx"):
        output_name += ".docx"

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "input.pdf")
        docx_path = os.path.join(tmpdir, "output.docx")

        with open(pdf_path, "wb") as f:
            f.write(contents)

        try:
            from pdf2docx import Converter
            cv = Converter(pdf_path)
            cv.convert(docx_path)
            cv.close()
        except Exception as e:
            logger.error(f"pdf-to-word conversion failed: {e}")
            raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

        if not os.path.exists(docx_path):
            raise HTTPException(status_code=500, detail="Conversion failed: output file not produced")

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )


# ---------------------------------------------------------------------------
# POST /api/convert/word-to-pdf
# ---------------------------------------------------------------------------

@router.post("/word-to-pdf")
async def word_to_pdf(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """Convert an uploaded .docx/.doc file to PDF and return the binary."""
    _check_libreoffice()

    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    filename_lower = (file.filename or "").lower()
    if (
        file.content_type not in ACCEPTED_WORD_TYPES
        and not filename_lower.endswith(ACCEPTED_WORD_EXTS)
    ):
        raise HTTPException(status_code=400, detail="Only .docx or .doc files are accepted")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 20 MB limit")

    safe_name = _safe_filename(file.filename or "input.docx")
    pdf_name = re.sub(r'\.(docx|doc)$', '.pdf', safe_name, flags=re.IGNORECASE)
    if not pdf_name.lower().endswith(".pdf"):
        pdf_name += ".pdf"

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, safe_name)
        with open(input_path, "wb") as f:
            f.write(contents)

        try:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmpdir, input_path],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise Exception(result.stderr.decode())
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Conversion timed out")
        except Exception as e:
            logger.error(f"word-to-pdf conversion failed: {e}")
            raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

        pdf_path = os.path.join(tmpdir, pdf_name)
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=500, detail="Conversion failed: output PDF not found")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_name}"'},
    )