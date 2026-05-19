import os
import tempfile
import logging
import mimetypes
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, Header, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from ingest import ingest_file, init_clients

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INTERNAL_TOKEN = os.environ["INTERNAL_TOKEN"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing clients and Docling models...")
    init_clients()
    logger.info("Ready.")
    yield


app = FastAPI(title="RAG Parser Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


def verify_token(x_internal_token: str = Header(...)):
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/parse")
async def parse(
    file: UploadFile,
    project_id: Optional[str] = Form(default=None),
    x_internal_token: str = Header(...),
):
    verify_token(x_internal_token)

    allowed = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".html", ".htm", ".md"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}")

    # project_id llega como string del form-data; lo pasamos a int si vino
    pid: Optional[int] = None
    if project_id not in (None, ""):
        try:
            pid = int(project_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="project_id debe ser un entero"
            )

    data = await file.read()
    size_bytes = len(data)
    mime_type = (
        file.content_type
        or mimetypes.guess_type(file.filename or "")[0]
        or "application/octet-stream"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        result = ingest_file(
            file_path=tmp_path,
            filename=file.filename or f"upload{ext}",
            mime_type=mime_type,
            size_bytes=size_bytes,
            project_id=pid,
        )
    finally:
        os.unlink(tmp_path)

    return {"status": "ok", **result}
