"""Configuration settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "manuals-index"

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_embed_deployment: str = ""

    # Azure Blob Storage
    blob_conn_str: str = ""
    blob_container: str = "manuals"

    # RAG Configuration
    top_k: int = 6
    temperature: float = 0.0
    min_grounded_score: float = 0.7

    # Embedding dimensions (text-embedding-ada-002 = 1536)
    embedding_dimensions: int = 1536

    # Authentication Configuration
    auth_mode: str = "api_key"  # "api_key" or "managed_identity"
    api_key: str = ""  # Required when auth_mode is "api_key"

    # Azure Entra ID / Managed Identity (for auth_mode="managed_identity")
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""  # Only for service principal, not managed identity

    # Cosmos DB (for audit logging and chat history)
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "rag-chatbot"
    cosmos_container: str = "audit-logs"

    # Audit Configuration
    audit_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
