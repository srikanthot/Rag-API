# Audit Logging Guide

This document describes the audit logging system for the Azure RAG Chatbot, which uses Azure Cosmos DB to store request metadata for traceability and compliance.

## Overview

The audit logging system captures metadata about each chat request without storing sensitive content. This enables:

- Request traceability and debugging
- Usage analytics and monitoring
- Compliance and audit requirements
- Session history tracking

## What is Logged

### Stored per Request

| Field | Description | Example |
|-------|-------------|---------|
| `id` | Unique request identifier (UUID) | `"a1b2c3d4-e5f6-..."` |
| `session_id` | Session identifier for conversation tracking | `"session-123"` |
| `user_id` | User identifier for audit purposes | `"user@example.com"` |
| `timestamp` | ISO 8601 timestamp | `"2024-01-15T10:30:00Z"` |
| `question` | The user's question text | `"What is the safety procedure?"` |
| `auth_mode` | Authentication mode used | `"api_key"` or `"managed_identity"` |
| `record_type` | Type of audit record | `"chat_request"` |

### Retrieval Metadata (per chunk)

| Field | Description |
|-------|-------------|
| `manual_name` | Source manual filename |
| `page` | Page number in the manual |
| `chunk_id` | Unique chunk identifier |
| `score` | Retrieval relevance score |
| `reranker_score` | Reranker score (if available) |

### Response Metadata

| Field | Description |
|-------|-------------|
| `confidence` | Response confidence level (high/medium/low) |
| `latency_ms` | Request processing time in milliseconds |
| `citation_count` | Number of citations in the response |

## What is NOT Logged

To protect sensitive information and comply with data minimization principles:

- Full retrieved chunk content
- Full manual content
- Image data or binary content
- Raw LLM prompts or completions
- API keys or authentication tokens

## Configuration

### Environment Variables

```bash
# Cosmos DB Connection
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE=rag-chatbot
COSMOS_CONTAINER=audit-logs

# Enable/Disable Audit Logging
AUDIT_ENABLED=true
```

### Toggle Audit Logging

Set `AUDIT_ENABLED=false` to disable audit logging entirely. This is useful for:

- Development environments
- Performance testing
- Privacy-sensitive deployments

When disabled, the audit service gracefully skips all logging operations.

## Azure Cosmos DB Setup

### 1. Create Cosmos DB Account

```bash
az cosmosdb create \
  --name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --kind GlobalDocumentDB \
  --default-consistency-level Session
```

### 2. Create Database and Container

The application automatically creates the database and container if they don't exist. Alternatively, create them manually:

```bash
# Create database
az cosmosdb sql database create \
  --account-name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --name rag-chatbot

# Create container with partition key
az cosmosdb sql container create \
  --account-name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --database-name rag-chatbot \
  --name audit-logs \
  --partition-key-path /session_id \
  --throughput 400
```

### 3. Get Connection Details

```bash
# Get endpoint
az cosmosdb show \
  --name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --query documentEndpoint -o tsv

# Get primary key
az cosmosdb keys list \
  --name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --query primaryMasterKey -o tsv
```

## Partition Strategy

The audit logs use `session_id` as the partition key. This provides:

- Efficient queries for session history
- Good distribution of data across partitions
- Logical grouping of related requests

For anonymous requests (no session_id), the value defaults to `"anonymous"`.

## Sample Audit Record

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "session_id": "session-abc123",
  "user_id": "user@example.com",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "question": "What is the emergency shutdown procedure?",
  "retrieval_metadata": [
    {
      "manual_name": "Safety_Manual.pdf",
      "page": 45,
      "chunk_id": "safety-manual-p45-c1",
      "score": 0.92,
      "reranker_score": 0.88
    },
    {
      "manual_name": "Operations_Guide.pdf",
      "page": 12,
      "chunk_id": "ops-guide-p12-c3",
      "score": 0.85,
      "reranker_score": null
    }
  ],
  "response_metadata": {
    "confidence": "high",
    "latency_ms": 1250.5,
    "citation_count": 2
  },
  "auth_mode": "api_key",
  "record_type": "chat_request"
}
```

## Querying Audit Logs

### Query by Session

```sql
SELECT * FROM c 
WHERE c.session_id = 'session-abc123' 
ORDER BY c.timestamp DESC
```

### Query by User

```sql
SELECT TOP 100 * FROM c 
WHERE c.user_id = 'user@example.com' 
ORDER BY c.timestamp DESC
```

### Query by Time Range

```sql
SELECT * FROM c 
WHERE c.timestamp >= '2024-01-01T00:00:00Z' 
  AND c.timestamp < '2024-02-01T00:00:00Z'
ORDER BY c.timestamp DESC
```

### Query Low Confidence Responses

```sql
SELECT * FROM c 
WHERE c.response_metadata.confidence = 'low'
ORDER BY c.timestamp DESC
```

## Validation

To verify audit logging is working:

1. Ensure `AUDIT_ENABLED=true` and Cosmos DB credentials are configured
2. Make a `/chat` request
3. Check Cosmos DB for the new record:

```bash
# Using Azure CLI
az cosmosdb sql container show \
  --account-name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --database-name rag-chatbot \
  --name audit-logs

# Or use Azure Portal Data Explorer to query the container
```

## Data Retention

Consider implementing a TTL (Time-To-Live) policy for automatic data cleanup:

```bash
# Set 90-day TTL on the container
az cosmosdb sql container update \
  --account-name rag-chatbot-cosmos \
  --resource-group your-resource-group \
  --database-name rag-chatbot \
  --name audit-logs \
  --ttl 7776000  # 90 days in seconds
```

## Cost Optimization

Tips for managing Cosmos DB costs:

1. **Use serverless** for low-traffic deployments
2. **Set appropriate throughput** (400 RU/s minimum for provisioned)
3. **Enable TTL** to automatically delete old records
4. **Use efficient queries** with partition key filters
5. **Monitor usage** with Azure Monitor

## Security Considerations

1. **Access Control**: Use Azure RBAC to restrict access to Cosmos DB
2. **Encryption**: Data is encrypted at rest by default
3. **Network Security**: Consider using private endpoints
4. **Key Rotation**: Rotate Cosmos DB keys periodically
5. **Audit Access**: Enable diagnostic logging for Cosmos DB itself

## Troubleshooting

### Audit Records Not Appearing

1. Check `AUDIT_ENABLED=true`
2. Verify Cosmos DB credentials are correct
3. Check application logs for connection errors
4. Ensure the container exists and is accessible

### High Latency

1. Check Cosmos DB region matches your app region
2. Consider increasing throughput (RU/s)
3. Review query patterns for efficiency

### Connection Errors

1. Verify network connectivity to Cosmos DB
2. Check firewall rules allow your app's IP
3. Ensure credentials haven't expired
