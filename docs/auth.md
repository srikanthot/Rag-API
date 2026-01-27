# Authentication Guide

This document describes the authentication mechanisms available for the Azure RAG Chatbot API.

## Overview

The API supports two authentication modes, switchable via the `AUTH_MODE` environment variable:

1. **API Key Authentication (POC)** - Simple header-based authentication for development and proof-of-concept deployments
2. **Managed Identity / Entra ID (Enterprise)** - Azure Active Directory authentication for production deployments

## Mode A: API Key Authentication

API Key authentication is the simplest option, suitable for POC and development environments.

### Configuration

Set the following environment variables:

```bash
AUTH_MODE=api_key
API_KEY=your-secure-api-key-here
```

### Usage

Include the `X-API-KEY` header in all requests to protected endpoints:

```bash
curl -X POST "https://your-api.azurewebsites.net/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-secure-api-key-here" \
  -d '{"question": "What is the safety procedure?"}'
```

### Security Recommendations

When using API Key authentication:

- Generate a strong, random API key (minimum 32 characters)
- Store the API key in Azure Key Vault, not in code or config files
- Rotate keys periodically
- Use HTTPS to prevent key interception
- Consider IP allowlisting for additional security

## Mode B: Managed Identity / Entra ID Authentication

For enterprise deployments, use Azure Entra ID (formerly Azure AD) with Managed Identity.

### Configuration

Set the following environment variables:

```bash
AUTH_MODE=managed_identity
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
```

For service principal authentication (non-managed identity scenarios):

```bash
AZURE_CLIENT_SECRET=your-client-secret
```

### Usage

Include a Bearer token in the Authorization header:

```bash
curl -X POST "https://your-api.azurewebsites.net/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIs..." \
  -d '{"question": "What is the safety procedure?"}'
```

### Obtaining a Token

#### From Azure CLI

```bash
az login
TOKEN=$(az account get-access-token --resource api://your-client-id --query accessToken -o tsv)
curl -H "Authorization: Bearer $TOKEN" ...
```

#### From Managed Identity (in Azure)

When running in Azure App Service with Managed Identity enabled:

```python
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
token = credential.get_token("api://your-client-id/.default")
```

#### From Service Principal

```python
from azure.identity import ClientSecretCredential

credential = ClientSecretCredential(
    tenant_id="your-tenant-id",
    client_id="your-client-id",
    client_secret="your-client-secret"
)
token = credential.get_token("api://your-client-id/.default")
```

### Azure Setup for Managed Identity

1. **Register an App in Entra ID**
   - Go to Azure Portal > Entra ID > App registrations
   - Click "New registration"
   - Name: "RAG Chatbot API"
   - Supported account types: "Accounts in this organizational directory only"
   - Click "Register"

2. **Configure API Permissions**
   - In the app registration, go to "Expose an API"
   - Set Application ID URI (e.g., `api://rag-chatbot`)
   - Add scopes as needed (e.g., `Chat.Read`)

3. **Enable Managed Identity on App Service**
   - Go to your App Service > Identity
   - Enable "System assigned" managed identity
   - Note the Object ID

4. **Grant Permissions**
   - In the app registration, go to "API permissions"
   - Add the required permissions
   - Grant admin consent if required

### RBAC Notes

For fine-grained access control, consider implementing role-based access:

| Role | Description | Permissions |
|------|-------------|-------------|
| `Chat.User` | Basic chat access | Can use /chat endpoint |
| `Chat.Admin` | Administrative access | Can view audit logs, manage settings |

Roles can be defined in the Entra ID app manifest and assigned to users/groups.

## Public Endpoints

The following endpoints remain public (no authentication required):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/docs` | GET | Swagger UI documentation |
| `/redoc` | GET | ReDoc documentation |
| `/openapi.json` | GET | OpenAPI specification |

## Protected Endpoints

The following endpoints require authentication:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | RAG chat endpoint |

## Error Responses

### 401 Unauthorized

Returned when authentication fails:

**Missing API Key:**
```json
{
  "detail": "Missing X-API-KEY header"
}
```

**Invalid API Key:**
```json
{
  "detail": "Invalid API key"
}
```

**Missing Bearer Token:**
```json
{
  "detail": "Missing Authorization header"
}
```

**Invalid Token:**
```json
{
  "detail": "Invalid or expired token"
}
```

## Outbound Authentication (Managed Identity)

When `AUTH_MODE=managed_identity`, the application uses Managed Identity for outbound calls to Azure services:

### Azure AI Search

The application can authenticate to Azure AI Search using Managed Identity instead of API keys:

1. Enable Managed Identity on your App Service
2. Grant the "Search Index Data Reader" role to the managed identity on your Azure AI Search resource
3. The SDK will automatically use the managed identity for authentication

### Azure Blob Storage

For accessing manuals stored in Blob Storage:

1. Grant the "Storage Blob Data Reader" role to the managed identity
2. The SDK will use managed identity credentials automatically

### Azure OpenAI

For Azure OpenAI calls:

1. Grant the "Cognitive Services OpenAI User" role to the managed identity
2. Configure the OpenAI client to use DefaultAzureCredential

## Switching Between Modes

To switch authentication modes:

1. Update the `AUTH_MODE` environment variable
2. Restart the application
3. Update client applications to use the appropriate authentication method

No code changes are required - the mode is entirely configuration-driven.

## Testing Authentication

### Test API Key Mode

```bash
# Should fail (no key)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
# Expected: 401 Unauthorized

# Should succeed (with key)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-api-key" \
  -d '{"question": "test"}'
# Expected: 200 OK (or appropriate response)
```

### Test Health Endpoint (Always Public)

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```
