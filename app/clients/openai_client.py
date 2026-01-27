"""Azure OpenAI client for embeddings and chat completions."""

import logging
from typing import Optional

from openai import AzureOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for Azure OpenAI embeddings and chat completions."""

    def __init__(self):
        """Initialize the Azure OpenAI client."""
        settings = get_settings()
        self.client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version="2024-02-01",
            azure_endpoint=settings.azure_openai_endpoint,
        )
        self.embed_deployment = settings.azure_openai_embed_deployment
        self.chat_deployment = settings.azure_openai_chat_deployment
        self.temperature = settings.temperature

    def get_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        response = self.client.embeddings.create(
            model=self.embed_deployment,
            input=text,
        )
        return response.data[0].embedding

    def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.embed_deployment,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def chat_completion(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Override default temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            The assistant's response text.
        """
        response = self.client.chat.completions.create(
            model=self.chat_deployment,
            messages=messages,
            temperature=temperature if temperature is not None else self.temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get or create the OpenAI client singleton."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client
