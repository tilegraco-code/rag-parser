import os
import logging
from typing import Optional

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_openai import OpenAIEmbeddings
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_supabase: Optional[Client] = None
_embeddings: Optional[OpenAIEmbeddings] = None
_converter: Optional[DocumentConverter] = None
_chunker: Optional[HybridChunker] = None

SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "documents")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
CHUNK_MAX_TOKENS = int(os.environ.get("CHUNK_MAX_TOKENS", "512"))
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "32"))


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


def ingest_file(file_path: str, metadata: dict = {}) -> int:
    assert _converter and _chunker and _embeddings and _supabase, \
        "Call init_clients() first."

    # 1. Parsear con Docling
    logger.info(f"Parsing {file_path}...")
    result = _converter.convert(file_path)
    doc = result.document

    # 2. Chunkear
    chunks = [c for c in _chunker.chunk(doc) if c.text.strip()]
    logger.info(f"Got {len(chunks)} chunks.")

    if not chunks:
        return 0

    # 3. Embeddings en batches
    texts = [c.text.strip() for c in chunks]
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        vectors.extend(_embeddings.embed_documents(batch))
        logger.info(f"Embedded batch {i // EMBED_BATCH_SIZE + 1}")

    # 4. Upsert en Supabase
    rows = [
        {
            "content": text,
            "metadata": metadata,
            "embedding": vector,
        }
        for text, vector in zip(texts, vectors)
    ]
    _supabase.table(SUPABASE_TABLE).insert(rows).execute()
    logger.info(f"Inserted {len(rows)} rows into Supabase.")

    return len(rows)
