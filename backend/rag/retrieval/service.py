from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from backend.router.schemas import RouteResult

from .retriever import (
    DEFAULT_MIN_SCORE,
    DomainRetriever,
)


DEFAULT_VECTOR_STORE_PATH = (
    "data/processed/vector_stores"
)

DEFAULT_TOP_K = 5


class RetrievalService:
    """
    Public retrieval interface for CampusOne AI using lightweight BM25 indices.
    """

    def __init__(
        self,
        vector_store_path: str | Path = DEFAULT_VECTOR_STORE_PATH,
        embedding_model: str | None = None,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> None:
        self.vector_store_path = Path(
            vector_store_path
        )
        self.min_score = min_score
        self.retriever: DomainRetriever | None = None
        # embedding_service kept as None; BM25 operates without ML models
        self.embedding_service = None

    @property
    def is_loaded(self) -> bool:
        """Whether stores are loaded and ready for retrieval."""
        return self.retriever is not None

    def ensure_initialized(
        self,
        chunk_file: str | Path = "data/processed/scset_ug_chunks.jsonl",
    ) -> None:
        """
        Ensure BM25 document stores are loaded.
        If indexes already exist on disk, loads them.
        If not, builds them in-memory (<5 ms) from chunk_file.
        """
        if self.retriever is not None:
            return

        # Check if saved document stores exist on disk
        existing_index = any(
            (self.vector_store_path / domain / "documents.json").exists()
            or (self.vector_store_path / domain / "metadata.json").exists()
            for domain in (
                "IT",
                "HR_ADMIN",
                "FEES",
                "FACILITIES",
            )
        )

        if existing_index:
            self.load()
            return

        chunk_path = Path(chunk_file)
        if not chunk_path.exists():
            raise RuntimeError(
                f"Chunk file is missing: {chunk_path}"
            )

        from .dataset_loader import load_and_normalize_chunks

        documents = load_and_normalize_chunks(chunk_path)
        retriever = DomainRetriever()
        retriever.build(documents)
        self.retriever = retriever

    def load(self) -> None:
        """Load the persisted stores or initialize from default chunk file."""
        existing_index = any(
            (self.vector_store_path / domain / "documents.json").exists()
            or (self.vector_store_path / domain / "metadata.json").exists()
            for domain in (
                "IT",
                "HR_ADMIN",
                "FEES",
                "FACILITIES",
            )
        )

        if existing_index:
            self.retriever = DomainRetriever.load(
                directory=self.vector_store_path
            )
        else:
            self.ensure_initialized()

    def retrieve(
        self,
        query: str,
        domains: Sequence[str],
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant chunks using BM25 ranking."""
        if not query.strip():
            raise ValueError(
                "Query cannot be empty."
            )

        if self.retriever is None:
            raise RuntimeError(
                "RetrievalService is not loaded. "
                "Call load() or ensure_initialized() before retrieve()."
            )

        return self.retriever.retrieve(
            query=query,
            domains=domains,
            top_k=top_k,
            min_score=self.min_score,
        )

    def retrieve_for_route(
        self,
        query: str,
        route_result: RouteResult,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """
        Retrieve documents using Member 1's RouteResult.
        """
        if not query.strip():
            raise ValueError(
                "Query cannot be empty."
            )

        if route_result.is_out_of_scope:
            return []

        if route_result.needs_clarification:
            return []

        if not route_result.domains:
            return []

        if route_result.intent == "revaluation":
            # The current academic rules dataset contains no revaluation policy
            return []

        return self.retrieve(
            query=query,
            domains=route_result.domains,
            top_k=top_k,
        )

    def domain_sizes(self) -> dict[str, int]:
        """Return indexed chunk counts."""
        if self.retriever is None:
            raise RuntimeError(
                "RetrievalService is not loaded."
            )

        return {
            domain: self.retriever.size(domain)
            for domain in (
                "IT",
                "HR_ADMIN",
                "FEES",
                "FACILITIES",
            )
        }


__all__ = [
    "RetrievalService",
    "DEFAULT_VECTOR_STORE_PATH",
    "DEFAULT_TOP_K",
    "DEFAULT_MIN_SCORE",
]
