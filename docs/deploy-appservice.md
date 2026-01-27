# Azure App Service Deployment Guide

This document describes how to deploy the Azure RAG Chatbot to Azure App Service (Linux).

## Prerequisites

- Azure subscription with appropriate permissions
- Azure CLI installed and configured
- Docker (for local testing)
- Git repository access

## Deployment Options

### Option 1: Docker Container (Recommended)

The application includes a production-ready Dockerfile.

### Option 2: Direct Code Deployment

Use the startup command with Gunicorn/Uvicorn.

## Step-by-Step Deployment

### 1. Create Resource Group

```bash
az group create \
  --name rg-rag-chatbot \
  --location eastus
```

### 2. Create App Service Plan

```bash
az appservice plan create \
  --name asp-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --is-linux \
  --sku B1
```

**SKU Options:**
- `B1`: Basic tier, suitable for development/testing
- `S1`: Standard tier, recommended for production
- `P1V2`: Premium tier, for high-traffic production

### 3. Create Azure Container Registry (for Docker deployment)

```bash
az acr create \
  --name acrragchatbot \
  --resource-group rg-rag-chatbot \
  --sku Basic \
  --admin-enabled true
```

### 4. Build and Push Docker Image

```bash
# Login to ACR
az acr login --name acrragchatbot

# Build and push image
az acr build \
  --registry acrragchatbot \
  --image rag-chatbot:latest \
  --file Dockerfile \
  .
```

### 5. Create App Service

**Option A: Docker Container**

```bash
az webapp create \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --plan asp-rag-chatbot \
  --deployment-container-image-name acrragchatbot.azurecr.io/rag-chatbot:latest
```

**Option B: Code Deployment**

```bash
az webapp create \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --plan asp-rag-chatbot \
  --runtime "PYTHON:3.11"
```

### 6. Configure Container Registry Access

```bash
# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name acrragchatbot --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name acrragchatbot --query passwords[0].value -o tsv)

# Configure webapp to use ACR
az webapp config container set \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --docker-custom-image-name acrragchatbot.azurecr.io/rag-chatbot:latest \
  --docker-registry-server-url https://acrragchatbot.azurecr.io \
  --docker-registry-server-user $ACR_USERNAME \
  --docker-registry-server-password $ACR_PASSWORD
```

### 7. Configure Environment Variables

```bash
az webapp config appsettings set \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --settings \
    AZURE_SEARCH_ENDPOINT="https://your-search.search.windows.net" \
    AZURE_SEARCH_KEY="your-search-key" \
    AZURE_SEARCH_INDEX="manuals-index" \
    AZURE_OPENAI_ENDPOINT="https://your-openai.openai.azure.com" \
    AZURE_OPENAI_API_KEY="your-openai-key" \
    AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4" \
    AZURE_OPENAI_EMBED_DEPLOYMENT="text-embedding-ada-002" \
    AUTH_MODE="api_key" \
    API_KEY="your-secure-api-key" \
    COSMOS_ENDPOINT="https://your-cosmos.documents.azure.com:443/" \
    COSMOS_KEY="your-cosmos-key" \
    COSMOS_DATABASE="rag-chatbot" \
    COSMOS_CONTAINER="audit-logs" \
    AUDIT_ENABLED="true"
```

**Security Note:** For production, use Azure Key Vault references instead of plain text:

```bash
az webapp config appsettings set \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --settings \
    AZURE_OPENAI_API_KEY="@Microsoft.KeyVault(SecretUri=https://your-keyvault.vault.azure.net/secrets/openai-key/)"
```

### 8. Configure Startup Command (Code Deployment Only)

If using code deployment instead of Docker:

```bash
az webapp config set \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --workers=4 --worker-class=uvicorn.workers.UvicornWorker app.main:app"
```

### 9. Enable Managed Identity

```bash
# Enable system-assigned managed identity
az webapp identity assign \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot

# Get the principal ID
PRINCIPAL_ID=$(az webapp identity show \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --query principalId -o tsv)

echo "Managed Identity Principal ID: $PRINCIPAL_ID"
```

### 10. Grant Managed Identity Permissions

**Azure AI Search:**

```bash
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Search Index Data Reader" \
  --scope /subscriptions/{subscription-id}/resourceGroups/rg-rag-chatbot/providers/Microsoft.Search/searchServices/your-search-service
```

**Azure OpenAI:**

```bash
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Cognitive Services OpenAI User" \
  --scope /subscriptions/{subscription-id}/resourceGroups/rg-rag-chatbot/providers/Microsoft.CognitiveServices/accounts/your-openai-account
```

**Azure Blob Storage:**

```bash
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Blob Data Reader" \
  --scope /subscriptions/{subscription-id}/resourceGroups/rg-rag-chatbot/providers/Microsoft.Storage/storageAccounts/your-storage-account
```

**Azure Cosmos DB:**

```bash
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Cosmos DB Built-in Data Contributor" \
  --scope /subscriptions/{subscription-id}/resourceGroups/rg-rag-chatbot/providers/Microsoft.DocumentDB/databaseAccounts/your-cosmos-account
```

### 11. Configure HTTPS and Custom Domain (Optional)

```bash
# Enable HTTPS only
az webapp update \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --https-only true

# Add custom domain
az webapp config hostname add \
  --webapp-name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --hostname api.yourdomain.com
```

### 12. Enable Logging

```bash
az webapp log config \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --application-logging filesystem \
  --detailed-error-messages true \
  --failed-request-tracing true \
  --web-server-logging filesystem
```

## Networking (Optional)

### Private Endpoints

For enhanced security, configure private endpoints for Azure services:

```bash
# Create VNet
az network vnet create \
  --name vnet-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --address-prefix 10.0.0.0/16 \
  --subnet-name subnet-webapp \
  --subnet-prefix 10.0.1.0/24

# Enable VNet integration for App Service
az webapp vnet-integration add \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --vnet vnet-rag-chatbot \
  --subnet subnet-webapp
```

### IP Restrictions

```bash
az webapp config access-restriction add \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --rule-name "AllowCorporateNetwork" \
  --action Allow \
  --ip-address 203.0.113.0/24 \
  --priority 100
```

## Scaling

### Manual Scaling

```bash
az appservice plan update \
  --name asp-rag-chatbot \
  --resource-group rg-rag-chatbot \
  --number-of-workers 3
```

### Auto-Scaling

```bash
az monitor autoscale create \
  --resource-group rg-rag-chatbot \
  --resource asp-rag-chatbot \
  --resource-type Microsoft.Web/serverfarms \
  --name autoscale-rag-chatbot \
  --min-count 1 \
  --max-count 10 \
  --count 2

az monitor autoscale rule create \
  --resource-group rg-rag-chatbot \
  --autoscale-name autoscale-rag-chatbot \
  --condition "CpuPercentage > 70 avg 5m" \
  --scale out 1
```

## Verification

### Test Health Endpoint

```bash
curl https://app-rag-chatbot.azurewebsites.net/health
# Expected: {"status": "ok"}
```

### Test Chat Endpoint

```bash
curl -X POST https://app-rag-chatbot.azurewebsites.net/chat \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-api-key" \
  -d '{"question": "What is the safety procedure?"}'
```

### View Logs

```bash
az webapp log tail \
  --name app-rag-chatbot \
  --resource-group rg-rag-chatbot
```

## Troubleshooting

### Container Not Starting

1. Check container logs:
   ```bash
   az webapp log download \
     --name app-rag-chatbot \
     --resource-group rg-rag-chatbot \
     --log-file logs.zip
   ```

2. Verify environment variables are set correctly

3. Test container locally:
   ```bash
   docker run -p 8000:8000 \
     -e AZURE_SEARCH_ENDPOINT=... \
     acrragchatbot.azurecr.io/rag-chatbot:latest
   ```

### Authentication Errors

1. Verify API_KEY is set correctly
2. Check AUTH_MODE setting
3. For managed identity, verify role assignments

### Performance Issues

1. Check App Service plan tier
2. Review Azure Monitor metrics
3. Consider scaling up or out
4. Check Azure OpenAI rate limits

## Cost Optimization

1. Use appropriate App Service tier for workload
2. Enable auto-scaling to handle variable load
3. Use reserved instances for predictable workloads
4. Monitor and optimize Azure OpenAI usage
5. Set Cosmos DB TTL for audit logs

## Security Checklist

- [ ] HTTPS only enabled
- [ ] API key stored in Key Vault
- [ ] Managed identity configured
- [ ] Network restrictions in place
- [ ] Logging enabled
- [ ] Regular key rotation scheduled
- [ ] Backup strategy defined
