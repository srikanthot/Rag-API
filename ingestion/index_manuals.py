"""
Ingestion pipeline for indexing manual chunks into Azure AI Search.

This script:
1. Reads processed chunks from a JSON file
2. Generates embeddings using Azure OpenAI
3. Uploads documents to Azure AI Search index
4. Supports idempotent upserts (same chunk_id = update)

Usage:
    python -m ingestion.index_manuals --input ingestion/sample_chunks.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import IndexingResult
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.clients.openai_client import get_openai_client

# Configure logging - do not log raw content
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_chunks(input_path: str) -> list[dict]:
    """Load chunks from a JSON file.

    Args:
        input_path: Path to the JSON file containing chunks.

    Returns:
        List of chunk dictionaries.
    """
    logger.info(f"Loading chunks from: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    logger.info(f"Loaded {len(chunks)} chunks")
    return chunks


def validate_chunk(chunk: dict) -> bool:
    """Validate that a chunk has required fields.

    Args:
        chunk: Chunk dictionary to validate.

    Returns:
        True if valid, False otherwise.
    """
    required_fields = ["id", "manual_name", "page", "chunk_id", "content"]
    for field in required_fields:
        if field not in chunk:
            logger.warning(f"Chunk missing required field: {field}")
            return False
        if field == "content" and not chunk[field]:
            logger.warning(f"Chunk {chunk.get('id', 'unknown')} has empty content")
            return False
    return True


def generate_embeddings(
    chunks: list[dict],
    openai_client,
    batch_size: int = 16,
) -> list[dict]:
    """Generate embeddings for chunks.

    Args:
        chunks: List of chunk dictionaries.
        openai_client: OpenAI client instance.
        batch_size: Number of texts to embed per API call.

    Returns:
        Chunks with content_vector field added.
    """
    logger.info(f"Generating embeddings for {len(chunks)} chunks...")

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(chunks) + batch_size - 1) // batch_size

        # Prepare texts for embedding - combine content and image_caption if present
        texts = []
        for chunk in batch:
            text = chunk["content"]
            if chunk.get("image_caption"):
                text = f"{text}\n\nImage description: {chunk['image_caption']}"
            texts.append(text)

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        # Generate embeddings
        embeddings = openai_client.get_embeddings_batch(texts)

        # Add embeddings to chunks
        for chunk, embedding in zip(batch, embeddings):
            chunk["content_vector"] = embedding

    logger.info("Embedding generation complete")
    return chunks


def prepare_documents(chunks: list[dict]) -> list[dict]:
    """Prepare documents for Azure AI Search upload.

    Args:
        chunks: List of chunks with embeddings.

    Returns:
        List of documents ready for indexing.
    """
    documents = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for chunk in chunks:
        doc = {
            "id": chunk["id"],
            "manual_name": chunk["manual_name"],
            "page": chunk["page"],
            "chunk_id": chunk["chunk_id"],
            "content": chunk["content"],
            "content_vector": chunk["content_vector"],
            "image_caption": chunk.get("image_caption"),
            "section_title": chunk.get("section_title"),
            "last_updated": timestamp,
        }
        documents.append(doc)

    return documents


def upload_documents(
    documents: list[dict],
    search_client: SearchClient,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Upload documents to Azure AI Search using merge_or_upload (upsert).

    Args:
        documents: List of documents to upload.
        search_client: Azure Search client instance.
        batch_size: Number of documents per upload batch.

    Returns:
        Tuple of (successful_count, failed_count).
    """
    logger.info(f"Uploading {len(documents)} documents to Azure AI Search...")

    successful = 0
    failed = 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(documents) + batch_size - 1) // batch_size

        logger.info(f"Uploading batch {batch_num}/{total_batches} ({len(batch)} documents)")

        try:
            # Use merge_or_upload for idempotent upsert
            results: list[IndexingResult] = search_client.merge_or_upload_documents(batch)

            for result in results:
                if result.succeeded:
                    successful += 1
                else:
                    failed += 1
                    logger.warning(
                        f"Failed to index document {result.key}: {result.error_message}"
                    )

        except Exception as e:
            logger.error(f"Batch upload failed: {e}")
            failed += len(batch)

    logger.info(f"Upload complete: {successful} successful, {failed} failed")
    return successful, failed


def main(input_path: str, dry_run: bool = False) -> int:
    """Main ingestion pipeline.

    Args:
        input_path: Path to input JSON file with chunks.
        dry_run: If True, skip actual upload to Azure.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    # Load environment variables
    load_dotenv()

    settings = get_settings()

    # Validate configuration
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        logger.error("Azure OpenAI credentials not configured")
        return 1

    if not dry_run and (not settings.azure_search_endpoint or not settings.azure_search_key):
        logger.error("Azure Search credentials not configured")
        return 1

    # Load and validate chunks
    try:
        chunks = load_chunks(input_path)
    except FileNotFoundError:
        logger.error(f"Input file not found: {input_path}")
        return 1
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in input file: {e}")
        return 1

    valid_chunks = [c for c in chunks if validate_chunk(c)]
    if len(valid_chunks) < len(chunks):
        logger.warning(
            f"Skipping {len(chunks) - len(valid_chunks)} invalid chunks"
        )

    if not valid_chunks:
        logger.error("No valid chunks to process")
        return 1

    # Generate embeddings
    try:
        openai_client = get_openai_client()
        chunks_with_embeddings = generate_embeddings(valid_chunks, openai_client)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return 1

    # Prepare documents
    documents = prepare_documents(chunks_with_embeddings)

    if dry_run:
        logger.info(f"Dry run: would upload {len(documents)} documents")
        for doc in documents:
            logger.info(
                f"  - {doc['id']}: {doc['manual_name']} p{doc['page']} "
                f"(vector dim: {len(doc['content_vector'])})"
            )
        return 0

    # Upload to Azure AI Search
    try:
        search_client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index,
            credential=AzureKeyCredential(settings.azure_search_key),
        )
        successful, failed = upload_documents(documents, search_client)
    except Exception as e:
        logger.error(f"Search client error: {e}")
        return 1

    if failed > 0:
        logger.warning(f"Indexing completed with {failed} failures")
        return 1

    logger.info(f"Successfully indexed {successful} documents")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Index manual chunks into Azure AI Search"
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to JSON file containing chunks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and generate embeddings without uploading",
    )

    args = parser.parse_args()
    exit_code = main(args.input, args.dry_run)
    sys.exit(exit_code)
