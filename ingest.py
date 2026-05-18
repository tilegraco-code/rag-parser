import os
import logging
from typing import Optional
from datetime import datetime, timezone

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_openai import OpenAIEmbeddings
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_supabase: Optional[Client] = None
_embeddings: Optional[OpenAIEmbeddings] = None
_converter: Optional[DocumentConverter] = None
_chunker: Optional[HybridChunker] = None

DOCUMENTS_TABLE = "documents"
CHUNKS_TABLE = "document_chunks"

EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
CHUNK_MAX_TOKENS = int(os.environ.get("CHUNK_MAX_TOKENS", "512"))
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "32"))

# Estados de documents (la fn match_document_chunks solo busca status = 'ready')
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


def init_clients():
    global _supabase, _embeddings, _converter, _chunker

    _supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    _embeddings = OpenAIEmbeddings(
        model=EMBED_MODEL,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )
    _converter = DocumentConverter()
    _chunker = HybridChunker(max_tokens=CHUNK_MAX_TOKENS)

    logger.info("All clients initialized.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _page_count(doc) -> Optional[int]:
    """Cantidad de páginas si Docling la expone; None si no."""
    try:
        pages = getattr(doc, "pages", None)
        if pages:
            return len(pages)
    except Exception:
        pass
    return None


def ingest_file(
    file_path: str,
    *,
    filename: str,
    mime_type: str,
    size_bytes: int,
    project_id: Optional[int] = None,
) -> dict:
    """
    Flujo de 2 tablas:
      1. Inserta fila en `documents` (status=processing) -> obtiene document_id
      2. Parsea + chunkea con Docling
      3. Embeddings en batches
      4. Inserta chunks en `document_chunks`
      5. Actualiza `documents` -> status=ready, chunk_count, page_count
      6. Si algo falla -> status=failed, error_message
    """
    assert _converter and _chunker and _embeddings and _supabase, \
        "Call init_clients() first."

    # 1. Crear la fila en documents
    doc_row = {
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "status": STATUS_PROCESSING,
        "chunk_count": 0,
        "project_id": project_id,
    }
    inserted = _supabase.table(DOCUMENTS_TABLE).insert(doc_row).execute()
    document_id = inserted.data[0]["id"]
    logger.info(f"Created documents row {document_id} for {filename!r}")

    try:
        # 2. Parsear con Docling
        logger.info(f"Parsing {file_path}...")
        result = _converter.convert(file_path)
        doc = result.document
        page_count = _page_count(doc)

        # Chunkear
        chunks = [c for c in _chunker.chunk(doc) if c.text.strip()]
        logger.info(f"Got {len(chunks)} chunks.")

        texts = [c.text.strip() for c in chunks]

        # 3. Embeddings en batches
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            vectors.extend(_embeddings.embed_documents(batch))
            logger.info(f"Embedded batch {i // EMBED_BATCH_SIZE + 1}")

        # 4. Insertar chunks
        if texts:
            rows = [
                {
                    "document_id": document_id,
                    "chunk_index": idx,
                    "content": text,
                    # pgvector acepta el literal de texto "[...]"
                    "embedding": "[" + ",".join(map(repr, vector)) + "]",
                    "metadata": {
                        "filename": filename,
                        "project_id": project_id,
                        "chunk_index": idx,
                    },
                }
                for idx, (text, vector) in enumerate(zip(texts, vectors))
            ]
            # Insertar de a batches para no pegarle al límite de payload
            for i in range(0, len(rows), EMBED_BATCH_SIZE):
                _supabase.table(CHUNKS_TABLE).insert(
                    rows[i : i + EMBED_BATCH_SIZE]
                ).execute()
            logger.info(f"Inserted {len(rows)} chunks for document {document_id}")

        # 5. Marcar el documento como listo
        _supabase.table(DOCUMENTS_TABLE).update(
            {
                "status": STATUS_READY,
                "chunk_count": len(texts),
                "page_count": page_count,
                "updated_at": _now_iso(),
            }
        ).eq("id", document_id).execute()

        return {
            "document_id": document_id,
            "chunks_inserted": len(texts),
            "page_count": page_count,
        }

    except Exception as e:
        logger.exception(f"Ingest failed for document {document_id}")
        _supabase.table(DOCUMENTS_TABLE).update(
            {
                "status": STATUS_FAILED,
                "error_message": str(e)[:1000],
                "updated_at": _now_iso(),
            }
        ).eq("id", document_id).execute()
        raise
