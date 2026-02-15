# B1 -- RAG Design: Resume Screening

## Chunking Strategy

We use **chunk-based RAG** with `RecursiveCharacterTextSplitter` from LangChain.
Each resume (including PDF uploads) is split into overlapping chunks, embedded with
real OpenAI embeddings, and stored in Qdrant for semantic retrieval at scoring time.

| Setting | Value | Why |
|---------|-------|-----|
| Chunk size | 500 characters | Small enough for precise retrieval, large enough for context |
| Chunk overlap | 100 characters | Prevents losing information at chunk boundaries |
| Separators | `\n\n`, `\n`, ` `, `""` | Split on paragraph > line > word > character boundaries |
| Embedding model | `text-embedding-3-small` (1536 dims) | Cost-effective, good quality for document similarity |

**Why chunked RAG:**
- PDF resumes can be multi-page; chunking ensures each section is independently searchable
- At scoring time, only the most relevant chunks (top-5) are sent to GPT-4o, reducing token usage
- Chunks are stored with metadata (`resume_id`, `chunk_index`, `tenant_id`) for precise retrieval
- Deterministic UUIDs (`uuid5`) for chunk point IDs ensure idempotent re-uploads

## Embedding Pipeline

### On Resume Upload (`POST /api/v1/resumes` or `POST /api/v1/resumes/upload-pdf`)

```
Resume (text or PDF)
    │
    ▼
Extract text (PyMuPDF for PDFs)
    │
    ▼
Split into chunks (RecursiveCharacterTextSplitter: 500 chars, 100 overlap)
    │
    ▼
Embed each chunk (OpenAI text-embedding-3-small → 1536-dim vectors)
    │
    ▼
Store chunks in Qdrant (deterministic UUID5 point IDs, tenant_id + resume_id metadata)
    │
    ▼
Save resume in Postgres (embedding_id for cross-reference)
```

1. User uploads resume via API (plain text or PDF file)
2. For PDFs: `pdf_service.extract_text_from_pdf()` extracts text using PyMuPDF
3. `embedding_service.chunk_text(text)` splits into overlapping chunks
4. `embedding_service.embed_texts(chunks)` calls OpenAI embeddings for all chunks
5. `vector_service.upsert_resume_chunks()` stores each chunk vector in Qdrant with metadata
6. Resume row in Postgres updated with `embedding_id` for cross-reference

### On Job Creation (`POST /api/v1/jobs`)

Same flow -- the JD is embedded and stored in Qdrant so we can query against it later.

### On Screening (`POST /api/v1/screen`)

```
1. Load JD embedding from Qdrant (by job.embedding_id)
2. Query Qdrant: "find top-N similar resume chunks, filtered by tenant_id"
3. Deduplicate by resume_id → ranked list of candidate resumes
4. For each resume: retrieve top-5 relevant chunks via RAG
5. Send relevant chunks (not full resume) to GPT-4o for scoring
```

## Embedding Storage in Qdrant

**Collection:** `resumes` (single collection, multi-tenant via payload filter)

Each resume is stored as **multiple chunk points** (not a single point):

```
Point {
    id: "<deterministic_uuid5>",       // uuid5(NAMESPACE_DNS, "{resume_id}:chunk:{index}")
    vector: [float; 1536],
    payload: {
        "tenant_id": "<tenant_uuid>",
        "resume_id": "<resume_uuid>",
        "chunk_index": 0,
        "chunk_text": "actual chunk content...",
        "type": "resume"
    }
}
```

We use a single collection rather than per-tenant collections because:
- Qdrant payload filtering is efficient (indexed)
- Simpler operations (one collection to manage, backup, monitor)
- Tenant count can grow without creating hundreds of collections

## Tenant-Filtered Retrieval

Every vector search includes a mandatory tenant filter:

```python
results = await client.query_points(
    collection_name="resumes",
    query=job_embedding,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="tenant_id",
                match=MatchValue(value=str(tenant_id)),
            )
        ]
    ),
    limit=top_k,
)
```

**There is no code path that queries Qdrant without a tenant filter.**
This mirrors the PostgreSQL isolation strategy: the `tenant_id` is injected from the
JWT-authenticated request context, not from user input.

## Cost Impact

The vector pre-filter is the primary cost control mechanism:

- Without pre-filter: 200 resumes x $0.003/call = $0.60 per screening run
- With pre-filter (top-50): 50 resumes x $0.003/call = $0.15 per screening run
- **75% reduction in LLM costs per screening run**

Combined with Redis caching (eliminates re-screening unchanged JD/resume pairs),
the effective cost is even lower for repeat screenings.
