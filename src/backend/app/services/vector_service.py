"""Vector DB (Qdrant) integration for semantic resume matching.

Supports chunked resume storage -- each resume is split into multiple chunks,
each stored as a separate vector with metadata linking back to the resume.
"""

import logging
import uuid as uuid_mod
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "resumes"
VECTOR_DIM = 1536  # text-embedding-3-small dimension

_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    return _qdrant_client


async def ensure_collection() -> None:
    """Create the resumes collection if it doesn't exist."""
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", COLLECTION_NAME)


def _chunk_point_id(resume_id: UUID, chunk_index: int) -> str:
    """Generate a deterministic UUID for a resume chunk."""
    return str(uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, f"{resume_id}:chunk:{chunk_index}"))


async def upsert_resume_chunks(
    resume_id: UUID,
    tenant_id: UUID,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    """Store multiple chunk embeddings for a single resume."""
    client = get_qdrant_client()
    points = [
        PointStruct(
            id=_chunk_point_id(resume_id, i),
            vector=embedding,
            payload={
                "tenant_id": str(tenant_id),
                "resume_id": str(resume_id),
                "chunk_index": i,
                "chunk_text": chunk,
                "type": "resume_chunk",
            },
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    await client.upsert(collection_name=COLLECTION_NAME, points=points)


async def upsert_resume_embedding(
    resume_id: UUID,
    tenant_id: UUID,
    embedding: list[float],
) -> None:
    """Store a single resume embedding (backward compat for text uploads)."""
    client = get_qdrant_client()
    await client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=str(resume_id),
                vector=embedding,
                payload={"tenant_id": str(tenant_id), "type": "resume"},
            )
        ],
    )


async def find_similar_resumes(
    tenant_id: UUID,
    job_embedding: list[float],
    top_k: int | None = None,
) -> list[str]:
    """Find the top-K most similar resume IDs for a given JD embedding.

    Searches across all chunk vectors and deduplicates by resume_id.
    Results are filtered by tenant_id for isolation.
    """
    if top_k is None:
        top_k = settings.max_resumes_per_screen

    client = get_qdrant_client()
    # Search more chunks to ensure we get enough unique resumes
    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=job_embedding,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="tenant_id",
                    match=MatchValue(value=str(tenant_id)),
                )
            ]
        ),
        limit=top_k * 5,  # fetch more since chunks may belong to same resume
    )

    # Deduplicate by resume_id, keeping order (best match first)
    seen = set()
    resume_ids = []
    for point in results.points:
        payload = point.payload or {}
        # Chunk points have resume_id in payload; single-vector points use point.id
        rid = payload.get("resume_id", str(point.id))
        if rid not in seen:
            seen.add(rid)
            resume_ids.append(rid)
        if len(resume_ids) >= top_k:
            break

    return resume_ids


async def find_resume_chunks(
    resume_id: UUID,
    job_embedding: list[float],
    top_k: int = 5,
) -> list[str]:
    """Find the most relevant chunks for a specific resume given a job embedding.

    Returns chunk texts sorted by relevance.
    """
    client = get_qdrant_client()
    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=job_embedding,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="resume_id",
                    match=MatchValue(value=str(resume_id)),
                ),
                FieldCondition(
                    key="type",
                    match=MatchValue(value="resume_chunk"),
                ),
            ]
        ),
        limit=top_k,
    )

    # Sort by chunk_index to maintain document order
    chunks = []
    for point in results.points:
        payload = point.payload or {}
        chunk_text = payload.get("chunk_text", "")
        chunk_index = payload.get("chunk_index", 0)
        if chunk_text:
            chunks.append((chunk_index, chunk_text))

    chunks.sort(key=lambda x: x[0])
    return [text for _, text in chunks]
