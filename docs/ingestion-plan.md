# Ingestion Plan for Manuals

This document describes the step-by-step ingestion process for making 50+ confidential manuals searchable, including handling text, images, diagrams, scanned photos, and handwritten content.

## Overview

The ingestion pipeline processes PDF manuals through multiple stages to extract all searchable content:

```
PDF Manual → Classification → Extraction → Chunking → Embedding → Indexing
```

## Stage 1: PDF Classification

Each PDF page is classified to determine the extraction method:

### Classification Logic

1. **Digital PDF** (native text)
   - Text can be extracted directly using PDF libraries
   - Detected by: Text extraction yields readable content

2. **Scanned/Image PDF**
   - Pages are images without embedded text
   - Detected by: Text extraction yields empty or garbled content
   - Requires: OCR processing

3. **Mixed PDF**
   - Some pages digital, some scanned
   - Process each page according to its type

## Stage 2: Text Extraction

### For Digital PDFs

```python
# Using pypdf for native text extraction
from pypdf import PdfReader

reader = PdfReader("manual.pdf")
for page_num, page in enumerate(reader.pages):
    text = page.extract_text()
    # Process text...
```

### For Scanned/Image PDFs

**Primary Method: Azure Document Intelligence**

```python
from azure.ai.documentintelligence import DocumentIntelligenceClient

# Use prebuilt-read model for general OCR
# Use prebuilt-layout for structure-aware extraction
poller = client.begin_analyze_document(
    "prebuilt-read",
    document=pdf_bytes
)
result = poller.result()
```

**Benefits of Document Intelligence**:
- High accuracy for printed text
- Good handwriting recognition
- Preserves reading order
- Extracts tables and structure

**Alternative: Azure AI Search OCR Skill**
- Built into the indexing pipeline
- Less accurate for handwriting
- Simpler setup but less control

## Stage 3: Image and Diagram Processing

### 3.1 Extract Embedded Images

```python
from pypdf import PdfReader
from PIL import Image
import io

reader = PdfReader("manual.pdf")
for page_num, page in enumerate(reader.pages):
    for image_obj in page.images:
        image_bytes = image_obj.data
        # Process image...
```

### 3.2 OCR on Images

Run Azure Document Intelligence on extracted images to capture any text within diagrams:

```python
poller = client.begin_analyze_document(
    "prebuilt-read",
    document=image_bytes
)
image_text = poller.result().content
```

### 3.3 Generate Image Captions

For diagrams and images, generate a textual description to make them searchable:

**Option A: Azure OpenAI GPT-4 Vision**

```python
response = openai_client.chat.completions.create(
    model=CHAT_DEPLOYMENT,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this diagram in 2-3 sentences for search indexing."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
            ]
        }
    ],
    max_tokens=150
)
caption = response.choices[0].message.content
```

**Option B: Azure Computer Vision (Image Analysis)**
- Use for simpler captioning needs
- Lower cost but less detailed descriptions

### 3.4 Image Processing Output

Each image produces:
- `image_ocr_text`: Any text found in the image
- `image_caption`: Generated description of the image/diagram
- `image_page`: Page number where image was found

## Stage 4: Chunking Strategy

### Chunk Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Target size | 800-1200 tokens | Balances context with retrieval precision |
| Overlap | 150-250 tokens | Ensures continuity across chunk boundaries |
| Max size | 1500 tokens | Hard limit for embedding model |

### Chunking Rules

1. **Respect document structure**
   - Prefer breaking at section/paragraph boundaries
   - Keep headings with their content

2. **Preserve context**
   - Include section title in each chunk
   - Maintain reading order

3. **Handle special content**
   - Tables: Keep together if under max size, else split by rows
   - Lists: Keep together if under max size
   - Images: Create separate chunks for image captions

### Chunking Implementation

```python
def chunk_text(text: str, metadata: dict) -> list[dict]:
    """
    Chunk text with overlap and metadata preservation.
    """
    chunks = []
    # Use tiktoken for accurate token counting
    # Split on paragraph boundaries when possible
    # Add overlap from previous chunk
    # Attach metadata to each chunk
    return chunks
```

### Metadata per Chunk

| Field | Description | Example |
|-------|-------------|---------|
| `manual_name` | Source PDF filename | "Safety_Manual_v2.pdf" |
| `page` | Page number (1-indexed) | 42 |
| `chunk_id` | Unique identifier | "safety_manual_v2_p42_c3" |
| `section_title` | Current section heading | "Emergency Procedures" |
| `content_type` | Type of content | "text" / "image_caption" / "table" |

## Stage 5: Embedding Generation

### Embedding Model

**Recommended**: `text-embedding-3-small` or `text-embedding-ada-002`

```python
response = openai_client.embeddings.create(
    model=EMBED_DEPLOYMENT,
    input=chunk_text
)
vector = response.data[0].embedding
```

### Embedding Considerations

- Batch embeddings for efficiency (max 16 texts per request)
- Handle rate limits with exponential backoff
- Cache embeddings to avoid reprocessing

## Stage 6: Index Upload

### Document Structure for Azure AI Search

```json
{
    "id": "safety_manual_v2_p42_c3",
    "manual_name": "Safety_Manual_v2.pdf",
    "page": 42,
    "chunk_id": "safety_manual_v2_p42_c3",
    "section_title": "Emergency Procedures",
    "content": "In case of fire, immediately evacuate...",
    "content_vector": [0.123, -0.456, ...],
    "image_caption": null,
    "last_updated": "2024-01-15T10:30:00Z"
}
```

### Upload Strategy

- Use batch upload (max 1000 documents per batch)
- Implement retry logic for transient failures
- Track upload status for each document

## Pipeline Architecture

```
+------------------------------------------------------------------+
|                     Ingestion Pipeline                            |
+------------------------------------------------------------------+
|                                                                   |
|  +----------+    +----------+    +----------+    +----------+    |
|  |  Blob    |--->|  PDF     |--->|  Chunk   |--->|  Embed   |    |
|  |  Storage |    |  Extract |    |  + Meta  |    |  + Index |    |
|  +----------+    +----------+    +----------+    +----------+    |
|       |               |               |               |          |
|       |               v               |               v          |
|       |         +----------+         |         +----------+     |
|       |         |  Doc     |         |         |  Azure   |     |
|       |         |  Intel   |         |         |  AI      |     |
|       |         |  (OCR)   |         |         |  Search  |     |
|       |         +----------+         |         +----------+     |
|       |               |               |                          |
|       |               v               |                          |
|       |         +----------+         |                          |
|       |         |  GPT-4V  |         |                          |
|       |         |  Caption |         |                          |
|       |         +----------+         |                          |
|       |                               |                          |
+-------+-------------------------------+--------------------------+
```

## Error Handling

1. **PDF parsing errors**: Log and skip corrupted pages, continue with rest
2. **OCR failures**: Retry with different model, fall back to empty text
3. **Embedding failures**: Retry with backoff, queue for later
4. **Index upload failures**: Retry batch, split if needed

## Incremental Updates

For updating existing manuals:

1. Compare file hash to detect changes
2. Delete old chunks for changed manual
3. Re-process only changed pages if possible
4. Upload new chunks with updated `last_updated`

## Logging and Monitoring

**Do NOT log**:
- Raw manual content (confidential)
- Full chunk text

**DO log**:
- Manual name and processing status
- Page counts and chunk counts
- Processing times and errors
- Upload success/failure counts
