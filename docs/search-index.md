# Azure AI Search Index Schema

This document defines the Azure AI Search index schema for the RAG chatbot, enabling hybrid (keyword + vector) retrieval with citation support.

## Index Overview

The index stores chunked content from PDF manuals with metadata for citations and filtering.

**Index Name**: `manuals-index` (configurable via `AZURE_SEARCH_INDEX`)

## Field Definitions

### Core Fields

| Field | Type | Key | Searchable | Filterable | Sortable | Facetable | Purpose |
|-------|------|-----|------------|------------|----------|-----------|---------|
| `id` | Edm.String | Yes | No | No | No | No | Unique document identifier |
| `manual_name` | Edm.String | No | Yes | Yes | Yes | Yes | Source PDF filename for citations |
| `page` | Edm.Int32 | No | No | Yes | Yes | Yes | Page number (1-indexed) for citations |
| `chunk_id` | Edm.String | No | No | Yes | No | No | Unique chunk identifier |
| `content` | Edm.String | No | Yes | No | No | No | Main text content of the chunk |
| `content_vector` | Collection(Edm.Single) | No | Yes (vector) | No | No | No | Embedding vector for semantic search |
| `image_caption` | Edm.String | No | Yes | No | No | No | Generated caption for images/diagrams |
| `section_title` | Edm.String | No | Yes | Yes | No | Yes | Section heading for context |
| `last_updated` | Edm.DateTimeOffset | No | No | Yes | Yes | No | Timestamp for incremental updates |

### Field Details

#### id (Key Field)
- **Format**: `{manual_name_slug}_{page}_{chunk_number}`
- **Example**: `safety_manual_v2_p42_c3`
- **Purpose**: Uniquely identifies each chunk for updates and deletions

#### manual_name
- **Searchable**: Yes - allows keyword search within specific manuals
- **Filterable**: Yes - enables queries like `manual_name eq 'Safety_Manual.pdf'`
- **Facetable**: Yes - allows listing all available manuals

#### page
- **Filterable**: Yes - enables page range queries
- **Sortable**: Yes - allows ordering results by page number
- **Purpose**: Essential for citations

#### content
- **Searchable**: Yes - primary field for keyword search
- **Analyzer**: `en.microsoft` (English analyzer with stemming)
- **Purpose**: Main text content for retrieval

#### content_vector
- **Dimensions**: 1536 (for text-embedding-ada-002) or 1536/3072 (for text-embedding-3-small/large)
- **Algorithm**: HNSW (Hierarchical Navigable Small World)
- **Metric**: Cosine similarity
- **Purpose**: Enables semantic/vector search

#### image_caption
- **Searchable**: Yes - allows finding content by diagram descriptions
- **Nullable**: Yes - only populated for image chunks
- **Purpose**: Makes diagrams and images searchable

#### section_title
- **Searchable**: Yes - allows searching by section names
- **Filterable**: Yes - enables filtering by section
- **Purpose**: Provides context and improves retrieval

## Vector Search Configuration

### Vector Profile

```json
{
    "name": "vector-profile",
    "algorithm": "hnsw-algorithm",
    "vectorizer": null
}
```

### HNSW Algorithm Configuration

```json
{
    "name": "hnsw-algorithm",
    "kind": "hnsw",
    "hnswParameters": {
        "m": 4,
        "efConstruction": 400,
        "efSearch": 500,
        "metric": "cosine"
    }
}
```

**Parameters Explained**:
- `m`: Number of bi-directional links (4 is good balance of speed/recall)
- `efConstruction`: Size of dynamic candidate list during indexing (higher = better recall, slower indexing)
- `efSearch`: Size of dynamic candidate list during search (higher = better recall, slower search)
- `metric`: Cosine similarity for normalized embeddings

## Hybrid Search Configuration

The index supports hybrid search combining:
1. **Keyword Search**: BM25 on `content`, `image_caption`, `section_title`
2. **Vector Search**: Cosine similarity on `content_vector`

### Search Query Example

```python
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

# Hybrid search with vector and keyword
vector_query = VectorizedQuery(
    vector=query_embedding,
    k_nearest_neighbors=TOP_K,
    fields="content_vector"
)

results = search_client.search(
    search_text=user_query,
    vector_queries=[vector_query],
    select=["id", "manual_name", "page", "chunk_id", "content", "section_title"],
    filter="manual_name eq 'Safety_Manual.pdf'",  # Optional filter
    top=TOP_K
)
```

## Semantic Configuration (Optional)

For enhanced ranking with semantic understanding:

```json
{
    "name": "semantic-config",
    "prioritizedFields": {
        "titleField": {
            "fieldName": "section_title"
        },
        "contentFields": [
            {
                "fieldName": "content"
            },
            {
                "fieldName": "image_caption"
            }
        ]
    }
}
```

**Note**: Semantic ranking requires Standard tier or higher.

## Filter Examples

### Filter by Manual

```odata
manual_name eq 'Safety_Manual.pdf'
```

### Filter by Page Range

```odata
page ge 10 and page le 50
```

### Filter by Section

```odata
section_title eq 'Emergency Procedures'
```

### Filter by Multiple Manuals

```odata
search.in(manual_name, 'Safety_Manual.pdf,Operations_Guide.pdf', ',')
```

### Filter by Date (for incremental updates)

```odata
last_updated ge 2024-01-01T00:00:00Z
```

## Index Creation

### Using Azure CLI

```bash
az search index create \
    --name manuals-index \
    --service-name <search-service-name> \
    --resource-group <resource-group> \
    --fields @infra/search-index.json
```

### Using Python SDK

```python
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

index = SearchIndex(
    name="manuals-index",
    fields=[...],  # See infra/search-index.json
    vector_search=VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw-algorithm")
        ],
        profiles=[
            VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw-algorithm")
        ]
    )
)

index_client.create_or_update_index(index)
```

## Citation Format

When returning results, format citations as:

```
[Manual Name, Page X, Chunk ID]
```

Example:
```
According to the safety procedures [Safety_Manual.pdf, Page 42, safety_manual_p42_c3], 
employees must evacuate immediately when the fire alarm sounds.
```

## Performance Considerations

1. **Indexing**: Batch uploads of 1000 documents for optimal throughput
2. **Search**: Use `select` to return only needed fields
3. **Filters**: Apply filters to reduce search scope
4. **Vector dimensions**: Match embedding model dimensions exactly

## Index Maintenance

### Refresh Strategy

1. **Full refresh**: Delete and recreate index (for major changes)
2. **Incremental**: Use `last_updated` filter to find stale documents
3. **Merge**: Use merge operations for partial updates

### Monitoring

- Track index size and document count
- Monitor search latency
- Review search analytics for query patterns
