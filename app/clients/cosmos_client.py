"""Azure Cosmos DB client for audit logging and chat history storage."""

import logging
from typing import Optional

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.cosmos.container import ContainerProxy
from azure.cosmos.database import DatabaseProxy

from app.config import get_settings

logger = logging.getLogger(__name__)


class AzureCosmosClient:
    """Client for Azure Cosmos DB operations."""

    def __init__(self):
        """Initialize the Cosmos DB client."""
        settings = get_settings()

        if not settings.cosmos_endpoint or not settings.cosmos_key:
            logger.warning("Cosmos DB credentials not configured - audit logging disabled")
            self._client = None
            self._database = None
            self._container = None
            return

        try:
            self._client = CosmosClient(
                url=settings.cosmos_endpoint,
                credential=settings.cosmos_key,
            )
            self._database = self._get_or_create_database(settings.cosmos_database)
            self._container = self._get_or_create_container(settings.cosmos_container)
            logger.info(f"Cosmos DB client initialized (database={settings.cosmos_database}, container={settings.cosmos_container})")
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB client: {e}")
            self._client = None
            self._database = None
            self._container = None

    def _get_or_create_database(self, database_name: str) -> Optional[DatabaseProxy]:
        """Get or create the database.

        Args:
            database_name: Name of the database.

        Returns:
            DatabaseProxy instance or None if creation fails.
        """
        if not self._client or not database_name:
            return None

        try:
            return self._client.create_database_if_not_exists(id=database_name)
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to create/get database '{database_name}': {e}")
            return None

    def _get_or_create_container(self, container_name: str) -> Optional[ContainerProxy]:
        """Get or create the container.

        Args:
            container_name: Name of the container.

        Returns:
            ContainerProxy instance or None if creation fails.
        """
        if not self._database or not container_name:
            return None

        try:
            return self._database.create_container_if_not_exists(
                id=container_name,
                partition_key=PartitionKey(path="/session_id"),
                offer_throughput=400,  # Minimum RU/s for cost efficiency
            )
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to create/get container '{container_name}': {e}")
            return None

    @property
    def is_available(self) -> bool:
        """Check if Cosmos DB client is available and configured."""
        return self._container is not None

    def create_item(self, item: dict) -> Optional[dict]:
        """Create a new item in the container.

        Args:
            item: The item to create. Must include 'id' and 'session_id' fields.

        Returns:
            The created item or None if creation fails.
        """
        if not self._container:
            logger.debug("Cosmos DB not available - skipping item creation")
            return None

        try:
            result = self._container.create_item(body=item)
            logger.debug(f"Created Cosmos DB item: {item.get('id')}")
            return result
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to create item: {e}")
            return None

    def upsert_item(self, item: dict) -> Optional[dict]:
        """Create or update an item in the container.

        Args:
            item: The item to upsert. Must include 'id' and 'session_id' fields.

        Returns:
            The upserted item or None if operation fails.
        """
        if not self._container:
            logger.debug("Cosmos DB not available - skipping item upsert")
            return None

        try:
            result = self._container.upsert_item(body=item)
            logger.debug(f"Upserted Cosmos DB item: {item.get('id')}")
            return result
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to upsert item: {e}")
            return None

    def read_item(self, item_id: str, partition_key: str) -> Optional[dict]:
        """Read an item from the container.

        Args:
            item_id: The item ID.
            partition_key: The partition key (session_id).

        Returns:
            The item or None if not found.
        """
        if not self._container:
            return None

        try:
            return self._container.read_item(item=item_id, partition_key=partition_key)
        except exceptions.CosmosResourceNotFoundError:
            return None
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to read item: {e}")
            return None

    def query_items(
        self,
        query: str,
        parameters: Optional[list] = None,
        partition_key: Optional[str] = None,
    ) -> list[dict]:
        """Query items from the container.

        Args:
            query: SQL query string.
            parameters: Query parameters.
            partition_key: Optional partition key for scoped queries.

        Returns:
            List of matching items.
        """
        if not self._container:
            return []

        try:
            items = self._container.query_items(
                query=query,
                parameters=parameters or [],
                partition_key=partition_key,
            )
            return list(items)
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to query items: {e}")
            return []


_cosmos_client: Optional[AzureCosmosClient] = None


def get_cosmos_client() -> AzureCosmosClient:
    """Get or create the Cosmos DB client singleton."""
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = AzureCosmosClient()
    return _cosmos_client
