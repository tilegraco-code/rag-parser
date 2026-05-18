import os
import tempfile
import logging
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
    user_id: str = Form(default=""),
    x_internal_token: str = Header(...),
):
    verify_token(x_internal_token)

    allowed = {".pdf", ".docx", ".doc"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        count = ingest_file(
            file_path=tmp_path,
            metadata={"user_id": user_id, "filename": file.filename},
        )
    finally:
        os.unlink(tmp_path)

    return {"status": "ok", "chunks_inserted": count}
