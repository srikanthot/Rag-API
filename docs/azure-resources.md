# Azure Resources Checklist

This document lists all Azure resources required for the RAG chatbot system.

## Required Azure Resources

### 1. Azure Blob Storage

**Purpose**: Store the 50+ confidential PDF manuals

**Configuration**:
- Create a Storage Account (Standard LRS or GRS for redundancy)
- Create a container named `manuals` (or as configured in `BLOB_CONTAINER`)
- Enable soft delete for blob protection
- Consider enabling versioning for audit trail

**Access**:
- Use connection string (`BLOB_CONN_STR`) or Managed Identity
- Ensure private endpoint if required for compliance

---

### 2. Azure AI Search

**Purpose**: Index and query manual content with hybrid (keyword + vector) search

**Configuration**:
- SKU: Standard S1 or higher (for vector search support)
- Enable semantic ranking (optional but recommended)
- Create index: `manuals-index` (or as configured in `AZURE_SEARCH_INDEX`)

**Features Required**:
- Vector search capability
- Hybrid search (keyword + vector)
- Filtering on `manual_name`, `page`
- Semantic ranking (optional)

**Access**:
- Admin key for indexing (`AZURE_SEARCH_KEY`)
- Query key for search operations (or Managed Identity)

---

### 3. Azure OpenAI

**Purpose**: Generate responses and create embeddings

**Deployments Required**:

| Deployment | Model | Purpose |
|------------|-------|---------|
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | gpt-4 or gpt-4-turbo | Response generation |
| `AZURE_OPENAI_EMBED_DEPLOYMENT` | text-embedding-ada-002 or text-embedding-3-small | Vector embeddings |

**Configuration**:
- Region: Choose region with model availability
- TPM (Tokens Per Minute): Size based on expected load

**Access**:
- API key (`AZURE_OPENAI_API_KEY`) or Managed Identity

---

### 4. Azure Document Intelligence

**Purpose**: OCR for scanned PDFs, images, and handwritten content

**Configuration**:
- SKU: S0 (Standard)
- Use prebuilt-read model for general document OCR
- Use prebuilt-layout for structure extraction

**Alternative**: Azure AI Search built-in OCR skill (less accurate for handwriting)

**Access**:
- Endpoint (`AZURE_DOC_INTELLIGENCE_ENDPOINT`)
- Key (`AZURE_DOC_INTELLIGENCE_KEY`) or Managed Identity

---

### 5. Azure Cosmos DB (Optional - for Phase 2)

**Purpose**: Store chat history and audit logs

**Configuration**:
- API: Core (SQL)
- Partition key: `/session_id` or `/user_id`
- TTL: Configure based on retention requirements

**Collections**:
- `chat_history`: Store conversation threads
- `audit_logs`: Track queries and responses

**Access**:
- Endpoint (`COSMOS_ENDPOINT`)
- Key (`COSMOS_KEY`) or Managed Identity

---

### 6. Azure Key Vault

**Purpose**: Securely store all secrets and keys

**Secrets to Store**:
- `azure-search-key`
- `azure-openai-key`
- `blob-connection-string`
- `doc-intelligence-key`
- `cosmos-key`

**Access**:
- Use Managed Identity from App Service
- Grant "Key Vault Secrets User" role

---

### 7. Azure App Service

**Purpose**: Host the FastAPI application

**Configuration**:
- SKU: B1 or higher (P1v2+ for production)
- Runtime: Python 3.10+
- Enable Managed Identity
- Configure environment variables from Key Vault references

**Alternative**: Azure Functions (for serverless deployment)

**Networking**:
- Consider VNet integration for private endpoints
- Enable HTTPS only

---

## Resource Provisioning Order

1. **Key Vault** - Create first to store secrets
2. **Storage Account** - For PDF storage
3. **Azure AI Search** - For indexing
4. **Azure OpenAI** - For embeddings and chat
5. **Document Intelligence** - For OCR
6. **Cosmos DB** - For audit (optional)
7. **App Service** - Deploy application last

## Managed Identity Setup

For production, use Managed Identity instead of keys:

1. Enable System Assigned Managed Identity on App Service
2. Grant roles:
   - Storage Blob Data Reader on Storage Account
   - Search Index Data Contributor on AI Search
   - Cognitive Services OpenAI User on OpenAI
   - Key Vault Secrets User on Key Vault

## Cost Estimation

| Resource | SKU | Estimated Monthly Cost |
|----------|-----|------------------------|
| AI Search | S1 | ~$250 |
| OpenAI | Pay-as-you-go | Variable (~$100-500) |
| App Service | P1v2 | ~$75 |
| Storage | Standard LRS | ~$5 |
| Document Intelligence | S0 | ~$50 |
| Cosmos DB | Serverless | ~$25 |
| Key Vault | Standard | ~$1 |

*Costs vary by region and usage*

## Security Considerations

- Enable private endpoints for all services
- Use Managed Identity over API keys
- Enable diagnostic logging
- Configure network security groups
- Enable Azure Defender for cloud resources
- Implement RBAC for all resources
