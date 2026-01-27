# Retrieval System Documentation

This document describes the hybrid retrieval system used in the RAG chatbot.

## Overview

The retrieval system uses Azure AI Search to find relevant chunks from indexed manuals. It supports three search modes:

1. **Hybrid Search** (default) - Combines vector and keyword search
2. **Vector Search** - Semantic similarity using embeddings
3. **Keyword Search** - Traditional BM25 text matching

## Hybrid Search Implementation

Hybrid search combines the strengths of both vector and keyword search:

### How It Works

1. **Query Embedding**: The user's query is converted to a vector using Azure OpenAI's embedding model (text-embedding-ada-002 or text-embedding-3-small).

2. **Parallel Search**: Azure AI Search executes both searches simultaneously:
   - **Vector Search**: Finds semantically similar content using HNSW algorithm with cosine similarity
   - **Keyword Search**: Finds exact and stemmed term matches using BM25

3. **Result Fusion**: Azure AI Search combines results using **Reciprocal Rank Fusion (RRF)**:
   ```
   RRF_score = Σ (1 / (k + rank_i))
   ```
   Where `k` is a constant (typically 60) and `rank_i` is the rank from each search method.

### Why Hybrid?

| Search Type | Strengths | Weaknesses |
|-------------|-----------|------------|
| Vector | Semantic understanding, handles synonyms | May miss exact terms |
| Keyword | Precise term matching, good for names/codes | No semantic understanding |
| Hybrid | Best of both worlds | Slightly higher latency |

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TOP_K` | 6 | Number of chunks to retrieve |
| `MIN_GROUNDED_SCORE` | 0.7 | Minimum score threshold for grounding |

### Adjusting TOP_K

- **Lower (3-4)**: Faster, more focused context, risk of missing relevant info
- **Higher (8-10)**: More comprehensive, but may include noise, longer prompts

Recommended: Start with 6, adjust based on answer quality.

## Search Client Usage

### Basic Hybrid Search

```python
from app.clients.search_client import get_search_client

client = get_search_client()
results = client.hybrid_search(
    query="What are the fire safety procedures?",
    top_k=6
)

for result in results:
    print(f"{result.manual_name} p{result.page}: score={result.score}")
```

### Filtered Search

```python
# Search within a specific manual
results = client.hybrid_search(
    query="emergency evacuation",
    filter_expression="manual_name eq 'Safety_Manual.pdf'"
)

# Search within page range
results = client.hybrid_search(
    query="maintenance schedule",
    filter_expression="page ge 10 and page le 50"
)
```

## Retrieval Service

The `RetrievalService` provides a higher-level interface:

```python
from app.services.retrieval import get_retrieval_service

service = get_retrieval_service()

# Retrieve chunks
results = service.retrieve(
    query="How do I reset the control panel?",
    top_k=6
)

# Check if results are relevant
if service.has_relevant_results(results):
    context = service.get_context_for_prompt(results)
else:
    # Handle no relevant results
    pass
```

## Search Result Structure

Each `SearchResult` contains:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique document ID |
| `manual_name` | str | Source PDF filename |
| `page` | int | Page number (1-indexed) |
| `chunk_id` | str | Unique chunk identifier |
| `content` | str | Text content of the chunk |
| `section_title` | str | Section heading (optional) |
| `image_caption` | str | Image description (optional) |
| `score` | float | Combined search score |
| `reranker_score` | float | Semantic reranker score (if enabled) |

## Grounding Threshold

The `MIN_GROUNDED_SCORE` threshold determines when results are considered relevant:

- **Score >= threshold**: Results are used for answer generation
- **Score < threshold**: System returns "I don't know" response

This prevents hallucination when the query doesn't match indexed content.

## Performance Considerations

1. **Embedding Latency**: ~100-200ms per query embedding
2. **Search Latency**: ~50-150ms for hybrid search
3. **Total Retrieval**: ~150-350ms typical

### Optimization Tips

- Use filters to narrow search scope
- Cache frequent query embeddings
- Consider async operations for parallel requests

## Logging

The retrieval system logs metadata without exposing content:

```
INFO: Retrieved 6 chunks for query (top_k=6, filter=None)
DEBUG: [1] Safety_Manual.pdf p12 (safety_manual_p12_c1) score=0.8542
DEBUG: [2] Safety_Manual.pdf p15 (safety_manual_p15_c1) score=0.7891
```

Content is never logged to protect confidential manual information.
