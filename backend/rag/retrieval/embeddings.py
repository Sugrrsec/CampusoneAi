from __future__ import annotations

import threading
from typing import Sequence

import numpy as np


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    """
    Creates semantic embeddings for document chunks and user queries.

    This is an embedding model, not a conversational LLM.
    Supports lazy loading to prevent blocking application startup.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        lazy: bool = True,
    ) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        if not lazy:
            self._load_model()

    @property
    def model(self):
        """Thread-safe lazy property for the underlying SentenceTransformer."""
        if self._model is None:
            self._load_model()
        return self._model

    @model.setter
    def model(self, value) -> None:
        self._model = value

    def _load_model(self) -> None:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        import torch

                        # Limit threads on cloud container environments (e.g., Render)
                        torch.set_num_threads(1)
                        torch.set_num_interop_threads(1)
                    except Exception:
                        pass
                    try:
                        from sentence_transformers import SentenceTransformer
                        self._model = SentenceTransformer(self.model_name)
                    except ImportError as exc:
                        raise ImportError(
                            "sentence-transformers is not installed. "
                            "CampusOne AI uses lightweight BM25 retrieval for production deployment. "
                            "Install 'sentence-transformers' only if you need embedding generation."
                        ) from exc

    @property
    def is_loaded(self) -> bool:
        """Whether the model weights are currently loaded in memory."""
        return self._model is not None

    @property
    def dimension(self) -> int:
        """Return the size of each generated embedding vector."""
        if self._model is not None:
            dimension = self._model.get_embedding_dimension()
            return int(dimension)

        # Common model dimension shortcuts to avoid eager PyTorch loading
        if "all-MiniLM-L6-v2" in self.model_name:
            return 384
        if "all-mpnet-base-v2" in self.model_name:
            return 768

        dimension = self.model.get_embedding_dimension()

        if dimension is None:
            raise RuntimeError(
                "Could not determine embedding dimension."
            )

        return int(dimension)

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> np.ndarray:
        """
        Convert document chunks into normalized embedding vectors.
        """

        if not texts:
            return np.empty(
                (0, self.dimension),
                dtype=np.float32,
            )

        cleaned_texts = [
            text.strip()
            for text in texts
            if text and text.strip()
        ]

        if not cleaned_texts:
            return np.empty(
                (0, self.dimension),
                dtype=np.float32,
            )

        embeddings = self.model.encode(
            cleaned_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return np.asarray(
            embeddings,
            dtype=np.float32,
        )

    def embed_query(
        self,
        query: str,
    ) -> np.ndarray:
        """
        Convert one user query into a normalized embedding vector.
        """

        query = query.strip()

        if not query:
            raise ValueError(
                "Query cannot be empty."
            )

        embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return np.asarray(
            embedding[0],
            dtype=np.float32,
        )


__all__ = [
    "EmbeddingService",
    "DEFAULT_EMBEDDING_MODEL",
]