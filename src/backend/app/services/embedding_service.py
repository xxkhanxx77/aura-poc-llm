"""Embedding service -- RAG pipeline with real OpenAI embeddings and text chunking.

Flow:
  1. Text chunking (RecursiveCharacterTextSplitter, 500 chars, 100 overlap)
  2. Embed each chunk with OpenAI text-embedding-3-small
  3. Store chunk vectors in Qdrant with metadata
  4. At query time, retrieve most relevant chunks per resume
"""

import logging
from uuid import UUID

from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services import vector_service

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-3-small dimension
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

_embeddings_model: OpenAIEmbeddings | None = None


def get_embeddings_model() -> OpenAIEmbeddings:
    """Get or create the OpenAI embeddings model."""
    global _embeddings_model
    if _embeddings_model is None:
        _embeddings_model = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )
    return _embeddings_model


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_text(text)
    return chunks if chunks else [text]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using OpenAI embeddings."""
    model = get_embeddings_model()
    return await model.aembed_documents(texts)


async def embed_query(text: str) -> list[float]:
    """Embed a single query text (for search)."""
    model = get_embeddings_model()
    return await model.aembed_query(text)


async def embed_and_store_resume(
    resume_id: UUID,
    tenant_id: UUID,
    text: str,
) -> str:
    """Chunk resume text, embed each chunk, and store in Qdrant.

    Returns the resume_id as the embedding reference.
    """
    chunks = chunk_text(text)
    embeddings = await embed_texts(chunks)

    await vector_service.ensure_collection()
    await vector_service.upsert_resume_chunks(
        resume_id=resume_id,
        tenant_id=tenant_id,
        chunks=chunks,
        embeddings=embeddings,
    )

    logger.info(
        "Stored %d chunk embeddings for resume %s (tenant %s)",
        len(chunks), resume_id, tenant_id,
    )
    return str(resume_id)


async def embed_and_store_job(
    job_id: UUID,
    tenant_id: UUID,
    text: str,
) -> str:
    """Embed job description and store in Qdrant (single vector, no chunking)."""
    embedding = await embed_query(text)

    await vector_service.ensure_collection()

    from qdrant_client.models import PointStruct

    client = vector_service.get_qdrant_client()
    await client.upsert(
        collection_name=vector_service.COLLECTION_NAME,
        points=[
            PointStruct(
                id=str(job_id),
                vector=embedding,
                payload={"tenant_id": str(tenant_id), "type": "job"},
            )
        ],
    )
    logger.info("Stored embedding for job %s (tenant %s)", job_id, tenant_id)
    return str(job_id)


async def get_embedding_vector(point_id: str) -> list[float]:
    """Retrieve an existing embedding vector from Qdrant by point ID."""
    client = vector_service.get_qdrant_client()
    points = await client.retrieve(
        collection_name=vector_service.COLLECTION_NAME,
        ids=[point_id],
        with_vectors=True,
    )
    if not points:
        raise ValueError(f"Embedding not found for point {point_id}")
    return points[0].vector


async def retrieve_resume_chunks(
    resume_id: UUID,
    job_embedding: list[float],
    top_k: int = 5,
) -> str:
    """Retrieve the most relevant chunks for a resume given a job embedding.

    Returns assembled text from top-K matching chunks.
    """
    chunks = await vector_service.find_resume_chunks(
        resume_id=resume_id,
        job_embedding=job_embedding,
        top_k=top_k,
    )
    if not chunks:
        return ""
    return "\n\n".join(chunks)
